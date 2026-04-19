from odoo import models, fields

class NewspaperCustomerType(models.Model):
    _name = 'newspaper.customer.type'
    _description = 'Newspaper Customer Type'

    name = fields.Char(string='Type Name', required=True)
    description = fields.Text(string='Description')
