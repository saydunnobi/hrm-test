from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class MobileRawReceipt(models.Model):
    _name = "mobile.raw.receipt"
    _description = "Mobile Raw Material Receipt"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    partner_id = fields.Many2one("res.partner", string="Vendor", required=True, tracking=True)
    config_id = fields.Many2one(
        "mobile.mfg.config",
        required=True,
        default=lambda self: self.env["mobile.mfg.config"].search([("company_id", "=", self.env.company.id)], limit=1),
        check_company=True,
    )
    warehouse_id = fields.Many2one(related="config_id.warehouse_id", store=True)
    company_id = fields.Many2one(related="config_id.company_id", store=True, index=True)
    scheduled_date = fields.Datetime(default=fields.Datetime.now, required=True)
    line_ids = fields.One2many("mobile.raw.receipt.line", "receipt_id", string="Materials", copy=True)
    picking_id = fields.Many2one("stock.picking", string="Receipt Transfer", copy=False, check_company=True)
    raw_qc_id = fields.Many2one("mobile.raw.qc", string="Incoming QC", copy=False, check_company=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("waiting_receipt", "Waiting Receipt Validation"),
        ("received", "Received in QC Location"),
        ("qc_done", "Raw Material QC Done"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)
    notes = fields.Html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mobile.raw.receipt") or _("New")
        return super().create(vals_list)

    def action_create_receipt(self):
        self.ensure_one()
        self.config_id._check_ready()
        if not self.line_ids:
            raise UserError(_("Add at least one raw material line."))
        if self.picking_id:
            raise UserError(_("A receipt transfer already exists."))
        supplier_location = self.env.ref("stock.stock_location_suppliers")
        picking_type = self.warehouse_id.in_type_id
        if not picking_type:
            raise UserError(_("The warehouse has no receipt operation type."))

        picking = self.env["stock.picking"].create({
            "picking_type_id": picking_type.id,
            "partner_id": self.partner_id.id,
            "location_id": supplier_location.id,
            "location_dest_id": self.config_id.incoming_qc_location_id.id,
            "origin": self.name,
            "scheduled_date": self.scheduled_date,
            "company_id": self.company_id.id,
            "move_ids": [Command.create({
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.quantity,
                "product_uom": line.uom_id.id,
                "location_id": supplier_location.id,
                "location_dest_id": self.config_id.incoming_qc_location_id.id,
                "company_id": self.company_id.id,
            }) for line in self.line_ids],
        })
        picking.action_confirm()
        self.write({"picking_id": picking.id, "state": "waiting_receipt"})
        self.message_post(body=_("Receipt transfer %s was created.", picking._get_html_link()))
        return self.action_open_picking()

    def action_confirm_received(self):
        self.ensure_one()
        if not self.picking_id or self.picking_id.state != "done":
            raise UserError(_("Validate the Odoo receipt transfer before confirming receipt."))
        self.state = "received"
        if not self.raw_qc_id:
            qc = self.env["mobile.raw.qc"].create_from_receipt(self)
            self.raw_qc_id = qc.id
        return self.action_open_raw_qc()

    def action_open_picking(self):
        self.ensure_one()
        if not self.picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.picking_id.id,
        }

    def action_open_raw_qc(self):
        self.ensure_one()
        if not self.raw_qc_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "mobile.raw.qc",
            "view_mode": "form",
            "res_id": self.raw_qc_id.id,
        }

    def action_cancel(self):
        for rec in self:
            if rec.picking_id and rec.picking_id.state not in ("done", "cancel"):
                rec.picking_id.action_cancel()
            rec.state = "cancel"


class MobileRawReceiptLine(models.Model):
    _name = "mobile.raw.receipt.line"
    _description = "Mobile Raw Material Receipt Line"
    _check_company_auto = True
    _order = "id"

    receipt_id = fields.Many2one("mobile.raw.receipt", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="receipt_id.company_id", store=True)
    product_id = fields.Many2one(
        "product.product",
        required=True,
        check_company=True,
        domain="[('is_storable', '=', True)]",
    )
    quantity = fields.Float(required=True, default=1.0, digits="Product Unit")
    uom_id = fields.Many2one("uom.uom", required=True, compute="_compute_uom", store=True, readonly=False)
    note = fields.Char()

    @api.depends("product_id")
    def _compute_uom(self):
        for line in self:
            line.uom_id = line.product_id.uom_id

    @api.constrains("quantity")
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Receipt quantity must be greater than zero."))
