from odoo import models, fields

class NewspaperPage(models.Model):
    _name = 'newspaper.page'
    _description = 'Newspaper Page'

    name = fields.Char(string='Page Name', required=True)
    description = fields.Text(string='Description')
    position_ids = fields.One2many('newspaper.ad.position', 'page_id', string='Ad Positions')
