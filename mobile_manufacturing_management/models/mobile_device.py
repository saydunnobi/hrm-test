from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


class MobileDevice(models.Model):
    _name = "mobile.device"
    _description = "Manufactured Mobile Device"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "imei_1"
    _order = "id desc"

    imei_1 = fields.Char(required=True, index="btree", tracking=True)
    imei_2 = fields.Char(index="btree", tracking=True)
    lot_id = fields.Many2one("stock.lot", required=True, ondelete="restrict", check_company=True)
    product_id = fields.Many2one("product.product", related="lot_id.product_id", store=True, index=True)
    production_id = fields.Many2one("mrp.production", string="Manufacturing Order", check_company=True, tracking=True)
    requisition_id = fields.Many2one("mobile.material.requisition", string="Material Requisition", check_company=True)
    company_id = fields.Many2one("res.company", required=True, default=lambda self: self.env.company, index=True)
    current_location_id = fields.Many2one(
        "stock.location",
        related="lot_id.location_id",
        string="Current Stock Location",
        store=False,
    )
    state = fields.Selection([
        ("awaiting_mo", "Awaiting MO Completion"),
        ("qc1_pending", "QC Stage 1 Pending"),
        ("rework_qc1", "Rework - Return to QC 1"),
        ("qc2_pending", "QC Stage 2 Pending"),
        ("rework_qc2", "Rework - Return to QC 2"),
        ("packaging_ready", "Ready for Packaging"),
        ("packed", "Packed / Finished Goods"),
        ("rejected", "Rejected / Hold"),
    ], default="awaiting_mo", required=True, tracking=True, index=True)
    qc_check_ids = fields.One2many("mobile.device.qc", "device_id", string="QC History")
    rework_ids = fields.One2many("mobile.rework.order", "device_id", string="Rework History")
    rework_count = fields.Integer(compute="_compute_counts")
    qc_count = fields.Integer(compute="_compute_counts")
    packaging_batch_id = fields.Many2one("mobile.packaging.batch", tracking=True, check_company=True)
    package_id = fields.Many2one("stock.package", string="Odoo Package", check_company=True)
    active = fields.Boolean(default=True)

    _imei_1_unique = models.Constraint("UNIQUE(imei_1)", "IMEI 1 must be globally unique.")
    _imei_2_unique = models.Constraint("UNIQUE(imei_2)", "IMEI 2 must be globally unique.")
    _lot_unique = models.Constraint("UNIQUE(lot_id)", "A serial number can be linked to only one mobile device.")

    @api.depends("qc_check_ids", "rework_ids")
    def _compute_counts(self):
        for device in self:
            device.qc_count = len(device.qc_check_ids)
            device.rework_count = len(device.rework_ids)

    @api.constrains("imei_1", "imei_2", "lot_id")
    def _check_device_imei(self):
        for device in self:
            if device.imei_1 != device.lot_id.name:
                raise ValidationError(_("Device IMEI 1 must match the linked Odoo serial number."))
            if device.imei_2 and device.imei_1 == device.imei_2:
                raise ValidationError(_("IMEI 1 and IMEI 2 cannot be identical."))

    def action_open_qc_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("QC History"),
            "res_model": "mobile.device.qc",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }

    def action_open_rework_history(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Rework History"),
            "res_model": "mobile.rework.order",
            "view_mode": "list,form",
            "domain": [("device_id", "=", self.id)],
            "context": {"default_device_id": self.id},
        }
