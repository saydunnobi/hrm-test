from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class MobileProductionQC(models.Model):
    _name = "mobile.production.qc"
    _description = "Pre-IMEI Production Quality Check"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    production_id = fields.Many2one("mrp.production", required=True, ondelete="restrict", check_company=True, tracking=True)
    product_id = fields.Many2one(related="production_id.product_id", store=True)
    company_id = fields.Many2one(related="production_id.company_id", store=True, index=True)
    tested_qty = fields.Float(required=True, digits="Product Unit", tracking=True)
    pass_qty = fields.Float(digits="Product Unit", tracking=True)
    fail_qty = fields.Float(digits="Product Unit", tracking=True)
    state = fields.Selection([
        ("draft", "Pending"),
        ("pass", "Passed"),
        ("fail", "Failed / Rework"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)
    inspector_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, tracking=True)
    inspection_date = fields.Datetime(default=fields.Datetime.now)
    checklist_power = fields.Boolean(string="Power / Boot Test")
    checklist_display = fields.Boolean(string="Display & Touch")
    checklist_camera = fields.Boolean(string="Camera")
    checklist_audio = fields.Boolean(string="Speaker & Microphone")
    checklist_connectivity = fields.Boolean(string="Network / Wi-Fi / Bluetooth")
    checklist_cosmetic = fields.Boolean(string="Physical / Cosmetic")
    notes = fields.Html()
    rework_id = fields.Many2one("mobile.rework.order", copy=False, check_company=True)

    _production_unique = models.Constraint("UNIQUE(production_id)", "Only one pre-IMEI production QC is allowed per Manufacturing Order.")

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mobile.production.qc") or _("New")
        return super().create(vals_list)

    @api.constrains("tested_qty", "pass_qty", "fail_qty")
    def _check_quantities(self):
        for qc in self:
            if qc.tested_qty <= 0:
                raise ValidationError(_("Tested quantity must be greater than zero."))
            if qc.pass_qty < 0 or qc.fail_qty < 0:
                raise ValidationError(_("Pass and fail quantities cannot be negative."))
            if qc.product_id and qc.product_id.uom_id.compare(qc.pass_qty + qc.fail_qty, qc.tested_qty) != 0:
                raise ValidationError(_("Pass quantity + fail quantity must equal tested quantity."))

    def _check_mandatory_checklist(self):
        self.ensure_one()
        checklist = [
            self.checklist_power,
            self.checklist_display,
            self.checklist_camera,
            self.checklist_audio,
            self.checklist_connectivity,
            self.checklist_cosmetic,
        ]
        if not all(checklist):
            raise UserError(_("Complete all production QC checklist items before passing the batch."))

    def action_pass(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only a pending Production QC can be passed."))
        self._check_quantities()
        self._check_mandatory_checklist()
        if self.fail_qty:
            raise UserError(_("Fail quantity must be zero to pass production QC."))
        if self.production_id.product_uom_id.compare(self.pass_qty, self.production_id.product_qty) != 0:
            raise UserError(_("The full Manufacturing Order quantity must pass before IMEI assignment."))
        self.write({"state": "pass", "inspection_date": fields.Datetime.now()})
        self.production_id.mobile_flow_state = "imei_ready"
        self.message_post(body=_("Production QC passed. IMEI generation/import is now allowed."))
        return True

    def action_fail(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("Only a pending Production QC can be failed."))
        self._check_quantities()
        if self.fail_qty <= 0:
            raise UserError(_("Enter a failed quantity before creating rework."))
        if not self.rework_id or self.rework_id.state == "cancel":
            rework = self.env["mobile.rework.order"].create({
                "production_id": self.production_id.id,
                "production_qc_id": self.id,
                "quantity": self.fail_qty,
                "return_stage": "production_qc",
                "failure_description": self.notes or _("Production batch failed pre-IMEI QC."),
            })
            self.rework_id = rework.id
        self.state = "fail"
        self.production_id.mobile_flow_state = "production_qc"
        return self.action_open_rework()

    def action_open_rework(self):
        self.ensure_one()
        if not self.rework_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "mobile.rework.order",
            "view_mode": "form",
            "res_id": self.rework_id.id,
        }

    def action_reset_for_retest(self):
        self.ensure_one()
        if self.rework_id and self.rework_id.state != "done":
            raise UserError(_("Complete the rework order before resetting QC."))
        self.write({
            "state": "draft",
            "pass_qty": self.tested_qty,
            "fail_qty": 0,
            "checklist_power": False,
            "checklist_display": False,
            "checklist_camera": False,
            "checklist_audio": False,
            "checklist_connectivity": False,
            "checklist_cosmetic": False,
        })
        return True
