from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError


class MobileMaterialRequisition(models.Model):
    _name = "mobile.material.requisition"
    _description = "Mobile Production Material Requisition"
    _check_company_auto = True
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    name = fields.Char(default=lambda self: _("New"), copy=False, readonly=True, index=True)
    config_id = fields.Many2one(
        "mobile.mfg.config",
        required=True,
        default=lambda self: self.env["mobile.mfg.config"].search([("company_id", "=", self.env.company.id)], limit=1),
        check_company=True,
    )
    company_id = fields.Many2one(related="config_id.company_id", store=True, index=True)
    requested_by_id = fields.Many2one("res.users", default=lambda self: self.env.user, required=True, tracking=True)
    approved_by_id = fields.Many2one("res.users", readonly=True, tracking=True)
    request_date = fields.Datetime(default=fields.Datetime.now, required=True)
    planned_start = fields.Datetime(default=fields.Datetime.now, required=True, tracking=True)
    product_id = fields.Many2one(
        "product.product",
        string="Mobile Product",
        required=True,
        check_company=True,
        domain="[('is_storable', '=', True)]",
        tracking=True,
    )
    product_tmpl_id = fields.Many2one(
        "product.template", related="product_id.product_tmpl_id", readonly=True,
    )
    bom_id = fields.Many2one(
        "mrp.bom",
        required=True,
        check_company=True,
        domain="['&', ('type', '=', 'normal'), '|', ('product_id', '=', product_id), ('product_tmpl_id', '=', product_tmpl_id)]",
        tracking=True,
    )
    quantity = fields.Float(default=1.0, required=True, digits="Product Unit", tracking=True)
    uom_id = fields.Many2one("uom.uom", compute="_compute_uom", store=True, readonly=False, required=True)
    line_ids = fields.One2many("mobile.material.requisition.line", "requisition_id", copy=True)
    material_picking_id = fields.Many2one("stock.picking", copy=False, check_company=True)
    production_id = fields.Many2one("mrp.production", string="Manufacturing Order", copy=False, check_company=True)
    state = fields.Selection([
        ("draft", "Draft"),
        ("submitted", "Submitted"),
        ("waiting_material", "Waiting Material Issue"),
        ("material_ready", "Material Ready"),
        ("in_production", "In Production"),
        ("done", "Completed"),
        ("cancel", "Cancelled"),
    ], default="draft", tracking=True, index=True)
    priority = fields.Selection([("0", "Normal"), ("1", "Urgent")], default="0")
    notes = fields.Html()

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", _("New")) == _("New"):
                vals["name"] = self.env["ir.sequence"].next_by_code("mobile.material.requisition") or _("New")
        return super().create(vals_list)

    @api.depends("product_id")
    def _compute_uom(self):
        for rec in self:
            rec.uom_id = rec.product_id.uom_id

    @api.onchange("product_id")
    def _onchange_product_id(self):
        if self.product_id:
            bom = self.env["mrp.bom"]._bom_find(self.product_id, company_id=self.company_id.id).get(self.product_id)
            self.bom_id = bom

    @api.constrains("quantity")
    def _check_quantity(self):
        for rec in self:
            if rec.quantity <= 0:
                raise ValidationError(_("Production quantity must be greater than zero."))

    def action_load_bom_materials(self):
        self.ensure_one()
        if self.state != "draft":
            raise UserError(_("BoM materials can only be loaded in Draft state."))
        if not self.bom_id:
            raise UserError(_("Select a Bill of Materials first."))
        factor = self.quantity / self.bom_id.product_qty
        commands = [Command.clear()]
        for bom_line in self.bom_id.bom_line_ids:
            # Direct BoM requirements are used here. Sub-assemblies should have
            # their own requisition/MO through standard multi-level BoM routes.
            qty = bom_line.product_uom_id._compute_quantity(
                bom_line.product_qty * factor,
                bom_line.product_id.uom_id,
                round=False,
            )
            commands.append(Command.create({
                "product_id": bom_line.product_id.id,
                "required_qty": qty,
                "uom_id": bom_line.product_id.uom_id.id,
            }))
        self.line_ids = commands
        return True

    def action_submit(self):
        for rec in self:
            if not rec.line_ids:
                rec.action_load_bom_materials()
            rec.state = "submitted"

    def action_approve_and_issue(self):
        self.ensure_one()
        self.config_id._check_ready()
        if self.state != "submitted":
            raise UserError(_("Only a submitted requisition can be approved."))
        if not self.line_ids:
            raise UserError(_("No material lines are available."))
        shortage_lines = self.line_ids.filtered(lambda line: line.shortage_qty > 0)
        if shortage_lines:
            details = "\n".join(
                _("- %(product)s: shortage %(qty)s %(uom)s",
                  product=line.product_id.display_name,
                  qty=line.shortage_qty,
                  uom=line.uom_id.name)
                for line in shortage_lines
            )
            raise UserError(_(
                "The Raw Material Store does not have enough stock. Replenish or receive the following items before approval:\n%(details)s",
                details=details,
            ))

        picking = self.env["stock.picking"].create({
            "picking_type_id": self.config_id.internal_picking_type_id.id,
            "location_id": self.config_id.raw_material_location_id.id,
            "location_dest_id": self.config_id.production_input_location_id.id,
            "origin": self.name,
            "company_id": self.company_id.id,
            "move_ids": [Command.create({
                "name": line.product_id.display_name,
                "product_id": line.product_id.id,
                "product_uom_qty": line.required_qty,
                "product_uom": line.uom_id.id,
                "location_id": self.config_id.raw_material_location_id.id,
                "location_dest_id": self.config_id.production_input_location_id.id,
                "company_id": self.company_id.id,
            }) for line in self.line_ids],
        })
        picking.action_confirm()
        picking.action_assign()
        self.write({
            "approved_by_id": self.env.user.id,
            "material_picking_id": picking.id,
            "state": "waiting_material",
        })
        self.message_post(body=_("Material issue transfer %s was created. Store personnel must scan/validate it.", picking._get_html_link()))
        return self.action_open_material_picking()

    def action_confirm_material_ready(self):
        self.ensure_one()
        if not self.material_picking_id or self.material_picking_id.state != "done":
            raise UserError(_("Validate the material issue transfer first."))
        self.state = "material_ready"
        return True

    def action_create_manufacturing_order(self):
        self.ensure_one()
        self.config_id._check_ready()
        if self.state == "waiting_material":
            self.action_confirm_material_ready()
        if self.state != "material_ready":
            raise UserError(_("Materials must be issued before creating the Manufacturing Order."))
        if self.production_id:
            raise UserError(_("A Manufacturing Order already exists."))
        if self.product_id.tracking != "serial":
            raise UserError(_("The mobile finished product must be tracked by unique serial number for IMEI control."))

        production = self.env["mrp.production"].create({
            "product_id": self.product_id.id,
            "product_qty": self.quantity,
            "product_uom_id": self.uom_id.id,
            "bom_id": self.bom_id.id,
            "picking_type_id": self.config_id.manufacturing_picking_type_id.id,
            "location_src_id": self.config_id.production_input_location_id.id,
            "location_dest_id": self.config_id.qc1_location_id.id,
            "date_start": self.planned_start,
            "origin": self.name,
            "priority": self.priority,
            "company_id": self.company_id.id,
            "mobile_requisition_id": self.id,
            "is_mobile_manufacturing": True,
        })
        production.action_confirm()
        self.write({"production_id": production.id, "state": "in_production"})
        self.message_post(body=_("Manufacturing Order %s was created.", production._get_html_link()))
        return self.action_open_production()

    def action_open_material_picking(self):
        self.ensure_one()
        if not self.material_picking_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "stock.picking",
            "view_mode": "form",
            "res_id": self.material_picking_id.id,
        }

    def action_open_production(self):
        self.ensure_one()
        if not self.production_id:
            return False
        return {
            "type": "ir.actions.act_window",
            "res_model": "mrp.production",
            "view_mode": "form",
            "res_id": self.production_id.id,
        }

    def action_cancel(self):
        for rec in self:
            if rec.production_id and rec.production_id.state not in ("done", "cancel"):
                rec.production_id.action_cancel()
            if rec.material_picking_id and rec.material_picking_id.state not in ("done", "cancel"):
                rec.material_picking_id.action_cancel()
            rec.state = "cancel"


class MobileMaterialRequisitionLine(models.Model):
    _name = "mobile.material.requisition.line"
    _description = "Mobile Production Material Requisition Line"
    _check_company_auto = True
    _order = "id"

    requisition_id = fields.Many2one("mobile.material.requisition", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="requisition_id.company_id", store=True)
    product_id = fields.Many2one("product.product", required=True, check_company=True)
    required_qty = fields.Float(required=True, digits="Product Unit")
    uom_id = fields.Many2one("uom.uom", required=True)
    available_qty = fields.Float(compute="_compute_available_qty", digits="Product Unit")
    shortage_qty = fields.Float(compute="_compute_available_qty", digits="Product Unit")

    @api.depends("product_id", "required_qty", "requisition_id.config_id.raw_material_location_id")
    def _compute_available_qty(self):
        Quant = self.env["stock.quant"]
        for line in self:
            location = line.requisition_id.config_id.raw_material_location_id
            if line.product_id and location:
                available = Quant._get_available_quantity(line.product_id, location, strict=False)
            else:
                available = 0.0
            line.available_qty = available
            line.shortage_qty = max(line.required_qty - available, 0.0)
