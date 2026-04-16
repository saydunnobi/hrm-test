# -*- coding: utf-8 -*-
# Author: Saydun Nobi
import json
import logging
import requests

from odoo import http, fields
from odoo.http import request

_logger = logging.getLogger(__name__)


class WhatsAppWebhook(http.Controller):

    # ── Webhook Verification (GET) ─────────────────────────────────────────────
    @http.route('/whatsapp/webhook', type='http', auth='public',
                methods=['GET'], csrf=False)
    def verify_webhook(self, **kwargs):
        ICP = request.env['ir.config_parameter'].sudo()
        verify_token = ICP.get_param('whatsapp_business.verify_token', '')

        hub_mode = kwargs.get('hub.mode')
        hub_verify_token = kwargs.get('hub.verify_token')
        hub_challenge = kwargs.get('hub.challenge', '')

        if hub_mode == 'subscribe' and hub_verify_token == verify_token:
            _logger.info('WhatsApp webhook verified.')
            return request.make_response(hub_challenge, headers=[('Content-Type', 'text/plain')])
        return request.make_response('Forbidden', status=403)

    # ── Incoming Messages (POST) ───────────────────────────────────────────────
    @http.route('/whatsapp/webhook', type='http', auth='public',
                methods=['POST'], csrf=False)
    def receive_message(self, **kwargs):
        try:
            data = json.loads(request.httprequest.data)
            _logger.info('WhatsApp payload received: %s', data)

            if data.get('object') != 'whatsapp_business_account':
                return request.make_response('ok', headers=[('Content-Type', 'text/plain')])

            for entry in data.get('entry', []):
                for change in entry.get('changes', []):
                    value = change.get('value', {})
                    messages = value.get('messages', [])
                    contacts = value.get('contacts', [])

                    for message in messages:
                        if message.get('type') != 'text':
                            continue
                        phone = message.get('from', '')
                        text = message.get('text', {}).get('body', '')
                        wa_id = message.get('id', '')

                        # Resolve name from contacts block
                        sender_name = 'Unknown'
                        for c in contacts:
                            if c.get('wa_id') == phone:
                                sender_name = c.get('profile', {}).get('name', 'Unknown')
                                break

                        self._handle_incoming(phone, sender_name, text, wa_id)

            return request.make_response(
                json.dumps({'status': 'ok'}),
                headers=[('Content-Type', 'application/json')]
            )
        except Exception as e:
            _logger.error('WhatsApp webhook error: %s', str(e))
            return request.make_response('error', status=500)

    def _handle_incoming(self, phone, sender_name, text, wa_id):
        env = request.env(su=True)
        ICP = env['ir.config_parameter']
        auto_lead = str(ICP.get_param('whatsapp_business.auto_lead', 'False')).lower() in ('1', 'true', 'yes')

        # Find or create conversation
        conv = env['whatsapp.conversation'].search([('phone_number', '=', phone)], limit=1)
        if not conv:
            conv = env['whatsapp.conversation'].create({
                'phone_number': phone,
                'contact_name': sender_name,
                'last_message_at': fields.Datetime.now(),
            })
        else:
            if sender_name and sender_name != 'Unknown':
                conv.write({'contact_name': sender_name})
            conv.write({'last_message_at': fields.Datetime.now()})

        # Save message
        env['whatsapp.message'].create({
            'conversation_id': conv.id,
            'direction': 'inbound',
            'body': text,
            'wa_message_id': wa_id,
            'is_read': False,
        })

        # Auto-create lead if setting is on and not already converted
        if auto_lead and conv.state == 'open' and not conv.lead_id:
            conv.action_convert_to_lead()
