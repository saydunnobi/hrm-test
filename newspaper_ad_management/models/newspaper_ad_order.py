from odoo import models, fields, api
from dateutil.relativedelta import relativedelta

class NewspaperAdOrder(models.Model):
    _name = 'newspaper.ad.order'
    _description = 'Newspaper Ad Order'

    name = fields.Char(string='Order Reference', required=True, copy=False, readonly=True, default='New')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True)
    customer_type_id = fields.Many2one(related='partner_id.newspaper_customer_type_id', string='Customer Type', store=True)
    
    page_id = fields.Many2one('newspaper.page', string='Page', required=True)
    position_id = fields.Many2one('newspaper.ad.position', string='Position', required=True, domain="[('page_id', '=', page_id)]")
    size_id = fields.Many2one('newspaper.ad.size', string='Ad Size', required=True)
    
    is_custom_size = fields.Boolean(related='size_id.is_custom')
    custom_width = fields.Float(string='Custom Width (cm)')
    custom_height = fields.Float(string='Custom Height (cm)')
    
    start_date = fields.Date(string='Start Date', required=True, default=fields.Date.context_today)
    end_date = fields.Date(string='End Date', required=True, default=fields.Date.context_today)
    duration_days = fields.Integer(string='Duration (Days)', compute='_compute_duration', store=True)
    
    payment_term_id = fields.Many2one('account.payment.term', string='Payment Terms')
    
    # Add an income account for journal entries based on user request
    income_account_id = fields.Many2one('account.account', string='Income Account', domain="[('account_type', '=', 'income')]")
    
    base_price = fields.Float(string='Calculated Price', compute='_compute_price', store=True)
    total_price = fields.Float(string='Total Price', compute='_compute_price', store=True)
    
    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirmed', 'Confirmed'),
        ('invoiced', 'Invoiced'),
        ('cancel', 'Cancelled'),
    ], string='Status', default='draft')
    
    invoice_id = fields.Many2one('account.move', string='Invoice', readonly=True)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', 'New') == 'New':
                vals['name'] = self.env['ir.sequence'].next_by_code('newspaper.ad.order') or 'New'
        return super(NewspaperAdOrder, self).create(vals_list)

    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for record in self:
            if record.start_date and record.end_date:
                delta = record.end_date - record.start_date
                record.duration_days = delta.days + 1
            else:
                record.duration_days = 0

    @api.depends('customer_type_id', 'position_id', 'size_id', 'duration_days')
    def _compute_price(self):
        for record in self:
            price = 0.0
            total = 0.0
            if record.position_id and record.size_id:
                domain = [
                    ('position_id', '=', record.position_id.id),
                    ('size_id', '=', record.size_id.id)
                ]
                if record.customer_type_id:
                    domain.append(('customer_type_id', '=', record.customer_type_id.id))
                
                pricelist = self.env['newspaper.ad.pricelist'].search(domain, limit=1)
                
                if pricelist:
                    price = pricelist.base_price
                    total = price
                    if record.duration_days > 1:
                        total += (record.duration_days - 1) * pricelist.extra_price_per_day
                else:
                    price = record.position_id.base_price or 0.0
                    total = price * record.duration_days
            
            record.base_price = price
            record.total_price = total

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_create_invoice(self):
        for record in self:
            if not record.partner_id:
                continue
            
            invoice_vals = {
                'move_type': 'out_invoice',
                'partner_id': record.partner_id.id,
                'invoice_payment_term_id': record.payment_term_id.id,
                'invoice_line_ids': [(0, 0, {
                    'name': f"Newspaper Ad Order: {record.name}",
                    'quantity': 1,
                    'price_unit': record.total_price,
                    'account_id': record.income_account_id.id if record.income_account_id else False,
                })],
            }
            invoice = self.env['account.move'].create(invoice_vals)
            record.write({
                'invoice_id': invoice.id,
                'state': 'invoiced'
            })
