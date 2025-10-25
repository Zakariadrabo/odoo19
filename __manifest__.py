{

    'name': 'Gestion de Fonds - Suite',
    'version': '19.0.1',
    'category': 'Finance',
    'summary': 'Gestion complète des fonds communs de placement',
    'description': """
    Module de gestion des fonds d'investissement
    ===========================================

    Fonctionnalités principales:
    * Gestion des sociétés de gestion
    * Gestion des fonds avec multi-sociétés
    * Suivi des performances
    * Gestion des investisseurs
    * Reporting réglementaire
""",
    'author': 'eSecureX',
    'website': 'https://www.esecurex.com',
    'depends': ['base','account','contacts'],
    'data': [
        'security/ir.model.access.csv',
        'views/efund_action_menu_principal.xml',
        'views/efund_menu_principal.xml',
        'views/efund_action_menu_parametre.xml',
        #'views/efund_action_fund.xml',

        'views/efund_menu_parametre.xml',
        'views/efund_investor_views.xml',
        'views/efund_views_parametre.xml',
        'views/efund_views_fund.xml',

    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
