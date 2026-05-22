# -*- coding: utf-8 -*-
# Author: Saydun Nobi
import logging
import requests
from odoo import _, api, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class WhatsAppMessage(models.Model):
    """
    A single WhatsApp message inside a conversation.
    """
    _name = 'whatsapp.message'
    _description = 'WhatsApp Message'
    _order = 'create_date asc'

    conversation_id = fields.Many2one(
        'whatsapp.conversation', string='Conversation',
        required=True, ondelete='cascade', index=True,
    )
    direction = fields.Selection([
        ('inbound', 'Received ←'),
        ('outbound', 'Sent →'),
    ], string='Direction', required=True, default='inbound')
    body = fields.Text(string='Message', required=True)
    wa_message_id = fields.Char(string='WhatsApp Message ID', readonly=True)
    is_read = fields.Boolean(string='Read', default=False)
    status = fields.Selection([
        ('sent', 'Sent'),
        ('delivered', 'Delivered'),
        ('read', 'Read'),
        ('failed', 'Failed'),
    ], string='Status', default='sent')



class WhatsAppSendWizard(models.TransientModel):
    """
    Wizard to type and send a reply from within Odoo.
    """
    _name = 'whatsapp.send.wizard'
    _description = 'Send WhatsApp Message'

    conversation_id = fields.Many2one('whatsapp.conversation', string='Conversation', required=True)
    phone_number = fields.Char(string='To', required=True)
    body = fields.Text(string='Message', required=True)

    def action_send(self):
        self.ensure_one()
        ICP = self.env['ir.config_parameter'].sudo()
        access_token = ICP.get_param('whatsapp_business.access_token', '')
        phone_number_id = ICP.get_param('whatsapp_business.phone_number_id', '')

        if not access_token or not phone_number_id:
            raise UserError(_(
                'WhatsApp is not configured. Please go to Settings → WhatsApp Business '
                'and enter your Phone Number ID and Access Token.'
            ))

        # Send via Meta Cloud API
        url = f'https://graph.facebook.com/v19.0/{phone_number_id}/messages'
        payload = {
            'messaging_product': 'whatsapp',
            'to': self.phone_number,
            'type': 'text',
            'text': {'body': self.body},
        }
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json',
        }
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            wa_id = resp.json().get('messages', [{}])[0].get('id', '')
        except Exception as e:
            raise UserError(_('Failed to send message: %s') % str(e))

        # Save outbound message
        self.env['whatsapp.message'].create({
            'conversation_id': self.conversation_id.id,
            'direction': 'outbound',
            'body': self.body,
            'wa_message_id': wa_id,
            'is_read': True,
            'status': 'sent',
        })
        self.conversation_id.write({'last_message_at': fields.Datetime.now()})
        _logger.info('Sent WhatsApp message to %s', self.phone_number)
        return {'type': 'ir.actions.act_window_close'}
