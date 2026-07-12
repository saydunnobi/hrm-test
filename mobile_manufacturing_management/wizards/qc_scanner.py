from odoo import _, fields, models
from odoo.exceptions import UserError


class MobileQCScanner(models.TransientModel):
    _name = "mobile.qc.scanner"
    _description = "Barcode/IMEI QC Scanner"
    _inherit = "barcodes.barcode_events_mixin"

    stage = fields.Selection([
        ("qc1", "QC Stage 1"),
        ("qc2", "QC Stage 2"),
    ], default="qc1", required=True)
    device_id = fields.Many2one("mobile.device", readonly=True)
    imei_1 = fields.Char(related="device_id.imei_1", readonly=True)
    imei_2 = fields.Char(related="device_id.imei_2", readonly=True)
    product_id = fields.Many2one(related="device_id.product_id", readonly=True)
    current_state = fields.Selection(related="device_id.state", readonly=True)
    checklist_display_touch = fields.Boolean(string="Display & Touch")
    checklist_camera = fields.Boolean(string="Camera")
    checklist_audio = fields.Boolean(string="Audio")
    checklist_charging = fields.Boolean(string="Charging & Battery")
    checklist_network = fields.Boolean(string="SIM / Network")
    checklist_wifi_bt = fields.Boolean(string="Wi-Fi & Bluetooth")
    checklist_software = fields.Boolean(string="Software / Version")
    checklist_imei = fields.Boolean(string="IMEI Match")
    checklist_cosmetic = fields.Boolean(string="Cosmetic Condition")
    failure_category = fields.Selection([
        ("hardware", "Hardware"),
        ("software", "Software"),
        ("cosmetic", "Cosmetic"),
        ("imei", "IMEI / Identity"),
        ("accessory", "Accessory"),
        ("other", "Other"),
    ])
    failure_description = fields.Text()

    def on_barcode_scanned(self, barcode):
        self.ensure_one()
        barcode = (barcode or "").strip()
        device = self.env["mobile.device"].search([
            "|", ("imei_1", "=", barcode), ("imei_2", "=", barcode),
        ], limit=1)
        if not device:
            self.device_id = False
            return {"warning": {"title": _("IMEI Not Found"), "message": _("No device matches barcode %s.", barcode)}}
        expected = "qc1_pending" if self.stage == "qc1" else "qc2_pending"
        if device.state != expected:
            self.device_id = False
            return {"warning": {
                "title": _("Invalid QC Stage"),
                "message": _("IMEI %(imei)s is in %(state)s and cannot be scanned at this station.", imei=device.imei_1, state=device.state),
            }}
        self.device_id = device.id
        return {"warning": {"title": _("IMEI Loaded"), "message": _("Device %s is ready for inspection.", device.imei_1)}}

    def _prepare_qc_values(self):
        self.ensure_one()
        if not self.device_id:
            raise UserError(_("Scan an IMEI first."))
        return {
            "device_id": self.device_id.id,
            "stage": self.stage,
            "inspector_id": self.env.user.id,
            "checklist_display_touch": self.checklist_display_touch,
            "checklist_camera": self.checklist_camera,
            "checklist_audio": self.checklist_audio,
            "checklist_charging": self.checklist_charging,
            "checklist_network": self.checklist_network,
            "checklist_wifi_bt": self.checklist_wifi_bt,
            "checklist_software": self.checklist_software,
            "checklist_imei": self.checklist_imei,
            "checklist_cosmetic": self.checklist_cosmetic,
            "failure_category": self.failure_category,
            "failure_description": self.failure_description,
        }

    def action_pass_and_next(self):
        self.ensure_one()
        qc = self.env["mobile.device.qc"].create(self._prepare_qc_values())
        qc.action_pass()
        return self._reload_action(_("IMEI %s passed.", qc.imei_1))

    def action_fail_and_rework(self):
        self.ensure_one()
        qc = self.env["mobile.device.qc"].create(self._prepare_qc_values())
        return qc.action_fail()

    def _reload_action(self, message):
        return {
            "type": "ir.actions.act_window",
            "name": _("Barcode QC Scanner"),
            "res_model": self._name,
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_stage": self.stage,
                "mobile_notification": message,
            },
        }
