from odoo import models, fields

class NewspaperAdPricelist(models.Model):
    _name = 'newspaper.ad.pricelist'
    _description = 'Newspaper Ad Pricelist'

    name = fields.Char(string='Name', required=True)
    customer_type_id = fields.Many2one('newspaper.customer.type', string='Customer Type')
    position_id = fields.Many2one('newspaper.ad.position', string='Ad Position')
    size_id = fields.Many2one('newspaper.ad.size', string='Ad Size')
    base_price = fields.Float(string='Base Price', required=True)
    extra_price_per_day = fields.Float(string='Extra Price Per Day', help='Additional cost for each extra day running.')
