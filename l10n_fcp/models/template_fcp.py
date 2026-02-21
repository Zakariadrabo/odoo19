import csv
import logging
import os
from odoo import models, fields, api, _
from odoo.modules import module
from odoo.addons.account.models.chart_template import template
_logger = logging.getLogger(__name__)

class AccountChartTemplate(models.AbstractModel):
    _inherit = 'account.chart.template'

    @template('ci_fcp')
    def _get_fcp_template_data(self):
        return {
            'name': _('Plan Comptable OPCVM UEMOA'),
            'code_digits': 6,
            'currency_id': self.env.ref('base.ci').id,
        }

    @api.model
    def _get_fcp_account_data(self):
        """
        Cette méthode lit le CSV et génère les données pour Odoo.
        Elle est beaucoup plus tolérante que le XML.
        """
        # Localisation du fichier CSV dans votre module
        #path = get_module_resource('l10n_fcp', 'data', 'account_account_template.csv')
        path = module.get_resource_path('l10n_fcp', 'data/account_account_template.csv')
        if not path or not os.path.exists(path):
            return {}

        accounts_data = {}
        with open(path, 'r', encoding='utf-8') as csvfile:
            reader = csv.DictReader(csvfile)

            # Extrait de votre méthode Python
            for row in reader:
                code = row['Compte']
                xml_id = f"account_{code}"
                accounts_data[xml_id] = {
                    'code': code,
                    'name': row['Libellé'],
                    'account_type': row['Type de compte'],
                    'reconcile': row['reconcile'] == 'True',
                    'create_asset': 'no',
                }

        return accounts_data