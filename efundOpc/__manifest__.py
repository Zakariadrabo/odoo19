{

    'name': 'efundOpc',
    'version': '19.0.1',
    'category': 'Finance',
    'summary': 'Gestion de Fonds - Suite',
    'description': """
    Module de gestion des fonds d'investissement
    Gestion complète des fonds communs de placement
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
    'depends': ['base', 'account', 'contacts'],
    'data': [
        'security/ir.model.access.csv',
        'security/efund_security.xml',
        'views/efund_views_management_company_form.xml',
        'views/efund_action_menu_principal.xml',
        'views/efund_menu_principal.xml',
        'views/efund_action_menu_parametre.xml',
        'views/efund_aml_alert_views.xml',
        'views/efund_views_instrument.xml',
        'wizard/efund_bon_amortization_wizard.xml',
        'wizard/efund_fund_import_price_wizard_views.xml',
        'views/efund_position_views.xml',
        'wizard/efund_position_wizard_views.xml',
        'views/efund_fund_subscription_views.xml',
        'wizard/efund_cash_deposit_wizard.xml',
        'wizard/efund_bourse_order_execution_wizard_views.xml',
        'views/efund_bourse_order_views.xml',
        'views/efund_depositaire.xml',
        'views/efund_menu_parametre.xml',
        'views/efund_fund_investor_views.xml',
        'views/efund_investor_views.xml',
        'views/efund_views_parametre.xml',
        'views/efund_views_fund.xml',
        'views/view_efund_initial_valuation_investor_line_form.xml',
        'views/fund_initial_valuation_wizard_views.xml',
        'views/fund_share_class_views.xml',
        'views/efund_view_compliance_policy_tree.xml',
        'views/efund_views_valuation.xml',
        'reports/efund_kyc_report.xml',
        'reports/efund_kyc_report_template.xml',
        'views/efund_fund_instrument_event_views.xml',
        'views/efund_position_adjustment_views.xml',
        'wizard/efund_account_activate_wizard_views.xml',
        'wizard/efund_fund_redemption_wizard_views.xml',
        'wizard/efund_fund_subscription_wizard_views.xml',
        'views/efund_mandate_views.xml',
        'wizard/efund_mandate_termination_wizard_views.xml',
        'views/efund_cash_deposit_views.xml',
        'views/efund_fund_redemption_views.xml',
        'views/efund_cash_withdraw_views.xml',
        'wizard/efund_confirm_wizard_views.xml',

    ],

    'installable': True,
    'application': True,
    'auto_install': False,
    'license': 'LGPL-3',
}
