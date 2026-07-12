from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .utils import create_stock_picking, group_untracked_lines


class MobileRawQC(models.Model):
    _name = "mobile.raw.qc"
    _description = "Incoming Raw Material QC"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    receipt_id = fields.Many2one("mobile.raw.receipt", required=True, ondelete="restrict", check_company=True, tracking=True)
    config_id = fields.Many2one(related="receipt_id.config_id", store=True)
    company_id = fields.Many2one(related="receipt_id.company_id", store=True, index=True)
    partner_id = fields.Many2one(related="receipt_id.partner_id", store=True)
    line_ids = fields.One2many("mobile.raw.qc.line", "qc_id", string="Inspection Lines", copy=True)
    pass_picking_id = fields.Many2one("stock.picking", string="Accepted Material Transfer", copy=False, check_company=True)
    fail_picking_id = fields.Many2one("stock.picking", string="Rejected Material Transfer", copy=False, check_company=True)
    state = fields.Selection([
        ("draft", "Inspection Pending"),
        ("transfer_pending", "Transfers Pending"),
        ("done", "Completed"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)
    inspected_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, tracking=True)
    inspection_date = fields.Datetime(default=fields.Datetime.now)
    notes = fields.Html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mobile.raw.qc") or _("New")
        return super().create(vals_list)

    @api.model
    def create_from_receipt(self, receipt):
        if receipt.picking_id.state != "done":
            raise UserError(_("The receipt transfer must be done before creating QC."))
        line_commands = []
        for move in receipt.picking_id.move_ids.filtered(lambda m: m.state == "done"):
            done_lines = move.move_line_ids.filtered(lambda ml: ml.quantity > 0)
            if done_lines:
                for move_line in done_lines:
                    line_commands.append(Command.create({
                        "product_id": move.product_id.id,
                        "uom_id": move_line.product_uom_id.id,
                        "received_qty": move_line.quantity,
                        "pass_qty": move_line.quantity,
                        "lot_id": move_line.lot_id.id,
                    }))
            else:
                line_commands.append(Command.create({
                    "product_id": move.product_id.id,
                    "uom_id": move.product_uom.id,
                    "received_qty": move.quantity,
                    "pass_qty": move.quantity,
                }))
        if not line_commands:
            raise UserError(_("No completed receipt quantities were found."))
        return self.create({
            "receipt_id": receipt.id,
            "line_ids": line_commands,
        })

    def action_validate_qc(self):
        self.ensure_one()
        self.config_id._check_ready()
        if self.state != "draft":
            raise UserError(_("Only a pending QC can be validated."))
        pass_specs = []
        fail_specs = []
        for line in self.line_ids:
            line._check_result_quantities()
            base = {
                "product": line.product_id,
                "uom": line.uom_id,
                "lot": line.lot_id,
            }
            if line.pass_qty:
                pass_specs.append({**base, "quantity": line.pass_qty})
            if line.fail_qty:
                fail_specs.append({**base, "quantity": line.fail_qty})

        auto_validate = self.config_id.auto_validate_transfers
        values = {}
        if pass_specs:
            pass_picking = create_stock_picking(
                self.env,
                picking_type=self.config_id.internal_picking_type_id,
                source_location=self.config_id.incoming_qc_location_id,
                destination_location=self.config_id.raw_material_location_id,
                lines=group_untracked_lines(pass_specs),
                origin=self.name,
                company=self.company_id,
                auto_validate=auto_validate,
            )
            values["pass_picking_id"] = pass_picking.id
        if fail_specs:
            fail_picking = create_stock_picking(
                self.env,
                picking_type=self.config_id.internal_picking_type_id,
                source_location=self.config_id.incoming_qc_location_id,
                destination_location=self.config_id.raw_rejected_location_id,
                lines=group_untracked_lines(fail_specs),
                origin=self.name,
                company=self.company_id,
                auto_validate=auto_validate,
            )
            values["fail_picking_id"] = fail_picking.id

        values["state"] = "done" if auto_validate else "transfer_pending"
        self.write(values)
        if self.state == "done":
            self.receipt_id.state = "qc_done"
        self.message_post(body=_("Incoming raw material QC was validated."))
        return True

    def action_check_transfers(self):
        self.ensure_one()
        pickings = self.pass_picking_id | self.fail_picking_id
        if pickings and any(p.state != "done" for p in pickings):
            raise UserError(_("Validate all accepted/rejected stock transfers first."))
        self.state = "done"
        self.receipt_id.state = "qc_done"
        return True

    def action_open_pass_picking(self):
        self.ensure_one()
        return self._open_picking(self.pass_picking_id)

    def action_open_fail_picking(self):
        self.ensure_one()
        return self._open_picking(self.fail_picking_id)

    def _open_picking(self, picking):
        if not picking:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": picking.id,
        }


class MobileRawQCLine(models.Model):
    _name = "mobile.raw.qc.line"
    _description = "Incoming Raw Material QC Line"
    _check_company_auto = True
    _order = "id"

    qc_id = fields.Many2one("mobile.raw.qc", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="qc_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    uom_id = fields.Many2one("uom.uom", required=True)
    lot_id = fields.Many2one("stock.lot", string="Lot/Serial", domain="[('product_id', '=', product_id)]", check_company=True)
    received_qty = fields.Float(required=True, digits="Product Unit", readonly=True)
    pass_qty = fields.Float(string="Accepted Qty", digits="Product Unit")
    fail_qty = fields.Float(string="Rejected Qty", digits="Product Unit")
    result = fields.Selection([
        ("pass", "Pass"),
        ("partial", "Partial"),
        ("fail", "Fail"),
    ], compute="_compute_result", store=True)
    test_notes = fields.Char()

    @api.depends("received_qty", "pass_qty", "fail_qty")
    def _compute_result(self):
        for line in self:
            if line.fail_qty and line.pass_qty:
                line.result = "partial"
            elif line.fail_qty and not line.pass_qty:
                line.result = "fail"
            elif line.pass_qty:
                line.result = "pass"
            else:
                line.result = False

    @api.onchange("received_qty")
    def _onchange_received_qty(self):
        if self.received_qty and not self.pass_qty and not self.fail_qty:
            self.pass_qty = self.received_qty

    def _check_result_quantities(self):
        self.ensure_one()
        precision = self.product_id.uom_id.rounding
        total = self.pass_qty + self.fail_qty
        if self.product_id.uom_id.compare(total, self.received_qty) != 0:
            raise ValidationError(_(
                "Accepted + Rejected quantity must equal received quantity for %s.",
                self.product_id.display_name,
            ))
        if self.product_id.tracking != "none" and not self.lot_id:
            raise ValidationError(_("Lot/Serial is required for tracked raw material %s.", self.product_id.display_name))
        if self.product_id.tracking == "serial" and self.received_qty != 1:
            raise ValidationError(_("Each serial-tracked raw material QC line must contain one unit."))
