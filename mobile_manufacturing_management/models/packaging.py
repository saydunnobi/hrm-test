from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .utils import create_stock_picking


class MobilePackagingBatch(models.Model):
    _name = "mobile.packaging.batch"
    _description = "Mobile IMEI Box Packaging"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin", "barcodes.barcode_events_mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    config_id = fields.Many2one(
        "mobile.mfg.config",
        required=True,
        default=lambda self: self.env["mobile.mfg.config"].search([("company_id", "=", self.env.company.id)], limit=1),
        check_company=True,
    )
    company_id = fields.Many2one(related="config_id.company_id", store=True, index=True)
    product_id = fields.Many2one("product.product", string="Mobile Model", readonly=True, check_company=True)
    box_capacity = fields.Integer(default=lambda self: self._default_box_capacity(), required=True, tracking=True)
    allow_partial_box = fields.Boolean(string="Allow Partial Box")
    line_ids = fields.One2many("mobile.packaging.batch.line", "batch_id", string="Scanned IMEIs", copy=False)
    quantity = fields.Integer(compute="_compute_quantity", store=True)
    remaining_qty = fields.Integer(compute="_compute_quantity", store=True)
    state = fields.Selection([
        ("draft", "Scanning"),
        ("ready", "Box Full / Ready"),
        ("done", "Packed & Stored"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)
    package_id = fields.Many2one("stock.package", string="Odoo Package", copy=False, check_company=True)
    finished_picking_id = fields.Many2one("stock.picking", string="Finished Goods Transfer", copy=False, check_company=True)
    packed_by_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    packed_date = fields.Datetime()
    note = fields.Html()

    def _default_box_capacity(self):
        config = self.env["mobile.mfg.config"].search([("company_id", "=", self.env.company.id)], limit=1)
        return config.box_capacity or 20

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mobile.packaging.batch") or _("New")
        return super().create(vals_list)

    @api.depends("line_ids", "box_capacity")
    def _compute_quantity(self):
        for batch in self:
            batch.quantity = len(batch.line_ids)
            batch.remaining_qty = max(batch.box_capacity - batch.quantity, 0)

    @api.constrains("box_capacity")
    def _check_capacity(self):
        for batch in self:
            if batch.box_capacity <= 0:
                raise ValidationError(_("Box capacity must be greater than zero."))

    def on_barcode_scanned(self, barcode):
        self.ensure_one()
        if not self._origin.id:
            return {"warning": {"title": _("Save Box First"), "message": _("Save the packaging box before scanning IMEIs.")}}
        if self.state not in ("draft", "ready"):
            return {"warning": {"title": _("Box Closed"), "message": _("This packaging box is no longer open for scanning.")}}
        barcode = (barcode or "").strip()
        device = self.env["mobile.device"].search([
            "|", ("imei_1", "=", barcode), ("imei_2", "=", barcode),
        ], limit=1)
        if not device:
            return {"warning": {"title": _("IMEI Not Found"), "message": _("No mobile device matches barcode %s.", barcode)}}
        if device.state != "packaging_ready":
            return {"warning": {"title": _("Invalid Stage"), "message": _("IMEI %s has not passed QC Stage 2.", device.imei_1)}}
        existing_line = self.env["mobile.packaging.batch.line"].search([
            ("device_id", "=", device.id),
            ("batch_id", "!=", self.id),
        ], limit=1)
        if device.packaging_batch_id or device in self.line_ids.device_id or existing_line:
            return {"warning": {"title": _("Already Packed"), "message": _("IMEI %s is already assigned to a packaging box.", device.imei_1)}}
        if self.quantity >= self.box_capacity:
            self.state = "ready"
            return {"warning": {"title": _("Box Full"), "message": _("The box already contains %s devices.", self.box_capacity)}}
        if self.product_id and self.product_id != device.product_id:
            return {"warning": {"title": _("Wrong Model"), "message": _("A box can contain only one mobile model.")}}

        self.env["mobile.packaging.batch.line"].create({
            "batch_id": self.id,
            "device_id": device.id,
            "scan_sequence": self.quantity + 1,
        })
        if not self.product_id:
            self.product_id = device.product_id.id
        if self.quantity >= self.box_capacity:
            self.state = "ready"
        return {"warning": {"title": _("IMEI Added"), "message": _("%(imei)s added. %(qty)s/%(capacity)s scanned.", imei=device.imei_1, qty=self.quantity, capacity=self.box_capacity)}}

    def action_close_and_print(self):
        self.ensure_one()
        self.config_id._check_ready()
        if self.state == "done":
            return self.env.ref("mobile_manufacturing_management.action_report_mobile_packaging_imei").report_action(self)
        if not self.line_ids:
            raise UserError(_("Scan at least one IMEI before closing the box."))
        if self.quantity != self.box_capacity and not self.allow_partial_box:
            raise UserError(_("This box requires %(capacity)s devices; %(qty)s have been scanned.", capacity=self.box_capacity, qty=self.quantity))
        if any(line.device_id.state != "packaging_ready" for line in self.line_ids):
            raise UserError(_("One or more devices are no longer ready for packaging."))

        package = self.env["stock.package"].create({"name": self.name})
        transfer_lines = [{
            "product": line.device_id.product_id,
            "quantity": 1,
            "uom": line.device_id.product_id.uom_id,
            "lot": line.device_id.lot_id,
        } for line in self.line_ids]
        picking = create_stock_picking(
            self.env,
            picking_type=self.config_id.internal_picking_type_id,
            source_location=self.config_id.packaging_location_id,
            destination_location=self.config_id.finished_goods_location_id,
            lines=transfer_lines,
            origin=self.name,
            company=self.company_id,
            auto_validate=True,
            result_package=package,
        )
        self.write({
            "state": "done",
            "package_id": package.id,
            "finished_picking_id": picking.id,
            "packed_by_id": self.env.user.id,
            "packed_date": fields.Datetime.now(),
        })
        self.line_ids.device_id.write({
            "state": "packed",
            "packaging_batch_id": self.id,
            "package_id": package.id,
        })
        productions = self.line_ids.device_id.production_id
        for production in productions:
            if production.mobile_device_ids and all(device.state == "packed" for device in production.mobile_device_ids):
                production.mobile_flow_state = "finished"
        return self.env.ref("mobile_manufacturing_management.action_report_mobile_packaging_imei").report_action(self)

    def action_remove_last_scan(self):
        self.ensure_one()
        if self.state == "done":
            raise UserError(_("A completed packaging box cannot be edited."))
        last_line = self.line_ids.sorted("scan_sequence")[-1:]
        if last_line:
            last_line.unlink()
        self.state = "ready" if self.quantity >= self.box_capacity else "draft"
        if not self.line_ids:
            self.product_id = False
        return True

    @api.ondelete(at_uninstall=False)
    def _unlink_except_completed(self):
        if any(batch.state == "done" for batch in self):
            raise UserError(_("Completed packaging boxes cannot be deleted because they are linked to stock packages and transfers."))

    def action_open_finished_picking(self):
        self.ensure_one()
        if not self.finished_picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.finished_picking_id.id,
        }


class MobilePackagingBatchLine(models.Model):
    _name = "mobile.packaging.batch.line"
    _description = "Mobile Packaging IMEI Line"
    _check_company_auto = True
    _order = "scan_sequence, id"

    batch_id = fields.Many2one("mobile.packaging.batch", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="batch_id.company_id", store=True)
    scan_sequence = fields.Integer(required=True)
    device_id = fields.Many2one("mobile.device", required=True, ondelete="restrict", check_company=True)
    imei_1 = fields.Char(related="device_id.imei_1", store=True)
    imei_2 = fields.Char(related="device_id.imei_2", store=True)
    product_id = fields.Many2one(related="device_id.product_id", store=True)
    production_id = fields.Many2one(related="device_id.production_id", store=True)

    _device_unique = models.Constraint("UNIQUE(device_id)", "A device can be assigned to only one packaging box at a time.")

    @api.constrains("batch_id", "device_id")
    def _check_packaging_device(self):
        for line in self:
            if line.batch_id.state == "done" and line.device_id.packaging_batch_id != line.batch_id:
                raise ValidationError(_("A completed packaging box cannot receive new device lines."))
            if line.device_id.company_id != line.batch_id.company_id:
                raise ValidationError(_("The device and packaging box must belong to the same company."))
            if line.batch_id.product_id and line.device_id.product_id != line.batch_id.product_id:
                raise ValidationError(_("A packaging box can contain only one mobile model."))
