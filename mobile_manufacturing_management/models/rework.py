from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .utils import create_stock_picking


class MobileReworkOrder(models.Model):
    _name = "mobile.rework.order"
    _description = "Mobile Manufacturing Rework Order"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    device_id = fields.Many2one("mobile.device", ondelete="restrict", check_company=True, tracking=True)
    production_id = fields.Many2one("mrp.production", required=True, ondelete="restrict", check_company=True, tracking=True)
    production_qc_id = fields.Many2one("mobile.production.qc", ondelete="set null", check_company=True)
    failed_qc_id = fields.Many2one("mobile.device.qc", ondelete="set null", check_company=True)
    company_id = fields.Many2one(related="production_id.company_id", store=True, index=True)
    config_id = fields.Many2one(related="production_id.mobile_config_id", store=True)
    quantity = fields.Float(default=1.0, required=True, digits="Product Unit")
    return_stage = fields.Selection([
        ("production_qc", "Pre-IMEI Production QC"),
        ("qc1", "QC Stage 1"),
        ("qc2", "QC Stage 2"),
    ], required=True, tracking=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("in_progress", "In Progress"),
        ("done", "Completed / Returned"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)
    assigned_to_id = fields.Many2one("res.users", tracking=True)
    start_time = fields.Datetime()
    end_time = fields.Datetime()
    failure_category = fields.Selection([
        ("hardware", "Hardware"),
        ("software", "Software"),
        ("cosmetic", "Cosmetic"),
        ("imei", "IMEI / Identity"),
        ("accessory", "Accessory"),
        ("other", "Other"),
    ])
    failure_description = fields.Text(required=True)
    root_cause = fields.Text()
    repair_action = fields.Text()
    component_line_ids = fields.One2many("mobile.rework.component", "rework_id", string="Replaced / Used Components")
    component_consumption_picking_id = fields.Many2one(
        "stock.picking", string="Replacement Component Consumption", copy=False, check_company=True,
    )
    return_picking_id = fields.Many2one("stock.picking", copy=False, check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mobile.rework.order") or _("New")
        return super().create(vals_list)

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("Rework quantity must be greater than zero."))
            if rec.device_id and rec.quantity != 1:
                raise ValidationError(_("An IMEI device rework order must have quantity 1."))

    def action_start(self):
        for rec in self:
            if rec.state != "draft":
                continue
            rec.write({
                "state": "in_progress",
                "start_time": fields.Datetime.now(),
                "assigned_to_id": rec.assigned_to_id.id or self.env.user.id,
            })
        return True

    def action_complete(self):
        self.ensure_one()
        if self.state not in ("draft", "in_progress"):
            raise UserError(_("Only an open rework order can be completed."))
        if not self.root_cause or not self.repair_action:
            raise UserError(_("Root cause and repair action are required before completion."))

        values = {"state": "done", "end_time": fields.Datetime.now()}
        if self.component_line_ids and not self.component_consumption_picking_id:
            self.config_id._check_ready()
            production_location = self.config_id.warehouse_id._get_production_location()
            component_picking = create_stock_picking(
                self.env,
                picking_type=self.config_id.internal_picking_type_id,
                source_location=self.config_id.raw_material_location_id,
                destination_location=production_location,
                lines=[{
                    "product": line.product_id,
                    "quantity": line.quantity,
                    "uom": line.uom_id,
                    "lot": line.lot_id,
                    "description": _("Rework replacement component for %s", self.name),
                } for line in self.component_line_ids],
                origin=self.name,
                company=self.company_id,
                auto_validate=True,
            )
            values["component_consumption_picking_id"] = component_picking.id

        if self.device_id:
            self.config_id._check_ready()
            if self.return_stage == "qc1":
                destination = self.config_id.qc1_location_id
                device_state = "qc1_pending"
            elif self.return_stage == "qc2":
                destination = self.config_id.qc2_location_id
                device_state = "qc2_pending"
            else:
                raise UserError(_("A device rework cannot return to batch Production QC."))
            picking = create_stock_picking(
                self.env,
                picking_type=self.config_id.internal_picking_type_id,
                source_location=self.config_id.rework_location_id,
                destination_location=destination,
                lines=[{
                    "product": self.device_id.product_id,
                    "quantity": 1,
                    "uom": self.device_id.product_id.uom_id,
                    "lot": self.device_id.lot_id,
                }],
                origin=self.name,
                company=self.company_id,
                auto_validate=True,
            )
            values["return_picking_id"] = picking.id
            self.device_id.state = device_state
        elif self.production_qc_id:
            # The physical rework stays inside the open MO. Mark the rework done
            # first, then reset the QC record so inspectors can test again.
            self.write(values)
            self.production_qc_id.action_reset_for_retest()
            return True

        self.write(values)
        return True

    def action_open_component_picking(self):
        self.ensure_one()
        if not self.component_consumption_picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.component_consumption_picking_id.id,
        }

    def action_open_return_picking(self):
        self.ensure_one()
        if not self.return_picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.return_picking_id.id,
        }

    def action_cancel(self):
        self.state = "cancel"


class MobileReworkComponent(models.Model):
    _name = "mobile.rework.component"
    _description = "Mobile Rework Component"
    _check_company_auto = True

    rework_id = fields.Many2one("mobile.rework.order", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="rework_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    quantity = fields.Float(default=1.0, required=True, digits="Product Unit")
    uom_id = fields.Many2one("uom.uom", compute="_compute_uom", store=True, readonly=False, required=True)
    lot_id = fields.Many2one("stock.lot", domain="[('product_id', '=', product_id)]", check_company=True)
    note = fields.Char()

    @api.constrains("quantity", "product_id", "lot_id")
    def _check_component_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_("Replacement component quantity must be greater than zero."))
            if line.product_id.tracking != "none" and not line.lot_id:
                raise ValidationError(_("Lot/Serial is required for tracked replacement component %s.", line.product_id.display_name))
            if line.product_id.tracking == "serial" and line.quantity != 1:
                raise ValidationError(_("A serial-tracked replacement component line must contain one unit."))

    @api.depends("product_id")
    def _compute_uom(self):
        for line in self:
            line.uom_id = line.product_id.uom_id
