{
    'name': 'HR Attendance Control',
    'version': '16.0.1.0.0',
    'category': 'Human Resources/Attendances',
    'summary': 'Force checkout, auto daily checkout at 23:59, and login time restriction',
    'description': """
        Features:
        - Force check-out any currently checked-in employee before new check-in
        - Auto check-out all previous unclosed attendances at 23:59
        - Daily scheduled auto check-out at 23:59 PM
        - Restrict employee login/check-in within a configured time range
    """,
    'author': 'Custom',
    'depends': ['hr_attendance', 'base_setup'],
    'data': [
        'security/ir.model.access.csv',
        'views/res_config_settings_views.xml',
        'views/hr_attendance_views.xml',
        'data/ir_cron_data.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'license': 'LGPL-3',
}
