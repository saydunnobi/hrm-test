from odoo import models, fields

class NewspaperCategory(models.Model):
    _name = 'newspaper.category'
    _description = 'Newspaper Category'

    name = fields.Char(string='Category Name', required=True)
