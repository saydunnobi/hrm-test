from odoo import api, fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ── Restricted Login/Check-in Time Range ──────────────────────────────────
    attendance_restrict_login = fields.Boolean(
        string='Restrict Login / Check-in Time',
        config_parameter='hr_attendance_control_ovi.restrict_login',
        help='If enabled, employees cannot login to Odoo or check-in during the restricted time range.',
    )
    attendance_restrict_from = fields.Float(
        string='Restrict From (hour)',
        config_parameter='hr_attendance_control_ovi.restrict_from',
        help='Start of restricted period (24-hour format, e.g. 22.5 = 22:30)',
        default=0.0,
    )
    attendance_restrict_to = fields.Float(
        string='Restrict To (hour)',
        config_parameter='hr_attendance_control_ovi.restrict_to',
        help='End of restricted period (24-hour format, e.g. 6.0 = 06:00)',
        default=0.0,
    )

    # ── Force Checkout Settings ───────────────────────────────────────────────
    attendance_force_checkout = fields.Boolean(
        string='Force Checkout on New Check-in',
        config_parameter='hr_attendance_control_ovi.force_checkout',
        default=True,
        help='Automatically check-out any open attendance before recording a new check-in.',
    )
    attendance_checkout_previous_days = fields.Boolean(
        string='Auto Checkout Previous Unclosed Attendances',
        config_parameter='hr_attendance_control_ovi.checkout_previous_days',
        default=True,
        help='When the daily cron runs, also close attendances left open from previous days.',
    )
