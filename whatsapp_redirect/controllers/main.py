import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)

class WhatsappWebhook(http.Controller):

    @http.route('/whatsapp/webhook', type='http', auth='public', methods=['GET', 'POST'], csrf=False)
    def whatsapp_webhook(self, **kwargs):
        """
        Webhook endpoint for Meta WhatsApp Cloud API.
        Handles GET for verification and POST for incoming messages.
        """
        if request.httprequest.method == 'GET':
            # Meta App Verification
            # In a production environment, this token should be a system parameter.
            verify_token = "odoo_whatsapp_token" 
            hub_mode = kwargs.get('hub.mode')
            hub_verify_token = kwargs.get('hub.verify_token')
            hub_challenge = kwargs.get('hub.challenge')

            if hub_mode == 'subscribe' and hub_verify_token == verify_token:
                _logger.info('WhatsApp Webhook verified successfully.')
                return request.make_response(hub_challenge, headers=[('Content-Type', 'text/plain')])
            return request.make_response("Verification failed", status=403)

        if request.httprequest.method == 'POST':
            try:
                data = json.loads(request.httprequest.data)
                _logger.info("Received WhatsApp Payload: %s", data)

                # Parse the Meta WhatsApp JSON structure
                if data.get('object') == 'whatsapp_business_account':
                    for entry in data.get('entry', []):
                        for change in entry.get('changes', []):
                            value = change.get('value', {})
                            messages = value.get('messages', [])
                            contacts = value.get('contacts', [])
                            
                            for message in messages:
                                if message.get('type') == 'text':
                                    phone_number = message.get('from')
                                    text_body = message.get('text', {}).get('body', '')
                                    
                                    # Find contact name if available
                                    contact_name = "WhatsApp User"
                                    for contact in contacts:
                                        if contact.get('wa_id') == phone_number:
                                            contact_name = contact.get('profile', {}).get('name', 'WhatsApp User')

                                    # Create the Lead
                                    self._create_whatsapp_lead(phone_number, contact_name, text_body)

                return request.make_response(json.dumps({'status': 'ok'}), headers=[('Content-Type', 'application/json')])

            except Exception as e:
                _logger.error("Error processing WhatsApp webhook: %s", str(e))
                return request.make_response("Error", status=500)

    def _create_whatsapp_lead(self, phone_number, contact_name, text_body):
        """Creates a CRM Lead from an incoming WhatsApp message"""
        # Search for an existing active lead from this phone to avoid duplicates if preferred.
        # Here we always create a new lead based on the user's prompt.
        env = request.env(su=True)
        formatted_phone = "+" + phone_number if not phone_number.startswith("+") else phone_number
        
        lead_vals = {
            'name': f'WhatsApp Request - {contact_name}',
            'contact_name': contact_name,
            'phone': formatted_phone,
            'description': f"Incoming WhatsApp Message:\n{text_body}",
            'type': 'lead',
        }
        
        lead = env['crm.lead'].create(lead_vals)
        _logger.info("Created new CRM Lead (ID: %s) from WhatsApp number: %s", lead.id, phone_number)
