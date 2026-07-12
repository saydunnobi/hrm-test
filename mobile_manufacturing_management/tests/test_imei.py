from odoo.tests.common import TransactionCase, tagged

from odoo.addons.mobile_manufacturing_management.models.stock_lot import imei_check_digit, imei_luhn_valid


@tagged("post_install", "-at_install")
class TestMobileIMEI(TransactionCase):
    def test_known_valid_imei(self):
        self.assertTrue(imei_luhn_valid("490154203237518"))
        self.assertFalse(imei_luhn_valid("490154203237519"))

    def test_check_digit(self):
        body = "49015420323751"
        self.assertEqual(imei_check_digit(body), "8")
        self.assertTrue(imei_luhn_valid(body + imei_check_digit(body)))
