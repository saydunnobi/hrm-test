{
    'name': 'Messenger & Instagram → CRM Lead',
    'version': '19.0.1.0.0',
    'category': 'Sales/CRM',
    'summary': 'Receive Facebook Messenger & Instagram DM messages and convert them to CRM Leads with one click.',
    'description': """
        Features:
        - Webhook endpoint for Facebook Messenger & Instagram DM
        - Incoming messages stored in Odoo with sender info
        - 1-Click "Convert to Lead" button on each message
        - Automatic lead creation when message arrives (optional)
        - Settings to store Page Access Token & Verify Token
    """,
    'author': 'Custom',
    'depends': ['crm', 'base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/messenger_message_views.xml',
        'views/res_config_settings_views.xml',
        'views/menu.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
