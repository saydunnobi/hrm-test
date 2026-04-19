from odoo import models, fields

class NewspaperColor(models.Model):
    _name = 'newspaper.color'
    _description = 'Newspaper Color / BW'

    name = fields.Char(string='Color/BW Type', required=True)
