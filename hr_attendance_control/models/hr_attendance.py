import logging
from datetime import datetime, time, timedelta

import pytz

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError

_logger = logging.getLogger(__name__)


class HrAttendance(models.Model):
    _inherit = 'hr.attendance'

    # ─────────────────────────────────────────────────────────────────────────
    #  Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _get_param(self, key, default=False):
        """Read a system parameter with a default fallback."""
        ICP = self.env['ir.config_parameter'].sudo()
        val = ICP.get_param(key, default)
        if val in (False, None, ''):
            return default
        return val

    def _get_param_bool(self, key, default=False):
        val = self._get_param(key, default)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ('1', 'true', 'yes')

    def _get_param_float(self, key, default=0.0):
        try:
            return float(self._get_param(key, default))
        except (TypeError, ValueError):
            return default

    def _now_in_tz(self, tz_name=None):
        """Return current datetime in the company (or given) timezone."""
        if not tz_name:
            tz_name = self.env.company.partner_id.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        return datetime.now(tz)

    def _float_to_time(self, float_hour):
        """Convert float hour (e.g. 22.5) to (hour, minute) tuple."""
        hour = int(float_hour)
        minute = int(round((float_hour - hour) * 60))
        return hour, minute

    # ─────────────────────────────────────────────────────────────────────────
    #  Login / Check-in Time Restriction
    # ─────────────────────────────────────────────────────────────────────────

    def _check_restricted_time(self):
        """
        Raise AccessError if the current time falls within the restricted
        login/check-in window configured in Settings.
        Restriction can span midnight (e.g. 23:00 – 05:00).
        """
        if not self._get_param_bool('hr_attendance_control.restrict_login'):
            return

        restrict_from = self._get_param_float('hr_attendance_control.restrict_from')
        restrict_to = self._get_param_float('hr_attendance_control.restrict_to')

        if restrict_from == restrict_to:
            return  # No restriction configured

        now_local = self._now_in_tz()
        current_float = now_local.hour + now_local.minute / 60.0

        # Determine if current time is inside the restricted range
        if restrict_from < restrict_to:
            # Normal range: e.g. 09:00 – 17:00
            is_restricted = restrict_from <= current_float < restrict_to
        else:
            # Overnight range: e.g. 23:00 – 05:00
            is_restricted = current_float >= restrict_from or current_float < restrict_to

        if is_restricted:
            h_from, m_from = self._float_to_time(restrict_from)
            h_to, m_to = self._float_to_time(restrict_to)
            raise AccessError(
                _(
                    'Check-in is not allowed between %(from)s and %(to)s. '
                    'Please try again outside the restricted period.',
                    from='%02d:%02d' % (h_from, m_from),
                    to='%02d:%02d' % (h_to, m_to),
                )
            )

    # ─────────────────────────────────────────────────────────────────────────
    #  Force Checkout helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _force_checkout_open_attendances(self, employee, checkout_dt=None):
        """
        Close ALL open attendances for *employee*.
        If checkout_dt is None, use the current UTC time.
        """
        if checkout_dt is None:
            checkout_dt = fields.Datetime.now()

        open_attendances = self.env['hr.attendance'].sudo().search([
            ('employee_id', '=', employee.id),
            ('check_out', '=', False),
        ])
        if open_attendances:
            _logger.info(
                'Force-checking-out %d open attendance(s) for employee %s.',
                len(open_attendances),
                employee.name,
            )
            open_attendances.write({'check_out': checkout_dt})
        return open_attendances

    # ─────────────────────────────────────────────────────────────────────────
    #  ORM overrides
    # ─────────────────────────────────────────────────────────────────────────

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('check_in'):
                continue

            employee = self.env['hr.employee'].sudo().browse(vals.get('employee_id'))
            if not employee:
                continue

            # 1. Enforce restricted login time
            self._check_restricted_time()

            # 2. Force-checkout any existing open attendance for this employee
            if self._get_param_bool('hr_attendance_control.force_checkout', True):
                self._force_checkout_open_attendances(employee)

        return super().create(vals_list)

    # ─────────────────────────────────────────────────────────────────────────
    #  Kiosk / Web check-in override (hr.attendance action_checkin)
    # ─────────────────────────────────────────────────────────────────────────

    # The standard Odoo kiosk and web attendance use
    # hr.employee._attendance_action_change() which internally calls
    # hr.attendance.create(). The ORM override above already covers it.
    # We additionally hook into the employee method for extra safety.

    # ─────────────────────────────────────────────────────────────────────────
    #  Scheduled Action  –  Daily auto-checkout at 23:59
    # ─────────────────────────────────────────────────────────────────────────

    @api.model
    def _cron_auto_checkout(self):
        """
        Scheduled to run daily at ~23:59 (server local time).

        1. Closes every open attendance whose check_in date is TODAY with
           check_out = today 23:59:59 (in UTC).
        2. If the setting 'checkout_previous_days' is enabled, also closes
           any open attendance from PREVIOUS days with check_out =
           end-of-that-day 23:59:59 (in UTC).
        """
        tz_name = self.env.company.partner_id.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        today_local = now_local.date()

        _logger.info('Running _cron_auto_checkout for company tz=%s, local date=%s', tz_name, today_local)

        # ── 1. Close today's open attendances ────────────────────────────────
        checkout_today_local = datetime.combine(today_local, time(23, 59, 59))
        checkout_today_utc = tz.localize(checkout_today_local).astimezone(pytz.utc).replace(tzinfo=None)

        # Find attendances with check_in on today (local) and no check_out
        today_start_utc = tz.localize(datetime.combine(today_local, time(0, 0, 0))).astimezone(pytz.utc).replace(tzinfo=None)
        today_end_utc = checkout_today_utc  # same as 23:59:59 UTC for today

        open_today = self.env['hr.attendance'].sudo().search([
            ('check_out', '=', False),
            ('check_in', '>=', today_start_utc),
            ('check_in', '<=', today_end_utc),
        ])

        if open_today:
            _logger.info('Auto-checking-out %d attendance(s) from today.', len(open_today))
            open_today.write({'check_out': checkout_today_utc})

        # ── 2. Close previous days' open attendances (if setting enabled) ───
        if self._get_param_bool('hr_attendance_control.checkout_previous_days', True):
            open_previous = self.env['hr.attendance'].sudo().search([
                ('check_out', '=', False),
                ('check_in', '<', today_start_utc),
            ])

            if open_previous:
                _logger.info(
                    'Closing %d unclosed attendance(s) from previous days.',
                    len(open_previous),
                )
                for att in open_previous:
                    # Check-out at 23:59:59 of the same local day as check_in
                    checkin_local = pytz.utc.localize(att.check_in).astimezone(tz)
                    checkout_local = datetime.combine(checkin_local.date(), time(23, 59, 59))
                    checkout_utc = tz.localize(checkout_local).astimezone(pytz.utc).replace(tzinfo=None)
                    att.write({'check_out': checkout_utc})

        _logger.info('_cron_auto_checkout completed.')


# ─────────────────────────────────────────────────────────────────────────────
#  Restrict Odoo Web Login during restricted hours
# ─────────────────────────────────────────────────────────────────────────────

class ResUsers(models.Model):
    _inherit = 'res.users'

    def _check_credentials(self, password, env):
        """
        Block Odoo login if the current time is within the restricted window.
        """
        # First let the normal credential check run (raises if wrong password)
        result = super()._check_credentials(password, env)

        # Skip restriction for admin / internal superuser
        if self.env.su or self.id == self.env.ref('base.user_admin').id:
            return result

        ICP = self.env['ir.config_parameter'].sudo()
        if not str(ICP.get_param('hr_attendance_control.restrict_login', 'False')).lower() in ('1', 'true', 'yes'):
            return result

        try:
            restrict_from = float(ICP.get_param('hr_attendance_control.restrict_from', 0.0))
            restrict_to = float(ICP.get_param('hr_attendance_control.restrict_to', 0.0))
        except (TypeError, ValueError):
            return result

        if restrict_from == restrict_to:
            return result

        tz_name = self.env.company.partner_id.tz or 'UTC'
        tz = pytz.timezone(tz_name)
        now_local = datetime.now(tz)
        current_float = now_local.hour + now_local.minute / 60.0

        if restrict_from < restrict_to:
            is_restricted = restrict_from <= current_float < restrict_to
        else:
            is_restricted = current_float >= restrict_from or current_float < restrict_to

        if is_restricted:
            def _fmt(f):
                h = int(f)
                m = int(round((f - h) * 60))
                return '%02d:%02d' % (h, m)
            raise AccessError(
                _(
                    'System login is not allowed between %(from)s and %(to)s.',
                    **{'from': _fmt(restrict_from), 'to': _fmt(restrict_to)},
                )
            )

        return result
