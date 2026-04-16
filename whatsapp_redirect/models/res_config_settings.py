# -*- coding: utf-8 -*-
# Author: Saydun Nobi
from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    whatsapp_phone_number_id = fields.Char(
        string='Phone Number ID',
        config_parameter='whatsapp_business.phone_number_id',
        help='Your WhatsApp Business Phone Number ID from Meta Developer Console.',
    )
    whatsapp_access_token = fields.Char(
        string='Access Token',
        config_parameter='whatsapp_business.access_token',
        help='Permanent or temporary Access Token from Meta Developer Console.',
    )
    whatsapp_verify_token = fields.Char(
        string='Webhook Verify Token',
        config_parameter='whatsapp_business.verify_token',
        help='A secret string you choose and paste in the Meta Webhook configuration.',
    )
    whatsapp_auto_lead = fields.Boolean(
        string='Auto-create CRM Lead for new contacts',
        config_parameter='whatsapp_business.auto_lead',
        help='Automatically create a CRM Lead when a message arrives from an unknown number.',
    )
