import csv
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import misc

_logger = logging.getLogger(__name__)


class Fund(models.Model):
    _name = 'efund.vehicule.fund'
    _description = 'Fonds de véhicule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'efund.vehicule': 'vehicule_id'}

    vehicule_id = fields.Many2one('efund.vehicule', required=True, ondelete='cascade')
    vehicle_type = fields.Selection(related='vehicule_id.vehicle_type', default='fund', store=True, readonly=False,
                                    required=True, string="Type")
    isin = fields.Char(string='Code Isin')
    nav_frequency = fields.Selection([('daily', 'Journalière'), ('weekly', 'Hebdomaire'), ('monthly', 'Mensuelle'), ],
                                     string="Périodicité calcul VL", default='daily')
    cutoff_time = fields.Float(string="Heure de cut-off", default=16.0,
                               help="Heure limite de réception des ordres (format décimal).\nExemples : 14.0 = 14h00, 14.5 = 14h30, 16.75 = 16h45.")
    allow_fractional_parts = fields.Boolean(string="Autoriser les parts fractionnées", default=False,
                                            help="Si décoché, les souscriptions sont arrondies à l'entier inférieur.")
    origin_nav = fields.Char(string="VL d'origine")

    ##################################################
    ## RELATIONS
    ##################################################
    share_class_ids = fields.One2many('efund.fund.share.class', 'vehicule_fund_id', string='Share Classes')
    depositary_id = fields.Many2one("efund.depositaire", string="Dépositaire")
    fund_type_id = fields.Many2one('efund.fund.type', string="Classe de fonds", required=True)

    # ------------------------------------------------------------
    # ACTION METHODS
    # ------------------------------------------------------------
    def action_activate(self):
        for record in self:
            if not record.start_date:
                raise ValidationError(_("Merci de saisir la date d'opération."))

            if record.company_id:
                record.setup_fund_accounting(record.company_id.id)
                record.state = 'active'
                record.message_post(body=_("Le fond a été activé."))
            else:
                raise ValidationError(_("Merci de sélectionner une société."))

    def action_suspend(self):
        for record in self:
            if record.state != 'active':
                raise ValidationError(_("Seuls les fonds actifs peuvent être suspendus."))
            record.state = 'suspended'
            record.message_post(body=_("Le fond a été suspendu."))

    def action_liquidate(self):
        for record in self:
            if record.state not in ('active', 'suspended'):
                raise ValidationError(_("Seuls les fonds actifs ou suspendus peuvent être liquidés."))
            record.state = 'liquidated'
            record.message_post(body=_("Le fond a été liquidé."))

    def action_reset_to_draft(self):
        pass

    def action_show_timeline(self):
        pass

    def action_show_currency(self):
        pass

    @api.model
    def setup_fund_accounting(self, company_id):
        """ Logique d'appel de la localisation l10n_fcp """
        if not self:
            return

        self.ensure_one()
        self.get_chart_account_data(company_id)



    @api.model
    def get_chart_account_data(self, company_id ):
        file_path = 'efundOpc/data/fcp_plan_comptable.csv'
        accounts_to_create = []
        try:
        # 1. Lecture complète et stockage en mémoire
            with misc.file_open(file_path, mode='r') as f:
                reader = csv.DictReader(f, delimiter=';')

                for row in reader:
                    # Préparation des valeurs pour Odoo
                    # On s'assure que les colonnes existent dans le CSV
                    reconcile_raw = str(row.get('reconcile', '')).upper()
                    reconcile_bool = True if reconcile_raw == 'VRAI' else False
                    code_store_data = {
                        'company_id': company_id,
                        'code': row.get('code'),
                    }
                    vals = {
                        'code': row.get('code'),
                        'name': row.get('name'),
                        'account_type': row.get('account_type'),
                        'code_store': code_store_data,
                        'reconcile': reconcile_bool,
                    }

                    # Validation simple : on n'ajoute que si le code et le nom sont là
                    if vals['code'] and vals['name']:
                        accounts_to_create.append(vals)

            # 2. Création massive dans la base de données

            if accounts_to_create:
                _logger.info("Début de la création de %s comptes pour le fonds.", len(accounts_to_create))

                # Option A : Création un par un (plus sûr pour isoler les erreurs)
                for acc_vals in accounts_to_create:
                    # Vérifier si le compte existe déjà pour éviter les crashs
                    """
                    existing = self.env['account.account'].search([
                        ('code', '=', acc_vals['code']),
                        (f'code_store.{company_id}', '=', acc_vals['code'])
                    ], limit=1)
                    """

                    existing = False

                    if not existing:
                        # Création du plan comptable
                        self.env['account.account'].sudo().create(acc_vals)

                        """
                        # Création des journaux comptables
                        journals = [
                            ('Souscriptions investisseurs', 'SUB', 'general'),
                            ('Rachats investisseurs', 'RED', 'general'),
                            ('Banque', 'BNK', 'bank'),
                            ('Opérations sur titres', 'SEC', 'general'),
                            ('Valorisation / Valeur liquidative', 'NAV', 'general'),
                            ('Frais', 'EXP', 'general'),
                        ]
                        """

                        """
                        journal_data = []
                        for name, code, jtype in journals:
                            vals = {
                                'name': name,
                                'code': code,
                                'type': jtype,
                                'company_id': company_id
                            }
                            journal_data.append(vals)

                        for j_vals in journal_data:
                            existing_journal = self.env['account.journal'].search([
                                ('code', '=', j_vals['code']),
                                ('company_id', '=', j_vals['company_id'])
                            ], limit=1)

                            if not existing_journal:
                                self.env['account.journal'].sudo().create(j_vals)
                            else:
                                _logger.warning("Le journal comptable %s existe déjà, passage au suivant.", j_vals['code'])



                        # Création des groupes de comptes
                        #self.create_account_groups(company_id)

                        """


                    else:
                        _logger.warning("Le compte %s existe déjà, passage au suivant.", acc_vals['code'])

                _logger.info("Importation terminée avec succès.")
            else:
                _logger.warning("Le fichier CSV est vide ou mal formaté.")

        except Exception as e:
            # On log l'erreur et on informe l'utilisateur
            _logger.error("Erreur critique lors de l'import : %s", str(e))
            raise UserError(f"Impossible d'importer le plan comptable : {str(e)}")

    def create_account_groups(self, company_id):
        file_path = 'efundOpc/data/fcp_account_group.csv'
        accounts_to_create = []
        try:
            # 1. Lecture complète et stockage en mémoire
            with misc.file_open(file_path, mode='r') as f:
                reader = csv.DictReader(f, delimiter=';')

                for row in reader:
                    # Préparation des valeurs pour Odoo
                    # On s'assure que les colonnes existent dans le CSV

                    vals = {
                        'name': row.get('name'),
                        'code_prefix_start': row.get('code_prefix_start'),
                        'code_prefix_end': row.get('code_prefix_end'),
                        'company_id': company_id,
                    }
                    # Validation simple : on n'ajoute que si le code et le nom sont là
                    if vals['code_prefix_start'] and vals['name']:
                        accounts_to_create.append(vals)

            # Création des groupes de comptes
            if accounts_to_create:
                self.env['account.group'].sudo().create(accounts_to_create)


        except Exception as e:
            # On log l'erreur et on informe l'utilisateur
            _logger.error("Erreur critique lors de l'import : %s", str(e))
            raise UserError(f"Impossible d'importer le plan comptable : {str(e)}")
