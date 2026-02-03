import base64
import io
import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import xlsxwriter
_logger = logging.getLogger(__name__)


class Mandate(models.Model):
    _name = 'efund.vehicule.mandate'
    _inherits = {'efund.vehicule': 'vehicule_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']

    code = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.vehicule.mandate'))
    vehicule_id = fields.Many2one('efund.vehicule', required=True, ondelete='cascade')
    #vehicle_type = fields.Selection([('mandate', 'Mandat')], default='mandate', required=True, string="Type")
    investor_id = fields.Many2one('efund.investor', required=True, string="Investisseur")
    risk_profile = fields.Selection([('low', 'Prudent'), ('medium', 'Équilibré'), ('high', 'Dynamique')],
                                    string='Profil de risque', required=True)
    currency_id = fields.Many2one(related='vehicule_id.currency_id', string="Devise")
    coupon_ids = fields.One2many('efund.mandate.coupon', 'mandate_id', string="Coupons")
    cash_move_ids = fields.One2many('efund.investor.cash_account.move', 'vehicule_id', string="Flux financiers")

    rule_ids = fields.One2many('efund.vehicule.mandate.rule', 'mandate_id', string="Règles de Mandat")
    is_fund_released = fields.Boolean(string='Est un fonds', default=False)
    coupon_capitalisation = fields.Boolean(string='Est capitalisé', default=False)

    # risk_profile_id = fields.Many2one('mandate.risk.profile',string='Profil de risque',required=True)

    # ---------------------------------------------------------
    # PARAMETRES FINANCIERS CONTRACTUELS
    # ---------------------------------------------------------
    initial_amount = fields.Monetary(string='Montant initial confié', required=True)
    target_return_rate = fields.Float(string='Taux de rendement objectif (%)', required=True)
    coupon_frequency = fields.Selection([('annual', 'Annuel'), ('semiannual', 'Semestriel'), ],
                                        string='Fréquence des coupons', required=True)
    calculeted_base = fields.Selection([('360', '360'), ('365', '365')], string='Calculé', default='360')

    # ---------------------------------------------------------
    # CORRIDOR DE PERFORMANCE
    # ---------------------------------------------------------
    days_corridor = fields.Integer(string='Nombre de jours corridor', required=True)
    corridor_min_rate = fields.Float(string='Corridor minimum (%)')
    corridor_max_rate = fields.Float(string='Corridor maximum (%)')
    corridor_start_date = fields.Date(string='Date début corridor')
    corridor_end_date = fields.Date(string='Date fin corridor')

    # ---------------------------------------------------------
    # PARAMETRES TEMPORELS
    # ---------------------------------------------------------
    start_date = fields.Date(string="Date d'effet", required=True)
    duration_months = fields.Integer(string='Durée du mandat (mois)', required=True)
    maturity_date = fields.Date(string='Date d’échéance', compute='_compute_maturity_date', store=True)
    amount_received_date = fields.Date(string='Date de réception des fonds')

    # ---------------------------------------------------------
    # INDICATEURS CALCULÉS (PAS SAISIS)
    # ---------------------------------------------------------
    realized_return_rate = fields.Float(string='Taux de rendement réalisé (%)', compute='_compute_realized_performance',
                                        store=True)
    deviation_from_target = fields.Float(string='Écart vs objectif (%)', compute='_compute_realized_performance',
                                         store=True)

    # Relation


    # ---------------------------------------------------------
    # CONTROLES
    # ---------------------------------------------------------
    @api.depends('start_date', 'duration_months')
    def _compute_maturity_date(self):
        for rec in self:
            if rec.start_date and rec.duration_months:
                rec.maturity_date = fields.Date.add(
                    rec.start_date, months=rec.duration_months
                )


    @api.depends('initial_amount')
    def _compute_realized_performance(self):
        pass
        """
        Calcul basé sur la dernière valorisation du portefeuille.
        
        for rec in self:
            valuation = self.env['mandate.valuation'].search(
                [('mandate_id', '=', rec.id)],
                order='valuation_date desc',
                limit=1
            )
            if valuation:
                rec.realized_return_rate = (
                        (valuation.total_value - rec.initial_amount)
                        / rec.initial_amount * 100
                )
                rec.deviation_from_target = (
                        rec.realized_return_rate - rec.target_return_rate
                )
            else:
                rec.realized_return_rate = 0.0
                rec.deviation_from_target = 0.0
                """

    @api.constrains('corridor_min_rate', 'corridor_max_rate')
    def _check_corridor(self):
        for rec in self:
            if rec.corridor_min_rate and rec.corridor_max_rate:
                if rec.corridor_min_rate >= rec.corridor_max_rate:
                    raise ValidationError(
                        _("Le corridor minimum doit être inférieur au corridor maximum.")
                    )

    def action_activate(self):
        for rec in self:
            if not rec.start_date:
                raise ValidationError(_("Merci de saisir la date d'opération."))
            if rec.state != 'draft':
                continue

            # implementer le déplacement du cash du compte investisseur vers le compte mandat
            balance = self.env['efund.investor.cash_account'].get_balance_by_investor(rec.investor_id.id, rec.vehicule_id.id)
            if balance <= 0:
                raise ValidationError(_("Le compte de l'investisseur n'a pas suffisamment de fonds pour confirmer le mandat."))


            # Vérification de l'existence du compte cash du fond
            vehicule_cash = self.env['efund.vehicule.cash'].search([('vehicule_id', '=', rec.vehicule_id.id)], limit=1)
            if not vehicule_cash:
                vehicule_cash = self.env['efund.vehicule.cash'].create({
                    'name': f"Compte cash - " + rec.vehicule_id.name,
                    'vehicule_id': rec.vehicule_id.id,
                    'state': 'active',
                })

                rec.message_post(body=_("Création du compte Cash du Mandat."))

            # récupérer ID du compte cash du fond
            vehicule_cash_id =  self.env['efund.vehicule.cash'].get_vehicule_cash_id_by_vehicule_id(rec.vehicule_id.id)

            if vehicule_cash_id <= 0 :
                raise ValidationError(_("Le compte cash du mandat n'a pas été trouvé. Veuillez contacter le support."))

            # débit du compte cash de l'investisseur vers le compte mandat
            investor_cash_account_id = self.env['efund.investor.cash_account'].get_cash_account_id_investor_by_vehicule_and_investor_id(self.vehicule_id.id, self.investor_id.id)
            investor_cash_move = self.env['efund.investor.cash_account.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.investor.cash_account.move'),
                'cash_account_id': investor_cash_account_id,
                'label': f"Transfert de {balance} du compte investisseur vers le compte du mandat {self.name}",
                'move_type': 'deposit_out',
                'amount': balance,
                'state': 'reconciled'
            })
            rec.message_post(body=_(f"Débit de %s de francs cfa du compte de l'investisseur pour le compte du mandat .")% (balance))

            # mouvement du compte investisseur vers le compte mandat
            fund_move = self.env['efund.vehicule.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                'vehicule_cash_id': vehicule_cash.id,
                'amount': balance,
                'label': f"Dépôt de {balance} francs CFA sur le compte du mandat {self.name}",
                'move_type': 'deposit_in',
                'liquidity_type': 'liquid',
                'state': 'reconciled',
                'investor_id': rec.investor_id.id,
                'vehicule_id': rec.vehicule_id.id,
            })
            rec.message_post(body=_("Crédit de %s venant du compte investisseur.") % balance)
            rec.state = 'active'
            rec.message_post(body=_("Le mandat a été confirmé et est maintenant actif."))

    def action_suspend(self):
        for record in self:
            if record.state != 'active':
                raise ValidationError(_("Seuls les mandats actifs peuvent être suspendus."))
            record.state = 'suspended'
            record.message_post(body=_("Le mandats a été suspendu."))

    def action_liquidate(self):
        for record in self:
            if record.state not in ('active', 'suspended'):
                raise ValidationError(_("Seuls les mandats actifs ou suspendus peuvent être liquidés."))
            record.state = 'liquidated'
            record.message_post(body=_("Le mandat a été liquidé."))

    def get_mandate_by_vehicule_id(self, vehicule_id):
        mandate = self.search([('vehicule_id', '=', vehicule_id)], limit=1)
        if mandate:
            return mandate
        else:
            return False

    def action_reset_to_draft(self):
        pass

    def action_view_coupons(self):
        pass

    def action_view_cash_moves(self):
        pass

    def action_close_mandate(self):
        pass

    def action_print_report(self):
        pass

    def action_view_valuations(self):
        pass

    def generate_coupon_schedule(self):
        self.ensure_one()
        service = self.env['efund.service']
        # 1. Nettoyage des anciens coupons non payés
        #self.coupon_ids.filtered(lambda c: c.state == 'draft').unlink()
        self.coupon_ids.unlink()

        # 2. Appel du générateur
        coupons_data = service.generate_coupon_schedule(
            self.initial_amount,
            self.target_return_rate,
            self.coupon_frequency,
            self.start_date,
            self.maturity_date,
            int(self.calculeted_base)
        )

        # 3. Création des enregistrements
        vals_list = []
        for i, line in enumerate(coupons_data, 1):
            vals_list.append({
                'mandate_id': self.id,
                'coupon_number': i,
                'date_debut': line.get('date_debut'),
                'date_fin': line.get('date_fin'),
                'date_paiement': line.get('date_fin'),
                'nb_jours': line.get('jours'),
                'montant': line.get('montant'),
                'state': 'draft',
            })
        self.env['efund.mandate.coupon'].create(vals_list)

        # Message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Calendrier des coupons généré'),
                'message': _('Génération réussi de %s paiement de coupon.') % len(coupons_data),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }

            }
        }

        # Valorisation des positions d'un véhicule

    def action_revalue_positions(self):
        """Boucle sur toutes les positions du mandat pour les actualiser"""
        self.ensure_one()
        positions = self.position_ids.filtered(lambda p: p.state == 'active')

        if not positions:
            return True

        # On appelle la méthode de calcul sur le recordset des positions
        positions._compute_market_value()

        # Optionnel : Ajouter un log dans le chatter pour l'audit
        self.message_post(body=_("Valorisation manuelle des positions effectuée le %s") % fields.Datetime.now())

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Succès'),
                'message': _('%s positions ont été actualisées.') % len(positions),
                'type': 'success',
                'sticky': False,
            }
        }



    def action_push_deposit(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Faire le déposit du mandat',
            'res_model': 'efund.vehicule.mandat.deposit.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_ids': [self.id],
                'default_mandate_id': self.id,
                'default_deposit_amount': self.initial_amount,
            },
        }

    def generate_excel(self):
        # Créer le fichier Excel en mémoire
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        ws_mandat = workbook.add_worksheet('Mandat')
        bolth = workbook.add_format({'bold': 1, 'align': 'left', 'fg_color': '#f2ba2c', 'border': 1})
        titrestation = workbook.add_format({'bold': 1, 'align': 'center', 'font_size': 18})
        boltdg = workbook.add_format({'border': 1, 'bold': 1})
        boltd = workbook.add_format({'border': 1,'align': 'right', })
        titre = workbook.add_format({'bold': 1, 'align': 'center', 'valign': 'vcenter','fg_color': '#f2ba2c', 'font_size': 24})
        sous_type = workbook.add_format({'bold': 1, 'align': 'center', 'valign': 'vcenter','fg_color': '#f2ba2c', 'font_size': 14})

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
        ws_mandat.merge_range(1, 0, 2, 6,f"Point sur la situation du mandat à la date du {fields.Date.today().strftime('%d-%m-%Y')}",titre)

        ws_mandat.write(rw + 4, col + 1, 'Titre', bolth)
        ws_mandat.write(rw + 4, col + 2, self.name, boltd)
        ws_mandat.write(rw + 5, col + 1, 'Montant', bolth)
        ws_mandat.write(rw + 5, col + 2, self.initial_amount, boltd)
        ws_mandat.write(rw + 6, col + 1, 'Taux objectif', bolth)
        ws_mandat.write(rw + 6, col + 2, self.target_return_rate, boltd)
        ws_mandat.write(rw + 7, col + 1, 'Taux réalisé', bolth)
        ws_mandat.write(rw + 7, col + 2, self.realized_return_rate, boltd)
        ws_mandat.write(rw + 8, col + 1, 'Durée du mandat (ans)', bolth)
        ws_mandat.write(rw + 8, col + 2, self.duration_months / 12 , boltd)
        ws_mandat.write(rw + 9, col + 1, 'Date d\'effet', bolth)
        ws_mandat.write(rw + 9, col + 2, self.start_date.strftime('%d-%m-%Y'), boltd)
        ws_mandat.write(rw + 10, col + 1, 'Date d\'échéance', bolth)
        ws_mandat.write(rw + 10, col + 2, self.maturity_date.strftime('%d-%m-%Y'), boltd)
        ws_mandat.write(rw + 11, col + 1, 'Date Coridor 14 jours', bolth)
        ws_mandat.write(rw + 11, col + 2, (self.maturity_date+ timedelta(self.days_corridor)).strftime('%d-%m-%Y'), boltd)
        ws_mandat.write(rw + 12, col + 1, 'Coupon', bolth)
        ws_mandat.write(rw + 12, col + 2, (self.initial_amount * self.target_return_rate) / 100, boltd)
        ws_mandat.write(rw + 13, col + 1, 'Principal + intérêt annuel', bolth)
        ws_mandat.write(rw + 13, col + 2, self.initial_amount + (self.initial_amount * self.target_return_rate) / 100, boltd)


        ws_mandat.merge_range(15, 0, 15, 6, f"Titres détenus", sous_type)


        rwstation = rw + 16
        colstation = col
        if position:
            ws_mandat.write(rwstation , colstation,'S/N',bolth)
            ws_mandat.write(rwstation, colstation + 1, 'Code Isin', bolth)
            ws_mandat.write(rwstation, colstation + 2, 'Type', bolth)
            ws_mandat.write(rwstation, colstation + 3, 'Sous type', bolth)
            ws_mandat.write(rwstation, colstation + 4, 'Pays', bolth)
            ws_mandat.write(rwstation, colstation + 5, 'Montant Nominal', bolth)
            ws_mandat.write(rwstation, colstation + 6, 'Quantité', bolth)

            rwstation += 1

            for i,pos in enumerate(position):
                ws_mandat.write(rwstation, colstation, i+1 , boltd)
                ws_mandat.write(rwstation, colstation + 1, pos.instrument_id.isin, boltd)
                ws_mandat.write(rwstation, colstation + 2, pos.instrument_id.instrument_type, boltd)
                if pos.instrument_id.instrument_type == 'bond':
                    bond = self.env['efund.vehicule.instrument.core.bond'].search([('instrument_id', '=', pos.instrument_id.id)])
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

            for  mvt in mvt_cash:
                ws_mandat.write(ws_flux, colstation, mvt.date.strftime('%d-%m-%Y'), boltd)
                ws_mandat.write(ws_flux, colstation + 1, f"{mvt.label}", boltd)
                ws_mandat.write(ws_flux, colstation + 2, mvt.amount, boltd) if '_out' in mvt.move_type else ws_mandat.write(ws_flux, colstation + 2, '', boltd)
                ws_mandat.write(ws_flux, colstation + 3, mvt.amount, boltd) if '_in' in mvt.move_type else ws_mandat.write(ws_flux, colstation + 3, '', boltd)
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



