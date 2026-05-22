{
    'name': 'Subcontract Management',
    'version': '1.0',
    'category': 'Operations/Project',
    'summary': 'Manage subcontracted projects, verify work distribution, and track OEE metrics',
    'description': """
        This module provides a centralized system to manage large projects broken down into assignments for multiple vendors or internal teams.
        Features include:
        - Project breakdown and assignments
        - Vendor-based work tracking
        - Profit and costing metrics
        - Operational Equipment Effectiveness (OEE) metrics
    """,
    'author': 'Kazi Md saydunnobi',
    'depends': ['base', 'purchase', 'stock'],
    'data': [
        'security/ir.model.access.csv',
        'views/menu_views.xml',
        'views/subcontract_project_views.xml',
        'views/subcontract_task_views.xml',
        'views/dashboard_action.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'subcontract_management/static/src/dashboard/dashboard.js',
            'subcontract_management/static/src/dashboard/dashboard.xml',
            'subcontract_management/static/src/css/style.css',
        ],
    },
    'installable': True,
    'application': True,
    'license': 'LGPL-3',
}
