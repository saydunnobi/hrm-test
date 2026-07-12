import re

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class MobileManufacturingConfig(models.Model):
    _name = "mobile.mfg.config"
    _description = "Mobile Manufacturing Configuration"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "warehouse_id"

    company_id = fields.Many2one(
        "res.company",
        required=True,
        default=lambda self: self.env.company,
        index=True,
    )
    warehouse_id = fields.Many2one(
        "stock.warehouse",
        required=True,
        check_company=True,
        domain="[('company_id', '=', company_id)]",
        tracking=True,
    )
    internal_picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Internal Transfer Operation",
        domain="[('code', '=', 'internal'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    manufacturing_picking_type_id = fields.Many2one(
        "stock.picking.type",
        string="Manufacturing Operation",
        domain="[('code', '=', 'mrp_operation'), ('company_id', '=', company_id)]",
        check_company=True,
    )
    incoming_qc_location_id = fields.Many2one("stock.location", string="Incoming Raw Material QC", check_company=True)
    raw_material_location_id = fields.Many2one("stock.location", string="Raw Material Store", check_company=True)
    raw_rejected_location_id = fields.Many2one("stock.location", string="Raw Material Rejected", check_company=True)
    production_input_location_id = fields.Many2one("stock.location", string="Production Input", check_company=True)
    qc1_location_id = fields.Many2one("stock.location", string="Device QC Stage 1", check_company=True)
    qc2_location_id = fields.Many2one("stock.location", string="Device QC Stage 2", check_company=True)
    rework_location_id = fields.Many2one("stock.location", string="Rework", check_company=True)
    packaging_location_id = fields.Many2one("stock.location", string="Packaging", check_company=True)
    finished_goods_location_id = fields.Many2one("stock.location", string="Finished Goods", check_company=True)
    device_rejected_location_id = fields.Many2one("stock.location", string="Device Rejected/Hold", check_company=True)

    box_capacity = fields.Integer(default=20, required=True, tracking=True)
    tac_prefix = fields.Char(
        string="IMEI TAC Prefix",
        size=8,
        default="35678912",
        help="First 8 digits used by the automatic IMEI generator. Replace with an officially allocated TAC in production.",
        tracking=True,
    )
    enforce_luhn = fields.Boolean(
        string="Validate IMEI Check Digit",
        default=True,
        help="When enabled, imported IMEIs must pass the standard Luhn check-digit validation.",
    )
    auto_validate_transfers = fields.Boolean(
        default=True,
        help="Automatically validate stock transfers created by QC, rework, and packaging actions.",
    )
    active = fields.Boolean(default=True)

    _company_warehouse_unique = models.Constraint(
        "UNIQUE(company_id, warehouse_id)",
        "Only one mobile manufacturing configuration is allowed per warehouse.",
    )

    @api.onchange("warehouse_id")
    def _onchange_warehouse_id(self):
        if self.warehouse_id:
            self.company_id = self.warehouse_id.company_id
            self.internal_picking_type_id = self.warehouse_id.int_type_id
            self.manufacturing_picking_type_id = self.warehouse_id.manu_type_id

    @api.constrains("box_capacity")
    def _check_box_capacity(self):
        for rec in self:
            if rec.box_capacity <= 0:
                raise ValidationError(_("Box capacity must be greater than zero."))

    @api.constrains("tac_prefix")
    def _check_tac_prefix(self):
        for rec in self:
            if rec.tac_prefix and not re.fullmatch(r"\d{8}", rec.tac_prefix):
                raise ValidationError(_("IMEI TAC Prefix must contain exactly 8 digits."))

    def action_setup_locations(self):
        self.ensure_one()
        warehouse = self.warehouse_id
        if not warehouse:
            raise UserError(_("Select a warehouse first."))

        parent = self.env["stock.location"].search([
            ("name", "=", "Mobile Manufacturing"),
            ("location_id", "=", warehouse.lot_stock_id.id),
            ("company_id", "=", self.company_id.id),
        ], limit=1)
        if not parent:
            parent = self.env["stock.location"].create({
                "name": "Mobile Manufacturing",
                "location_id": warehouse.lot_stock_id.id,
                "usage": "view",
                "company_id": self.company_id.id,
            })

        location_map = {
            "incoming_qc_location_id": "01 Incoming Raw Material QC",
            "raw_material_location_id": "02 Raw Material Store",
            "raw_rejected_location_id": "03 Raw Material Rejected",
            "production_input_location_id": "04 Production Input",
            "qc1_location_id": "05 Device QC Stage 1",
            "qc2_location_id": "06 Device QC Stage 2",
            "rework_location_id": "07 Rework",
            "packaging_location_id": "08 Packaging",
            "finished_goods_location_id": "09 Finished Goods",
            "device_rejected_location_id": "10 Device Rejected Hold",
        }
        values = {}
        for field_name, location_name in location_map.items():
            location = self[field_name]
            if not location:
                location = self.env["stock.location"].search([
                    ("name", "=", location_name),
                    ("location_id", "=", parent.id),
                    ("company_id", "=", self.company_id.id),
                ], limit=1)
            if not location:
                location = self.env["stock.location"].create({
                    "name": location_name,
                    "location_id": parent.id,
                    "usage": "internal",
                    "company_id": self.company_id.id,
                })
            values[field_name] = location.id

        values.update({
            "internal_picking_type_id": warehouse.int_type_id.id,
            "manufacturing_picking_type_id": warehouse.manu_type_id.id,
        })
        self.write(values)
        self.message_post(body=_("Mobile manufacturing locations were created or linked successfully."))
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": _("Configuration Ready"),
                "message": _("Locations and operation types are now configured."),
                "type": "success",
                "sticky": False,
            },
        }

    def _check_ready(self):
        self.ensure_one()
        required = [
            self.internal_picking_type_id,
            self.manufacturing_picking_type_id,
            self.incoming_qc_location_id,
            self.raw_material_location_id,
            self.raw_rejected_location_id,
            self.production_input_location_id,
            self.qc1_location_id,
            self.qc2_location_id,
            self.rework_location_id,
            self.packaging_location_id,
            self.finished_goods_location_id,
            self.device_rejected_location_id,
        ]
        if not all(required):
            raise UserError(_("Configuration is incomplete. Click 'Create/Link Locations' first."))
        return True
