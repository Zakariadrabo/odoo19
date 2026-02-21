# -*- coding: utf-8 -*-
{
    'name': 'Côte d\'Ivoire - Comptabilité Fonds Commun de Placement',
    'version': '19.0.1.0.0',
    'category': 'Accounting/Localizations/Account Charts',
    'description': """
Plan Comptable pour Fonds Commun de Placement - Côte d'Ivoire
==============================================================

Ce module inclut:
-----------------
* Plan comptable spécifique aux Fonds Communs de Placement (FCP)
* Journaux comptables adaptés aux opérations de FCP
* Taxes et régimes fiscaux en vigueur en Côte d'Ivoire
* Configuration des positions fiscales
* Rapports comptables conformes à la réglementation ivoirienne

Conforme au système comptable OHADA adapté aux organismes de placement collectif.
    """,
    'author': 'Votre Société',
    'website': 'https://www.votresite.com',
    'depends': [
        'account',
        'base_vat',
    ],
    'data': [
        # Sécurité
        # Plan comptable
        #'data/account_chart_template_data.xml',
        #'data/account.account.template.csv',
        
        # Taxes
        #'data/account_tax_group_data.xml',
        #'data/account_tax_template_data.xml',
        
        # Journaux
        #'data/account_journal_data.xml',
        
        # Positions fiscales
        #'data/account_fiscal_position_template_data.xml',
        
        # Configuration finale
        'data/account_chart_template_configure_data.xml',
    ],
    'demo': [],
    'license': 'LGPL-3',
    'installable': True,
    'auto_install': False,
    'application': False,
}
