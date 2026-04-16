# -*- coding: utf-8 -*-
# Author: Saydun Nobi
import logging
from odoo import _, api, fields, models

_logger = logging.getLogger(__name__)


class WhatsAppConversation(models.Model):
    """
    Represents a single WhatsApp conversation (thread) with one contact.
    Similar to opening a chat in WhatsApp — one row per phone number.
    """
    _name = 'whatsapp.conversation'
    _description = 'WhatsApp Conversation'
    _order = 'last_message_at desc'
    _rec_name = 'display_name_computed'

    # ── Contact info ──────────────────────────────────────────────────────────
    phone_number = fields.Char(
        string='Phone Number (WhatsApp ID)',
        required=True,
        help='The sender phone number as received from Meta (e.g. 8801XXXXXXXXX).',
    )
    contact_name = fields.Char(string='Name', default='Unknown')
    partner_id = fields.Many2one(
        'res.partner', string='Linked Contact',
        help='Odoo contact linked to this conversation.',
        compute='_compute_partner', store=True,
    )

    # ── Messages ──────────────────────────────────────────────────────────────
    message_ids = fields.One2many(
        'whatsapp.message', 'conversation_id', string='Messages',
    )
    message_count = fields.Integer(
        string='Messages', compute='_compute_message_count',
    )
    last_message_at = fields.Datetime(string='Last Message', readonly=True)
    last_message_preview = fields.Char(
        string='Preview', compute='_compute_preview', store=False,
    )
    unread_count = fields.Integer(
        string='Unread', compute='_compute_unread',
    )

    # ── CRM ───────────────────────────────────────────────────────────────────
    lead_id = fields.Many2one('crm.lead', string='CRM Lead', ondelete='set null')
    state = fields.Selection([
        ('open', 'Open'),
        ('converted', 'Converted to Lead'),
        ('closed', 'Closed'),
    ], string='Status', default='open')

    display_name_computed = fields.Char(
        compute='_compute_display_name_computed', store=False,
    )

    _sql_constraints = [
        ('unique_phone', 'UNIQUE(phone_number)', 'A conversation already exists for this phone number.'),
    ]

    # ── Computes ──────────────────────────────────────────────────────────────

    @api.depends('contact_name', 'phone_number')
    def _compute_display_name_computed(self):
        for rec in self:
            rec.display_name_computed = rec.contact_name or rec.phone_number

    @api.depends('phone_number')
    def _compute_partner(self):
        for rec in self:
            partner = self.env['res.partner'].search([
                '|',
                ('mobile', '=', rec.phone_number),
                ('phone', '=', rec.phone_number),
            ], limit=1)
            rec.partner_id = partner

    def _compute_message_count(self):
        for rec in self:
            rec.message_count = len(rec.message_ids)

    def _compute_preview(self):
        for rec in self:
            last = rec.message_ids.sorted('create_date', reverse=True)[:1]
            rec.last_message_preview = (last.body or '')[:80] if last else ''

    def _compute_unread(self):
        for rec in self:
            rec.unread_count = len(rec.message_ids.filtered(
                lambda m: m.direction == 'inbound' and not m.is_read
            ))

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_open_chat(self):
        """Open the chat/conversation form view."""
        self.ensure_one()
        # Mark all inbound as read
        self.message_ids.filtered(
            lambda m: m.direction == 'inbound' and not m.is_read
        ).write({'is_read': True})
        return {
            'type': 'ir.actions.act_window',
            'name': self.display_name_computed,
            'res_model': 'whatsapp.conversation',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'current',
        }

    def action_convert_to_lead(self):
        """1-Click: Create a CRM Lead from this conversation."""
        self.ensure_one()
        if self.lead_id:
            return self._open_lead()
        lead = self.env['crm.lead'].create({
            'name': f'WhatsApp – {self.contact_name or self.phone_number}',
            'contact_name': self.contact_name,
            'mobile': self.phone_number,
            'partner_id': self.partner_id.id or False,
            'description': self._build_lead_description(),
            'type': 'lead',
        })
        self.write({'lead_id': lead.id, 'state': 'converted'})
        return self._open_lead()

    def _build_lead_description(self):
        lines = [f'WhatsApp conversation with {self.contact_name} ({self.phone_number})\n']
        for msg in self.message_ids.sorted('create_date'):
            arrow = '←' if msg.direction == 'inbound' else '→'
            lines.append(f'[{msg.create_date}] {arrow} {msg.body}')
        return '\n'.join(lines)

    def _open_lead(self):
        return {
            'type': 'ir.actions.act_window',
            'name': _('CRM Lead'),
            'res_model': 'crm.lead',
            'view_mode': 'form',
            'res_id': self.lead_id.id,
        }

    def action_send_message_wizard(self):
        """Open reply wizard."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Send WhatsApp Message'),
            'res_model': 'whatsapp.send.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_conversation_id': self.id,
                'default_phone_number': self.phone_number,
            },
        }
