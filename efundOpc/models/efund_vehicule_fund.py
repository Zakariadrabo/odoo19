import csv
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import misc

_logger = logging.getLogger(__name__)


class Fund(models.Model):
    _name = 'efund.vehicule.fund'
    _description = 'Fonds de véhicule'
    _inherits = {'efund.vehicule': 'vehicule_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']

    vehicule_id = fields.Many2one('efund.vehicule', required=True, ondelete='cascade')
    vehicle_type = fields.Selection(related='vehicule_id.vehicle_type', default='fund', store=True, readonly=False,required=True, string="Type")
    isin = fields.Char(string='Code Isin')
    nav_frequency = fields.Selection([('daily', 'Journalière'), ('weekly', 'Hebdomaire'), ('monthly', 'Mensuelle'), ], string="Périodicité calcul VL", default='daily')
    cutoff_time = fields.Float(string="Heure de cut-off",digits=(4, 2), default=16.0, help="Heure limite de réception des ordres (format décimal).\nExemples : 14.0 = 14h00, 14.5 = 14h30, 16.75 = 16h45.")
    allow_fractional_parts = fields.Boolean(string="Autoriser parts fractionnées ?", default=False,  help="Si décoché, les souscriptions sont arrondies à l'entier inférieur.")
    origin_nav = fields.Char(string="VL initiale", required=True)

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
        for rec in self:
            if not rec.start_date:
                raise ValidationError(_("Merci de saisir la date d'opération."))
            if rec.company_id:
                rec.setup_fund_accounting(rec.company_id.id)
                # appel au service pour la création du premier VL
                res = self.env['efund.service'].create_first_nav(rec)
                if not res:
                    raise ValidationError(_("Erreur lors de la création du premier VL."))
                rec.state = 'active'
                rec.message_post(body=_("Le fond a été activé."))
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
        self.env['efund.event.handler'].get_chart_account_data(company_id)


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

    def action_revalue_positions(self):
        for record in self:
            position_ids = record.position_ids
            for pos in position_ids:
                # 1. Aller chercher le dernier prix VALIDÉ pour cet instrument
                last_price_rec = self.env['efund.vehicule.instrument.core.price'].search([
                    ('instrument_id', '=', pos.instrument_id.id),
                    ('is_validated', '=', True),
                    ('date', '<=', fields.Date.today())
                ], order='date desc', limit=1)

                if last_price_rec:
                    # 2. Mettre à jour la position avec le prix officiel
                    pos.write({
                        'last_price': last_price_rec.price,
                        'last_price_date': last_price_rec.date
                    })
                    # Le _compute_valuation_details fera le reste (Clean/Dirty/Accrued)
                else:
                    last_price_rec.cron_generate_daily_prices()
                    # self.action_refresh_valuation()
