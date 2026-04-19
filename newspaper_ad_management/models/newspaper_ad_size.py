from odoo import models, fields

class NewspaperAdSize(models.Model):
    _name = 'newspaper.ad.size'
    _description = 'Newspaper Ad Size'

    name = fields.Char(string='Size Name', required=True)
    width = fields.Float(string='Width (cm)')
    height = fields.Float(string='Height (cm)')
    is_custom = fields.Boolean(string='Is Custom Size', default=False)
