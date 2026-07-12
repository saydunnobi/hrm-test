import base64
import csv
import io
import re

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from odoo.addons.mobile_manufacturing_management.models.stock_lot import imei_check_digit, imei_luhn_valid


class MobileIMEIWizard(models.TransientModel):
    _name = "mobile.imei.wizard"
    _description = "Generate or Import Mobile IMEI Numbers"

    production_id = fields.Many2one("mrp.production", required=True, check_company=True)
    config_id = fields.Many2one(related="production_id.mobile_config_id")
    method = fields.Selection([
        ("auto", "Automatic IMEI Generation"),
        ("text", "Paste IMEI List"),
        ("csv", "Upload CSV"),
    ], default="auto", required=True)
    quantity = fields.Integer(compute="_compute_quantity", store=True, readonly=False, required=True)
    dual_sim = fields.Boolean(string="Generate / Import IMEI 2")
    tac_prefix = fields.Char(size=8, compute="_compute_tac", store=True, readonly=False)
    tac_prefix_2 = fields.Char(string="IMEI 2 TAC Prefix", size=8, compute="_compute_tac", store=True, readonly=False)
    serial_numbers = fields.Text(
        help="One device per line. For dual-SIM devices use: IMEI1,IMEI2",
    )
    csv_file = fields.Binary(string="CSV File")
    csv_filename = fields.Char()
    enforce_luhn = fields.Boolean(related="config_id.enforce_luhn")

    @api.depends("production_id", "production_id.mobile_device_ids")
    def _compute_quantity(self):
        for wizard in self:
            remaining = int(round(wizard.production_id.product_qty)) - len(wizard.production_id.mobile_device_ids)
            wizard.quantity = max(remaining, 0)

    @api.depends("config_id")
    def _compute_tac(self):
        for wizard in self:
            if not wizard.tac_prefix:
                wizard.tac_prefix = wizard.config_id.tac_prefix
            if not wizard.tac_prefix_2:
                wizard.tac_prefix_2 = wizard.config_id.tac_prefix

    @api.constrains("quantity")
    def _check_quantity(self):
        for wizard in self:
            if wizard.quantity <= 0:
                raise ValidationError(_("IMEI quantity must be greater than zero."))

    def action_generate_preview(self):
        self.ensure_one()
        if self.method != "auto":
            raise UserError(_("Preview generation is available only for Automatic method."))
        pairs = self._generate_auto_pairs(self.quantity)
        self.serial_numbers = "\n".join(
            f"{imei1},{imei2}" if imei2 else imei1
            for imei1, imei2 in pairs
        )
        self.method = "text"
        return {
            "type": "ir.actions.act_window",
            "res_model": self._name,
            "view_mode": "form",
            "res_id": self.id,
            "target": "new",
        }

    def action_apply(self):
        self.ensure_one()
        production = self.production_id
        if not production.is_mobile_manufacturing:
            raise UserError(_("The selected Manufacturing Order is not using the Mobile Manufacturing flow."))
        if not production.production_qc_id or production.production_qc_id.state != "pass":
            raise UserError(_("Production QC must pass before IMEI assignment."))
        if production.state in ("done", "cancel"):
            raise UserError(_("IMEIs cannot be assigned to a completed or cancelled Manufacturing Order."))
        if production.product_id.tracking != "serial":
            raise UserError(_("The finished mobile product must use unique serial number tracking."))

        if self.method == "auto":
            pairs = self._generate_auto_pairs(self.quantity)
        elif self.method == "text":
            pairs = self._parse_text(self.serial_numbers)
        else:
            pairs = self._parse_csv()

        if len(pairs) != self.quantity:
            raise UserError(_(
                "Expected %(expected)s device rows but received %(actual)s.",
                expected=self.quantity,
                actual=len(pairs),
            ))

        expected_total = int(round(production.product_qty))
        if production.product_uom_id.compare(production.product_qty, expected_total) != 0:
            raise UserError(_("The Manufacturing Order quantity must be a whole number for unique IMEI tracking."))
        if len(production.mobile_device_ids) + len(pairs) > expected_total:
            raise UserError(_("The total IMEI count cannot exceed the Manufacturing Order quantity."))

        self._validate_pairs(pairs)
        lots = self.env["stock.lot"]
        devices = self.env["mobile.device"]
        for imei1, imei2 in pairs:
            lot = self.env["stock.lot"].create({
                "name": imei1,
                "imei_2": imei2 or False,
                "product_id": production.product_id.id,
                "company_id": production.company_id.id,
            })
            lots |= lot
            devices |= self.env["mobile.device"].create({
                "imei_1": imei1,
                "imei_2": imei2 or False,
                "lot_id": lot.id,
                "production_id": production.id,
                "requisition_id": production.mobile_requisition_id.id,
                "company_id": production.company_id.id,
                "state": "awaiting_mo",
            })

        production.lot_producing_ids = [Command.link(lot.id) for lot in lots]
        production.qty_producing = len(production.lot_producing_ids)
        production.set_qty_producing()
        production.mobile_flow_state = "imei_assigned"
        production.message_post(body=_("%(count)s IMEI serial numbers were assigned.", count=len(lots)))
        return {
            "type": "ir.actions.act_window",
            "name": _("IMEI Devices"),
            "res_model": "mobile.device",
            "view_mode": "list,form",
            "domain": [("id", "in", devices.ids)],
        }

    def _generate_auto_pairs(self, quantity):
        self._validate_tac(self.tac_prefix, _("IMEI 1 TAC"))
        if self.dual_sim:
            self._validate_tac(self.tac_prefix_2, _("IMEI 2 TAC"))
        result = []
        for _index in range(quantity):
            imei1 = self._next_imei(self.tac_prefix)
            imei2 = self._next_imei(self.tac_prefix_2) if self.dual_sim else False
            result.append((imei1, imei2))
        return result

    def _next_imei(self, tac):
        serial = self.env["ir.sequence"].next_by_code("mobile.imei.serial")
        if not serial:
            raise UserError(_("IMEI serial sequence is not configured."))
        numeric = re.sub(r"\D", "", serial)
        if len(numeric) > 6:
            raise UserError(_("Automatic IMEI serial sequence exceeded six digits. Create a new TAC/sequence range."))
        body = f"{tac}{numeric.zfill(6)}"
        return body + imei_check_digit(body)

    def _parse_text(self, text):
        if not text:
            raise UserError(_("Paste at least one IMEI."))
        pairs = []
        for row_number, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            columns = [value.strip() for value in re.split(r"[,;\t]", line)]
            imei1 = columns[0] if columns else ""
            imei2 = columns[1] if len(columns) > 1 and columns[1] else False
            if self.dual_sim and not imei2:
                raise UserError(_("IMEI 2 is missing on line %s.", row_number))
            pairs.append((imei1, imei2))
        return pairs

    def _parse_csv(self):
        if not self.csv_file:
            raise UserError(_("Upload a CSV file."))
        try:
            content = base64.b64decode(self.csv_file).decode("utf-8-sig")
        except (ValueError, UnicodeDecodeError) as exc:
            raise UserError(_("The CSV file must be UTF-8 encoded.")) from exc
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)
        if not rows:
            raise UserError(_("The CSV file is empty."))
        first = [col.strip().lower() for col in rows[0]]
        has_header = any(col in ("imei", "imei1", "imei 1", "imei_1") for col in first)
        if has_header:
            header = first
            rows = rows[1:]
            idx1 = next((i for i, value in enumerate(header) if value in ("imei", "imei1", "imei 1", "imei_1")), 0)
            idx2 = next((i for i, value in enumerate(header) if value in ("imei2", "imei 2", "imei_2")), None)
        else:
            idx1, idx2 = 0, 1
        pairs = []
        for row_number, row in enumerate(rows, start=2 if has_header else 1):
            if not row or not any(str(value).strip() for value in row):
                continue
            imei1 = str(row[idx1]).strip() if len(row) > idx1 else ""
            imei2 = str(row[idx2]).strip() if idx2 is not None and len(row) > idx2 and str(row[idx2]).strip() else False
            if self.dual_sim and not imei2:
                raise UserError(_("IMEI 2 is missing in CSV row %s.", row_number))
            pairs.append((imei1, imei2))
        return pairs

    def _validate_pairs(self, pairs):
        flat = [value for pair in pairs for value in pair if value]
        if len(flat) != len(set(flat)):
            raise UserError(_("The submitted file/list contains duplicate IMEI numbers."))
        for imei1, imei2 in pairs:
            self._validate_imei(imei1, _("IMEI 1"))
            if imei2:
                self._validate_imei(imei2, _("IMEI 2"))
                if imei1 == imei2:
                    raise UserError(_("IMEI 1 and IMEI 2 cannot be identical."))
        existing_primary = self.env["stock.lot"].search([("name", "in", flat)], limit=1)
        existing_secondary = self.env["stock.lot"].search([("imei_2", "in", flat)], limit=1)
        existing_device = self.env["mobile.device"].search([
            "|", ("imei_1", "in", flat), ("imei_2", "in", flat),
        ], limit=1)
        existing = existing_primary.name or existing_secondary.imei_2 or existing_device.imei_1
        if existing:
            raise UserError(_("IMEI %s already exists in Odoo.", existing))

    def _validate_imei(self, imei, label):
        if not re.fullmatch(r"\d{15}", imei or ""):
            raise UserError(_("%(label)s '%(imei)s' must contain exactly 15 digits.", label=label, imei=imei))
        if self.enforce_luhn and not imei_luhn_valid(imei):
            raise UserError(_("%(label)s '%(imei)s' has an invalid Luhn check digit.", label=label, imei=imei))

    def _validate_tac(self, tac, label):
        if not re.fullmatch(r"\d{8}", tac or ""):
            raise UserError(_("%s must contain exactly 8 digits.", label))
