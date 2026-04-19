from odoo import models, fields, api

class NewspaperAvailabilityWizard(models.TransientModel):
    _name = 'newspaper.availability.wizard'
    _description = 'Check Ad Availability'

    check_date = fields.Date(string='Date to Check', required=True, default=fields.Date.context_today)

    def action_check_availability(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Availability on {self.check_date}',
            'res_model': 'newspaper.ad.position',
            'view_mode': 'kanban,list',
            'context': {
                'preview_date': self.check_date,
                'search_default_group_page': 1,
            },
        }
