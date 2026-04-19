from odoo import models, fields

class NewspaperSalesAchievement(models.Model):
    _name = 'newspaper.sales.achievement'
    _description = 'Sales Achievement'

    name = fields.Char(string='Achievement Name', required=True)
