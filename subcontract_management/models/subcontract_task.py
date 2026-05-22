from odoo import api, fields, models, _
from odoo.exceptions import ValidationError

class SubcontractTask(models.Model):
    _name = 'subcontract.task'
    _description = 'Subcontract Task'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Task Name', required=True, tracking=True)
    project_id = fields.Many2one('subcontract.project', string='Project', required=True, ondelete='cascade')
    assigned_type = fields.Selection([
        ('internal', 'Internal'),
        ('vendor', 'Vendor')
    ], string='Assigned Type', required=True, default='internal', tracking=True)
    
    vendor_id = fields.Many2one('res.partner', string='Assigned Vendor', domain=[('supplier_rank', '>', 0)], tracking=True)
    deadline = fields.Date(string='Deadline', tracking=True)
    priority = fields.Selection([
        ('0', 'Normal'),
        ('1', 'Low'),
        ('2', 'High'),
        ('3', 'Very High')
    ], string='Priority', default='0')

    state = fields.Selection([
        ('draft', 'Draft'),
        ('assigned', 'Assigned'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)
    
    # Work Tracking
    planned_qty = fields.Float(string='Planned Quantity', default=1.0)
    actual_qty = fields.Float(string='Actual Completed', default=0.0, tracking=True)
    good_qty = fields.Float(string='Good Quantity', default=0.0)
    rejected_qty = fields.Float(string='Rejected Quantity', default=0.0)
    
    start_time = fields.Datetime(string='Start Time')
    end_time = fields.Datetime(string='End Time')
    planned_time = fields.Float(string='Planned Time (Hours)', help="Total planned duration in hours")
    actual_time = fields.Float(string='Actual Time (Hours)', help="Total actual working hours")
    downtime = fields.Float(string='Downtime (Hours)', default=0.0)
    ideal_time_per_unit = fields.Float(string='Ideal Time per Unit (Hours)')
    
    # Costing
    vendor_cost = fields.Float(string='Cost per Unit', help="Cost per unit of work for the vendor")
    purchase_order_id = fields.Many2one('purchase.order', string='Purchase Order', readonly=True)
    
    # OEE Metrics
    oee_availability = fields.Float(string='Availability (%)', compute='_compute_oee', store=True)
    oee_performance = fields.Float(string='Performance (%)', compute='_compute_oee', store=True)
    oee_quality = fields.Float(string='Quality (%)', compute='_compute_oee', store=True)
    oee_total = fields.Float(string='OEE (%)', compute='_compute_oee', store=True)

    @api.depends('planned_time', 'downtime', 'actual_time', 'ideal_time_per_unit', 'actual_qty', 'good_qty')
    def _compute_oee(self):
        for task in self:
            # Availability = (Planned Time - Downtime) / Planned Time
            if task.planned_time > 0:
                avail = (task.planned_time - task.downtime) / task.planned_time
            else:
                avail = 0.0
            
            # Performance = (Ideal Time * Total Output) / Actual Time
            if task.actual_time > 0:
                perf = (task.ideal_time_per_unit * task.actual_qty) / task.actual_time
            else:
                perf = 0.0
                
            # Quality = Good Output / Total Output
            if task.actual_qty > 0:
                qual = task.good_qty / task.actual_qty
            else:
                qual = 0.0
                
            task.oee_availability = max(0.0, min(avail * 100, 100.0))
            task.oee_performance = max(0.0, min(perf * 100, 100.0))
            task.oee_quality = max(0.0, min(qual * 100, 100.0))
            task.oee_total = (avail * perf * qual) * 100.0

    def action_assign(self):
        for task in self:
            if task.assigned_type == 'vendor' and not task.vendor_id:
                raise ValidationError(_("You must select a vendor for vendor-assigned tasks."))
            task.state = 'assigned'
            # Trigger PO Creation if Vendor
            if task.assigned_type == 'vendor' and not task.purchase_order_id:
                task._create_purchase_order()

    def action_in_progress(self):
        self.write({'state': 'in_progress', 'start_time': fields.Datetime.now()})

    def action_done(self):
        self.write({'state': 'done', 'end_time': fields.Datetime.now()})

    def action_cancel(self):
        self.write({'state': 'cancelled'})

    def _create_purchase_order(self):
        """ Auto create purchase order for the assigned vendor """
        self.ensure_one()
        
        # We find or create a generic product for Subcontracting
        product = self.env['product.product'].search([('name', '=', 'Subcontracting Service')], limit=1)
        if not product:
            product = self.env['product.product'].sudo().create({
                'name': 'Subcontracting Service',
                'type': 'service',
                'purchase_ok': True,
                'sale_ok': False
            })

        PO = self.env['purchase.order'].sudo().create({
            'partner_id': self.vendor_id.id,
            'order_line': [
                (0, 0, {
                    'name': f"Subcontract Task: {self.name} (Project: {self.project_id.name})",
                    'product_id': product.id,
                    'product_qty': self.planned_qty,
                    'price_unit': self.vendor_cost,
                    'date_planned': self.deadline or fields.Datetime.now(),
                })
            ]
        })
        self.purchase_order_id = PO.id
        # Add message to task
        self.message_post(body=_("Purchase Order %s automatically created.") % PO.name)
