from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .utils import create_stock_picking


class MobileDeviceQC(models.Model):
    _name = "mobile.device.qc"
    _description = "IMEI Device Quality Check"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    device_id = fields.Many2one("mobile.device", required=True, ondelete="restrict", check_company=True, tracking=True)
    imei_1 = fields.Char(related="device_id.imei_1", store=True, index=True)
    imei_2 = fields.Char(related="device_id.imei_2", store=True)
    product_id = fields.Many2one(related="device_id.product_id", store=True)
    production_id = fields.Many2one(related="device_id.production_id", store=True)
    company_id = fields.Many2one(related="device_id.company_id", store=True, index=True)
    config_id = fields.Many2one(related="production_id.mobile_config_id", store=True)
    stage = fields.Selection([
        ("qc1", "QC Stage 1"),
        ("qc2", "QC Stage 2"),
    ], required=True, tracking=True, index=True)
    state = fields.Selection([
        ("draft", "Pending"),
        ("pass", "Passed"),
        ("fail", "Failed"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)
    inspector_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, tracking=True)
    scan_time = fields.Datetime(default=fields.Datetime.now)
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
    corrective_note = fields.Text()
    transfer_id = fields.Many2one("stock.picking", string="QC Movement", copy=False, check_company=True)
    rework_id = fields.Many2one("mobile.rework.order", copy=False, check_company=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mobile.device.qc") or _("New")
        return super().create(vals_list)

    def _check_expected_state(self):
        self.ensure_one()
        expected = "qc1_pending" if self.stage == "qc1" else "qc2_pending"
        if self.device_id.state != expected:
            raise UserError(_(
                "Device %(imei)s is currently in '%(state)s' and cannot be processed at %(stage)s.",
                imei=self.device_id.imei_1,
                state=dict(self.device_id._fields["state"].selection).get(self.device_id.state),
                stage=dict(self._fields["stage"].selection).get(self.stage),
            ))

    def _check_pass_checklist(self):
        self.ensure_one()
        checks = [
            self.checklist_display_touch,
            self.checklist_camera,
            self.checklist_audio,
            self.checklist_charging,
            self.checklist_network,
            self.checklist_wifi_bt,
            self.checklist_software,
            self.checklist_imei,
            self.checklist_cosmetic,
        ]
        if not all(checks):
            raise UserError(_("All checklist items must be completed before passing the device."))

    def action_pass(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("This QC check has already been completed."))
        self._check_expected_state()
        self._check_pass_checklist()
        self.config_id._check_ready()

        if self.stage == "qc1":
            source = self.config_id.qc1_location_id
            destination = self.config_id.qc2_location_id
            next_state = "qc2_pending"
            flow_state = "qc2"
        else:
            source = self.config_id.qc2_location_id
            destination = self.config_id.packaging_location_id
            next_state = "packaging_ready"
            flow_state = "packaging"

        picking = create_stock_picking(
            self.env,
            picking_type=self.config_id.internal_picking_type_id,
            source_location=source,
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
        self.write({
            "state": "pass",
            "transfer_id": picking.id,
            "scan_time": fields.Datetime.now(),
        })
        self.device_id.state = next_state
        self.production_id.mobile_flow_state = flow_state
        return True

    def action_fail(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("This QC check has already been completed."))
        self._check_expected_state()
        if not self.failure_category or not self.failure_description:
            raise UserError(_("Failure category and failure description are required."))
        self.config_id._check_ready()

        source = self.config_id.qc1_location_id if self.stage == "qc1" else self.config_id.qc2_location_id
        return_stage = self.stage
        picking = create_stock_picking(
            self.env,
            picking_type=self.config_id.internal_picking_type_id,
            source_location=source,
            destination_location=self.config_id.rework_location_id,
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
        rework = self.env["mobile.rework.order"].create({
            "device_id": self.device_id.id,
            "production_id": self.production_id.id,
            "failed_qc_id": self.id,
            "quantity": 1,
            "return_stage": return_stage,
            "failure_category": self.failure_category,
            "failure_description": self.failure_description,
        })
        self.write({
            "state": "fail",
            "transfer_id": picking.id,
            "rework_id": rework.id,
            "scan_time": fields.Datetime.now(),
        })
        self.device_id.state = "rework_qc1" if self.stage == "qc1" else "rework_qc2"
        return {
            "type": "ir.actions.act_window",
            "res_model": "mobile.rework.order",
            "view_mode": "form",
            "res_id": rework.id,
        }

    def action_open_transfer(self):
        self.ensure_one()
        if not self.transfer_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.transfer_id.id,
        }
