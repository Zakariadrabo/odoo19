import csv
import io
import logging
from datetime import timedelta

import xlsxwriter

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
    expense_policy = fields.Selection([
        ('all_in', 'toutes charges (Supporté par le Gestionnaire)'),
        ('real_costs', 'Frais Réels (Supporté par le Fonds)')
    ], string="Politique de charges", default='all_in')

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

    def generate_excel(self):
        # Créer le fichier Excel en mémoire
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws_mandat = workbook.add_worksheet('Mandat')
        bolth = workbook.add_format({'bold': 1, 'align': 'left', 'fg_color': '#f2ba2c', 'border': 1})
        titrestation = workbook.add_format({'bold': 1, 'align': 'center', 'font_size': 18})
        boltdg = workbook.add_format({'border': 1, 'bold': 1})
        boltd = workbook.add_format({'border': 1, 'align': 'right', })
        titre = workbook.add_format(
            {'bold': 1, 'align': 'center', 'valign': 'vcenter', 'fg_color': '#f2ba2c', 'font_size': 24})
        sous_type = workbook.add_format(
            {'bold': 1, 'align': 'center', 'valign': 'vcenter', 'fg_color': '#f2ba2c', 'font_size': 14})

        ws_mandat.set_column(0, 0, 10)
        ws_mandat.set_column(1, 1, 25)
        ws_mandat.set_column(2, 2, 15)
        ws_mandat.set_column(3, 3, 10)
        ws_mandat.set_column(4, 4, 10)
        ws_mandat.set_column(5, 5, 10)
        ws_mandat.set_column(6, 6, 10)

        position = self.position_ids.filtered(lambda p: p.state == 'active')
        mvt_cash = self.vehicule_cash_move_ids.filtered(lambda m: m.state == 'reconciled')

        rw = 0
        col = 0
        ws_mandat.merge_range(1, 0, 2, 6,
                              f"Point sur la situation du mandat à la date du {fields.Date.today().strftime('%d-%m-%Y')}",
                              titre)

        ws_mandat.write(rw + 4, col + 1, 'Titre', bolth)
        ws_mandat.write(rw + 4, col + 2, self.name, boltd)
        ws_mandat.write(rw + 5, col + 1, 'Montant', bolth)
        ws_mandat.write(rw + 5, col + 2, self.initial_amount, boltd)
        ws_mandat.write(rw + 6, col + 1, 'Taux objectif', bolth)
        ws_mandat.write(rw + 6, col + 2, self.target_return_rate, boltd)
        ws_mandat.write(rw + 7, col + 1, 'Taux réalisé', bolth)
        ws_mandat.write(rw + 7, col + 2, self.realized_return_rate, boltd)
        ws_mandat.write(rw + 8, col + 1, 'Durée du mandat (ans)', bolth)
        ws_mandat.write(rw + 8, col + 2, self.duration_months / 12, boltd)
        ws_mandat.write(rw + 9, col + 1, 'Date d\'effet', bolth)
        ws_mandat.write(rw + 9, col + 2, self.start_date.strftime('%d-%m-%Y'), boltd)
        ws_mandat.write(rw + 10, col + 1, 'Date d\'échéance', bolth)
        ws_mandat.write(rw + 10, col + 2, self.maturity_date.strftime('%d-%m-%Y'), boltd)
        ws_mandat.write(rw + 11, col + 1, 'Date Coridor 14 jours', bolth)
        ws_mandat.write(rw + 11, col + 2, (self.maturity_date + timedelta(self.days_corridor)).strftime('%d-%m-%Y'),
                        boltd)
        ws_mandat.write(rw + 12, col + 1, 'Coupon', bolth)
        ws_mandat.write(rw + 12, col + 2, (self.initial_amount * self.target_return_rate) / 100, boltd)
        ws_mandat.write(rw + 13, col + 1, 'Principal + intérêt annuel', bolth)
        ws_mandat.write(rw + 13, col + 2, self.initial_amount + (self.initial_amount * self.target_return_rate) / 100,
                        boltd)

        ws_mandat.merge_range(15, 0, 15, 6, f"Titres détenus", sous_type)

        rwstation = rw + 16
        colstation = col
        if position:
            ws_mandat.write(rwstation, colstation, 'S/N', bolth)
            ws_mandat.write(rwstation, colstation + 1, 'Code Isin', bolth)
            ws_mandat.write(rwstation, colstation + 2, 'Type', bolth)
            ws_mandat.write(rwstation, colstation + 3, 'Sous type', bolth)
            ws_mandat.write(rwstation, colstation + 4, 'Pays', bolth)
            ws_mandat.write(rwstation, colstation + 5, 'Montant Nominal', bolth)
            ws_mandat.write(rwstation, colstation + 6, 'Quantité', bolth)

            rwstation += 1

            for i, pos in enumerate(position):
                ws_mandat.write(rwstation, colstation, i + 1, boltd)
                ws_mandat.write(rwstation, colstation + 1, pos.instrument_id.isin, boltd)
                ws_mandat.write(rwstation, colstation + 2, pos.instrument_id.instrument_type, boltd)
                if pos.instrument_id.instrument_type == 'bond':
                    bond = self.env['efund.vehicule.instrument.core.bond'].search(
                        [('instrument_id', '=', pos.instrument_id.id)])
                    if bond:
                        ws_mandat.write(rwstation, colstation + 3, bond.bond_type, boltd)
                    else:
                        ws_mandat.write(rwstation, colstation + 3, '', boltd)
                ws_mandat.write(rwstation, colstation + 4, pos.instrument_id.issuer_id.country_id.name or '', boltd)
                ws_mandat.write(rwstation, colstation + 5, pos.quantity * pos.avg_cost, boltd)
                ws_mandat.write(rwstation, colstation + 6, pos.quantity, boltd)

                rwstation += 1

        # Mouvement cash
        ws_flux = rwstation + 2
        ws_mandat.merge_range(ws_flux, 0, ws_flux, 4, f"Flux de Trésorerie", sous_type)
        ws_flux += 2
        if mvt_cash:
            ws_mandat.write(ws_flux, colstation, 'Date', bolth)
            ws_mandat.write(ws_flux, colstation + 1, 'Opération', bolth)
            ws_mandat.write(ws_flux, colstation + 2, 'Débit', bolth)
            ws_mandat.write(ws_flux, colstation + 3, 'Crédit', bolth)
            ws_mandat.write(ws_flux, colstation + 4, 'Solde', bolth)

            ws_flux += 1

            for mvt in mvt_cash:
                ws_mandat.write(ws_flux, colstation, mvt.date.strftime('%d-%m-%Y'), boltd)
                ws_mandat.write(ws_flux, colstation + 1, f"{mvt.label}", boltd)
                ws_mandat.write(ws_flux, colstation + 2, mvt.amount,
                                boltd) if '_out' in mvt.move_type else ws_mandat.write(ws_flux, colstation + 2, '',
                                                                                       boltd)
                ws_mandat.write(ws_flux, colstation + 3, mvt.amount,
                                boltd) if '_in' in mvt.move_type else ws_mandat.write(ws_flux, colstation + 3, '',
                                                                                      boltd)
                ws_mandat.write(ws_flux, colstation + 4, mvt.balance_running, boltd)

                ws_flux += 1

        workbook.close()
        output.seek(0)
        excel_file = base64.b64encode(output.read())
        attachment = self.env['ir.attachment'].create({
            'name': 'situation_mandat.xlsx',
            'datas': excel_file,
            'db_datas': 'export_excel.xlsx',
            'res_model': 'efund.vehicule.mandate',  # Mettez le nom de votre modèle ici
            'res_id': self.id,
        })

        # Retourner une action pour télécharger le fichier
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % (attachment.id),
            'target': 'new',
            'nodestroy': True,
        }