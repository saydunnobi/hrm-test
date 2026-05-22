# -*- coding: utf-8 -*-
# ============================================================================
#  WhatsApp Business Chat for Odoo 19
#  Author: Saydun Nobi
#  License: LGPL-3
# ============================================================================
{
    'name': 'WhatsApp Business Chat Ovi',
    'version': '19.0.1.0.0',
    'category': 'Discuss/WhatsApp',
    'summary': 'Use WhatsApp Business from Odoo — send, receive messages and create CRM leads. One number. One inbox.',
    'description': """
WhatsApp Business Chat
======================
Login with your WhatsApp Business number and use Odoo like your personal WhatsApp:
- View all incoming messages in a real chat interface
- Reply directly from Odoo
- Automatically create CRM leads from unknown senders
- Incoming messages from known contacts are linked automatically
- Supports text, emojis
- Webhook powered by Meta WhatsApp Cloud API
    """,
    'author': 'Saydun Nobi',
    'depends': ['mail', 'crm', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'views/whatsapp_conversation_views.xml',
        'views/whatsapp_message_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'images': ['static/description/icon.png'],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
