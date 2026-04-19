from odoo import models, fields, api

class NewspaperAdPosition(models.Model):
    _name = 'newspaper.ad.position'
    _description = 'Newspaper Ad Position'

    name = fields.Char(string='Position Name', required=True)
    page_id = fields.Many2one('newspaper.page', string='Page')
    base_price = fields.Float(string='Default Base Price')

    booking_status = fields.Selection([
        ('available', 'Available'),
        ('booked', 'Booked')
    ], string='Status', compute='_compute_booking_status')
    
    current_ad_order_id = fields.Many2one('newspaper.ad.order', string='Current Ad', compute='_compute_booking_status')

    @api.depends_context('preview_date')
    def _compute_booking_status(self):
        for position in self:
            preview_date = self.env.context.get('preview_date', fields.Date.context_today(self))
            order = self.env['newspaper.ad.order'].search([
                ('position_id', '=', position.id),
                ('start_date', '<=', preview_date),
                ('end_date', '>=', preview_date),
                ('state', 'in', ['confirmed', 'invoiced'])
            ], limit=1)
            
            if order:
                position.booking_status = 'booked'
                position.current_ad_order_id = order.id
            else:
                position.booking_status = 'available'
                position.current_ad_order_id = False
