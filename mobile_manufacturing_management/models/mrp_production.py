from odoo import _, fields, models
from odoo.exceptions import UserError


class MrpProduction(models.Model):
    _inherit = "mrp.production"

    is_mobile_manufacturing = fields.Boolean(default=False, copy=False, tracking=True)
    mobile_requisition_id = fields.Many2one(
        "mobile.material.requisition",
        string="Mobile Material Requisition",
        copy=False,
        check_company=True,
    )
    mobile_config_id = fields.Many2one(
        "mobile.mfg.config",
        related="mobile_requisition_id.config_id",
        store=True,
    )
    production_qc_id = fields.Many2one("mobile.production.qc", copy=False, check_company=True)
    mobile_device_ids = fields.One2many("mobile.device", "production_id", string="IMEI Devices")
    mobile_device_count = fields.Integer(compute="_compute_mobile_counts")
    mobile_rework_count = fields.Integer(compute="_compute_mobile_counts")
    mobile_flow_state = fields.Selection([
        ("not_mobile", "Not Mobile Flow"),
        ("production_qc", "Production QC Pending"),
        ("imei_ready", "Ready for IMEI"),
        ("imei_assigned", "IMEI Assigned"),
        ("qc1", "Device QC 1"),
        ("qc2", "Device QC 2"),
        ("packaging", "Packaging"),
        ("finished", "Finished Goods"),
    ], default="not_mobile", copy=False, tracking=True)

    def _compute_mobile_counts(self):
        Rework = self.env["mobile.rework.order"]
        for production in self:
            production.mobile_device_count = len(production.mobile_device_ids)
            production.mobile_rework_count = Rework.search_count([("production_id", "=", production.id)])

    def action_create_production_qc(self):
        self.ensure_one()
        if not self.is_mobile_manufacturing:
            raise UserError(_("This is not a Mobile Manufacturing Order."))
        if self.state in ("draft", "cancel", "done"):
            raise UserError(_("Production QC must be performed after production starts and before the MO is closed."))
        if not self.production_qc_id:
            qc = self.env["mobile.production.qc"].create({
                "production_id": self.id,
                "tested_qty": self.product_qty,
                "pass_qty": self.product_qty,
            })
            self.write({"production_qc_id": qc.id, "mobile_flow_state": "production_qc"})
        return self.action_open_production_qc()

    def action_open_production_qc(self):
        self.ensure_one()
        if not self.production_qc_id:
            return self.action_create_production_qc()
        return {
            "type": "ir.actions.act_window",
            "res_model": "mobile.production.qc",
            "view_mode": "form",
            "res_id": self.production_qc_id.id,
        }

    def action_open_imei_wizard(self):
        self.ensure_one()
        if not self.is_mobile_manufacturing:
            raise UserError(_("This is not a Mobile Manufacturing Order."))
        if not self.production_qc_id or self.production_qc_id.state != "pass":
            raise UserError(_("Production QC must pass before assigning IMEIs."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Generate / Import IMEI"),
            "res_model": "mobile.imei.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {"default_production_id": self.id},
        }

    def action_open_mobile_devices(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("IMEI Devices"),
            "res_model": "mobile.device",
            "view_mode": "list,form",
            "domain": [("production_id", "=", self.id)],
            "context": {"default_production_id": self.id},
        }

    def action_open_mobile_reworks(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": _("Production Reworks"),
            "res_model": "mobile.rework.order",
            "view_mode": "list,form",
            "domain": [("production_id", "=", self.id)],
        }


    def _mobile_finalize_done_state(self):
        for production in self.filtered(lambda mo: mo.is_mobile_manufacturing and mo.state == "done"):
            production.mobile_device_ids.filtered(lambda device: device.state == "awaiting_mo").write({"state": "qc1_pending"})
            if production.mobile_flow_state not in ("qc1", "qc2", "packaging", "finished"):
                production.mobile_flow_state = "qc1"
            if production.mobile_requisition_id and production.mobile_requisition_id.state != "done":
                production.mobile_requisition_id.state = "done"

    def write(self, vals):
        result = super().write(vals)
        if vals.get("state") == "done":
            self._mobile_finalize_done_state()
        return result

    def action_cancel(self):
        assigned = self.filtered(lambda mo: mo.is_mobile_manufacturing and mo.mobile_device_ids)
        if assigned:
            raise UserError(_(
                "Remove the assigned IMEI/device records before cancelling these Mobile Manufacturing Orders: %s",
                ", ".join(assigned.mapped("display_name")),
            ))
        return super().action_cancel()

    def button_mark_done(self):
        mobile_orders = self.filtered("is_mobile_manufacturing")
        for production in mobile_orders:
            if not production.production_qc_id or production.production_qc_id.state != "pass":
                raise UserError(_("Production QC must pass before closing Mobile Manufacturing Order %s.", production.display_name))
            if production.product_tracking == "serial":
                expected = int(round(production.product_qty))
                if production.product_uom_id.compare(production.product_qty, expected) != 0:
                    raise UserError(_(
                        "Mobile Manufacturing Order %(mo)s must have a whole-number quantity for unique IMEI tracking.",
                        mo=production.display_name,
                    ))
                if len(production.lot_producing_ids) != expected:
                    raise UserError(_(
                        "Assign exactly %(expected)s IMEI serial numbers before closing %(mo)s. Currently assigned: %(actual)s.",
                        expected=expected,
                        mo=production.display_name,
                        actual=len(production.lot_producing_ids),
                    ))
        result = super().button_mark_done()
        mobile_orders._mobile_finalize_done_state()
        return result
