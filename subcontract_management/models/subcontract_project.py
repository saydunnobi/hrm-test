from odoo import api, fields, models

class SubcontractProject(models.Model):
    _name = 'subcontract.project'
    _description = 'Subcontract Project'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Project Name', required=True, tracking=True)
    partner_id = fields.Many2one('res.partner', string='Client', required=True, tracking=True)
    task_ids = fields.One2many('subcontract.task', 'project_id', string='Tasks')
    
    project_value = fields.Float(string='Total Income (Value)', required=True, default=0.0, tracking=True)
    total_cost = fields.Float(string='Total Cost', compute='_compute_cost_and_profit', store=True)
    net_profit = fields.Float(string='Net Profit', compute='_compute_cost_and_profit', store=True)
    profit_margin = fields.Float(string='Profit Margin (%)', compute='_compute_cost_and_profit', store=True)
    
    completion_percent = fields.Float(string='Completion (%)', compute='_compute_completion', store=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('done', 'Done'),
        ('cancelled', 'Cancelled')
    ], string='Status', default='draft', tracking=True)

    @api.depends('task_ids.vendor_cost', 'task_ids.actual_qty')
    def _compute_cost_and_profit(self):
        for project in self:
            total_cost = sum(task.vendor_cost * task.actual_qty for task in project.task_ids if task.assigned_type == 'vendor')
            # Assuming internal tasks also have some cost, but for simplicity we rely on vendor cost here.
            # If internal tasks have cost: total_cost += sum(internal_task_costs)
            
            project.total_cost = total_cost
            project.net_profit = project.project_value - total_cost
            if project.project_value > 0:
                project.profit_margin = (project.net_profit / project.project_value) * 100.0
            else:
                project.profit_margin = 0.0

    @api.depends('task_ids.planned_qty', 'task_ids.actual_qty')
    def _compute_completion(self):
        for project in self:
            total_planned = sum(task.planned_qty for task in project.task_ids)
            total_actual = sum(task.actual_qty for task in project.task_ids)
            if total_planned > 0:
                project.completion_percent = (total_actual / total_planned) * 100.0
            else:
                project.completion_percent = 0.0
