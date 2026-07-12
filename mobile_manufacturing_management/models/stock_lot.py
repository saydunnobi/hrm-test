import re

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError


def imei_luhn_valid(imei):
    if not re.fullmatch(r"\d{15}", imei or ""):
        return False
    total = 0
    # IMEI uses Luhn over all 15 digits; from the rightmost digit, double every
    # second digit (equivalent to doubling even indexes in the 14-digit body).
    for index, char in enumerate(imei):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            digit = digit // 10 + digit % 10
        total += digit
    return total % 10 == 0


def imei_check_digit(body14):
    if not re.fullmatch(r"\d{14}", body14 or ""):
        raise ValueError("IMEI body must be 14 digits")
    total = 0
    for index, char in enumerate(body14):
        digit = int(char)
        if index % 2 == 1:
            digit *= 2
            digit = digit // 10 + digit % 10
        total += digit
    return str((10 - (total % 10)) % 10)


class StockLot(models.Model):
    _inherit = "stock.lot"

    imei_2 = fields.Char(string="IMEI 2", index="btree", tracking=True)
    mobile_device_id = fields.One2many("mobile.device", "lot_id", string="Mobile Device")
    is_mobile_imei = fields.Boolean(compute="_compute_is_mobile_imei", store=True)

    @api.depends("name")
    def _compute_is_mobile_imei(self):
        for lot in self:
            lot.is_mobile_imei = bool(re.fullmatch(r"\d{15}", lot.name or ""))

    @api.constrains("name", "imei_2")
    def _check_imei_uniqueness(self):
        for lot in self:
            if re.fullmatch(r"\d{15}", lot.name or ""):
                duplicate_primary = self.search_count([
                    ("name", "=", lot.name),
                    ("id", "!=", lot.id),
                ])
                duplicate_as_secondary = self.search_count([
                    ("imei_2", "=", lot.name),
                    ("id", "!=", lot.id),
                ])
                if duplicate_primary or duplicate_as_secondary:
                    raise ValidationError(_("IMEI 1 %s is already used.", lot.name))
            if not lot.imei_2:
                continue
            if not re.fullmatch(r"\d{15}", lot.imei_2):
                raise ValidationError(_("IMEI 2 must contain exactly 15 digits."))
            duplicate = self.search_count([
                "|",
                ("imei_2", "=", lot.imei_2),
                ("name", "=", lot.imei_2),
                ("id", "!=", lot.id),
            ])
            if duplicate:
                raise ValidationError(_("IMEI 2 %s is already used.", lot.imei_2))
            if lot.imei_2 == lot.name:
                raise ValidationError(_("IMEI 1 and IMEI 2 cannot be the same."))
