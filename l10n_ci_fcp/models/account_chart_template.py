# -*- coding: utf-8 -*-

from odoo import api, fields, models, _


class AccountChartTemplate(models.AbstractModel):
    _inherit = "account.chart.template"

    @api.model
    def _get_ci_fcp_template_data(self):
        """
        Retourne les données spécifiques au template de plan comptable FCP Côte d'Ivoire
        """
        return {
            'code_digits': 6,
            'property_account_receivable_id': 'ci_fcp_411000',
            'property_account_payable_id': 'ci_fcp_401000',
            'property_account_expense_categ_id': 'ci_fcp_601000',
            'property_account_income_categ_id': 'ci_fcp_701000',
        }

    @api.model
    def _prepare_all_journals(self, acc_template_ref, company):
        """
        Prépare les journaux spécifiques aux FCP
        """
        journals = super()._prepare_all_journals(acc_template_ref, company)
        
        # Ajout de journaux spécifiques aux FCP si nécessaire
        if self == self.env.ref('l10n_ci_fcp.ci_fcp_chart_template', raise_if_not_found=False):
            journals.extend([
                {
                    'name': _('Souscriptions'),
                    'type': 'general',
                    'code': 'SOSC',
                    'favorite': True,
                    'sequence': 10,
                },
                {
                    'name': _('Rachats'),
                    'type': 'general',
                    'code': 'RCHT',
                    'favorite': True,
                    'sequence': 11,
                },
                {
                    'name': _('Revenus de Portefeuille'),
                    'type': 'general',
                    'code': 'REVP',
                    'favorite': False,
                    'sequence': 12,
                },
            ])
        
        return journals
