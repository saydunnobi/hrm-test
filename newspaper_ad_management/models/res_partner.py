from odoo import models, fields

class ResPartner(models.Model):
    _inherit = 'res.partner'

    newspaper_customer_type_id = fields.Many2one('newspaper.customer.type', string='Newspaper Customer Type')
