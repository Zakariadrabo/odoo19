import base64
import csv
import io
import json
import logging
from datetime import date, timedelta, datetime

from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from zeep.exceptions import ValidationError

_logger = logging.getLogger(__name__)

class FundInstrumentBond(models.Model):
    _name = "efund.vehicule.instrument.core.bond"
    _inherits = {'efund.vehicule.instrument.core': 'instrument_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']

    instrument_id = fields.Many2one('efund.vehicule.instrument.core', required=True,ondelete='cascade')

    bond_type = fields.Selection([ ('ota', 'OTA'),('bta', 'BTA'),('op', 'Obligation Privée')], string="Type d'obligation")
    currency_id = fields.Many2one(related='instrument_id.currency_id')
    issue_amount = fields.Monetary(string='Montant Emission', tracking=True, help="Montant total émis par l'émetteur")
    face_value = fields.Monetary(string="Valeur nominale")
    issue_date = fields.Date(string="Date d'émission")
    value_date = fields.Date(string="Date de valeur")
    coupon_rate = fields.Float(string="Taux du Coupon (%)")
    rate_net = fields.Float(string="Taux net (%)", compute='_compute_rate_net', store=True)
    maturity_date = fields.Date(string="Échéance")
    remaining_date_to_maturity = fields.Char(string="Jours restants à la maturité", store=True)
    remaining_date_to_coupon = fields.Char(string="Jours restants au prochain coupon",store=True)
    coupon_frequency = fields.Selection( [('annual', 'Annuel'), ('semi_annual', 'Semestriel'), ('quarterly', 'Trimestriel'),
         ('monthly', 'Mensuel'), ('at_maturity', 'A Maturité'), ], string='Fréquence', default='annual', )
    coupon_calculation_date = fields.Date(string='Date dernier calcul des coupons', default=fields.Date.today, help="Date du dernier calcul des coupons")
    next_coupon_date = fields.Date(string='Date prochain Coupon', compute='_compute_coupon_schedule', store=True, help="Date du prochain paiement de coupon")
    calculeted_base = fields.Selection([('360', '360'), ('365', '365')], string='Base de calculé', default='365')
    amortization_type = fields.Selection([('in_fine', "In Fine (Bullet)"), ('constant_annuity', "Annuités Constantes"),
                                          ('constant_principal', "Amortissement Constant"),
                                          ('custom_schedule', "Échéancier Personnalisé"),
                                          ], string="Type d'Amortissement", default="in_fine")

    days_to_maturity = fields.Integer(string="Jours restants", compute="_compute_days_to_maturity", store=True)


    last_validated_price = fields.Float(string="Dernier cours validé")
    last_price_date = fields.Date( string="Date dernier cours")

    # Champ One2many
    coupon_ids = fields.One2many('efund.bond.coupon', 'bond_id', string="Calendrier des coupons")
    bond_amortization_ids = fields.One2many('efund.bond.amortization', 'bond_id', string="calendrier des amortissements")



    def _cron_update_maturity_days(self):
        """Méthode appelée par le Cron chaque nuit"""
        records = self.search([('maturity_date', '!=', False)])
        # On force le recalcul
        records._compute_days_to_maturity()

    @api.depends('coupon_rate', 'tax_rate')
    def _compute_rate_net(self):
        for rec in self:
            rec.rate_net = rec.coupon_rate * (1- rec.tax_rate/100)


    @api.depends('coupon_frequency', 'coupon_calculation_date')
    def _compute_coupon_schedule(self):
        """Calcule toutes les informations de coupon en une passe"""
        today = fields.Date.today()

        for bond in self:
            first_coupon_date = fields.Date.today()
            if bond.issue_date and bond.value_date and bond.coupon_frequency:
                first_coupon_date = bond._get_next_coupon_date(bond.value_date)
            else:
                first_coupon_date = False

            # Réinitialisation
            bond.next_coupon_date = False

            # Vérification des prérequis
            if not first_coupon_date:
                continue

            # Calcul de la prochaine date
            next_date = first_coupon_date

            # Avancer jusqu'à dépasser la date actuelle
            while next_date <= today:
                next_date = bond._add_coupon_period(next_date)

            # Mise à jour des champs
            bond.next_coupon_date = next_date

            #if next_date and next_date > today:
            #    bond.days_to_next_coupon = (next_date - today).days

    def _add_coupon_period(self, date):
        """Ajoute une période de coupon à une date"""
        return self._get_next_coupon_date(date)

    def _get_next_coupon_date(self, from_date):
        """Retourne la prochaine date de coupon après une date donnée"""
        self.ensure_one()

        if self.coupon_frequency == 'annual':
            return from_date + relativedelta(years=1)
        elif self.coupon_frequency == 'semi_annual':
            return from_date + relativedelta(months=6)
        elif self.coupon_frequency == 'quarterly':
            return from_date + relativedelta(months=3)
        elif self.coupon_frequency == 'monthly':
            return from_date + relativedelta(months=1)
        else:  # at_maturity
            return self.maturity_date

    def date_diff_ymd(self, start_date, end_date):
        """
        Calcule la différence calendaire exacte entre deux dates
        en années, mois et jours (bissextile inclus).        """

        if end_date < start_date:
            raise ValueError("end_date doit être postérieure à start_date")

        years = end_date.year - start_date.year
        months = end_date.month - start_date.month
        days = end_date.day - start_date.day

        # Ajustement des jours négatifs
        if days < 0:
            months -= 1
            # dernier jour du mois précédent end_date
            last_day_prev_month = (end_date.replace(day=1) - timedelta(days=1)).day
            days += last_day_prev_month

        # Ajustement des mois négatifs
        if months < 0:
            years -= 1
            months += 12

        return {
            'years': years,
            'months': months,
            'days': days,
        }


    @api.depends('instrument_id',)
    def _compute_days_to_maturity(self):
        today = date.today(),
        for rec in self:
            serviceEngine = self.env['efund.service']
            res = serviceEngine.get_coupon_period(
                    order_date= date.today(),
                    maturity_date=rec.maturity_date,
                    frequency=1)
            _logger.info(f"************ res.get('next_coupon') {res.get('next_coupon')}")

            if res.get('next_coupon'):
                result = rec.date_diff_ymd(today, res.get('next_coupon') )
                result1 = rec.date_diff_ymd(today, rec.maturity_date)
                rec.remaining_date_to_coupon = f"{result.get('years')} ans {result.get('months')} mois {result.get('days')} jours"
                rec.remaining_date_to_maturity = f"{result1.get('years')} ans {result1.get('months')} mois {result1.get('days')} jours"

    def action_compute_coupons(self):
        self.ensure_one()
        service = self.env['efund.service']
        # 1. Nettoyage des anciens coupons non payés
        self.coupon_ids.filtered(lambda c: c.state == 'draft').unlink()

        # 2. Appel du générateur
        coupons_data = service.generate_coupon_schedule(
            self.issue_amount,
            self.coupon_rate,
            self.coupon_frequency,
            self.value_date,
            self.maturity_date,
            int(self.calculeted_base)
        )

        # 3. Création des enregistrements
        vals_list = []
        for i, line in enumerate(coupons_data, 1):
            vals_list.append({
                'bond_id': self.id,
                'coupon_number': i,
                'date_debut': line.get('date_debut'),
                'date_fin': line.get('date_fin'),
                'date_paiement': line.get('date_fin'),
                'nb_jours': line.get('jours'),
                'montant': line.get('montant'),
                'state': 'draft',
            })
        self.env['efund.bond.coupon'].create(vals_list)

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



    def action_view_coupons(self):
        pass
    def action_view_prices(self):
        pass
    def action_view_amortizations(self):
        pass
    def action_recompute_coupons(self):
        pass

    def action_open_amortization_wizard(self):
        self.ensure_one()
        service = self.env['efund.service']
        self.bond_amortization_ids.unlink()

        # 2. Appel du générateur
        amortization_data = service.generate_amortization_schedule(
            self.issue_amount,
            self.coupon_rate,
            self.coupon_frequency,
            self.value_date,
            self.maturity_date,
            int(self.calculeted_base),
            self.amortization_type
        )
        # 3. Création des enregistrements
        vals_list = []

        for i, line in enumerate(amortization_data, 1):
            vals_list.append({
                'bond_id': self.id,
                'installment_number': i,
                'due_date': line.get('next_date'),
                'opening_principal': line.get('capital_initial'),
                'coupon_amount': line.get('interet'),
                'principal_repayment': line.get('amortissement'),
                'annuite': line.get('annuite'),
                'closing_principal': line.get('capital_restant'),
                'state': 'draft',
            })
        self.env['efund.bond.amortization'].create(vals_list)

        # Message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Amortissement de l'instrument financier"),
                'message': _('Génération réussi .') ,
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.client',
                    'tag': 'reload',
                }

            }
        }

    def generate_amortization_schedule(self,
            montant,
            taux_annuel,
            frequence,
            date_valeur,
            date_maturite,
            base_calcul=365,
            type_amortissement='in_fine'
    ):
        """
        Génère un tableau d'amortissement générique
        """

        freq_map = {
            'monthly': 12,
            'quarterly': 4,
            'semi_annual': 2,
            'annual': 1,
        }

        if frequence not in freq_map:
            raise ValueError("Fréquence invalide")

        periods_per_year = freq_map[frequence]
        taux_periodique = taux_annuel / 100 / periods_per_year

        # Calcul du nombre total de périodes
        total_periods = int(
            (date_maturite.year - date_valeur.year) * periods_per_year +
            (date_maturite.month - date_valeur.month) / (12 / periods_per_year)
        )

        capital_restant = montant
        schedule = []
        annuite = 0

        # Annuité constante
        if type_amortissement == 'annuite_constante':
            annuite = (
                    montant * taux_periodique /
                    (1 - (1 + taux_periodique) ** -total_periods)
            )

        capital_constant = (
            montant / total_periods
            if type_amortissement == 'capital_constant'
            else 0
        )

        current_date = date_valeur

        for period in range(1, total_periods + 1):
            next_date = current_date + relativedelta(
                months=int(12 / periods_per_year)
            )

            days = (next_date - current_date).days

            interet = (
                    capital_restant * taux_periodique #taux_annuel / 100 * days / base_calcul
            )

            if type_amortissement == 'in_fine':
                amortissement = montant if period == total_periods else 0
                annuite_period = interet + amortissement

            elif type_amortissement == 'annuite_constante':
                amortissement = annuite - interet
                annuite_period = annuite

            elif type_amortissement == 'capital_constant':
                amortissement = capital_constant
                annuite_period = interet + amortissement

            else:
                raise ValueError("Type d'amortissement invalide")

            capital_restant -= amortissement

            schedule.append({
                'periode': period,
                'date_debut': current_date,
                'date_fin': next_date,
                'next_date': next_date,
                'capital_initial': round(capital_restant + amortissement, 2),
                'interet': round(interet, 2),
                'amortissement': round(amortissement, 2),
                'annuite': round(annuite_period, 2),
                'capital_restant': round(max(capital_restant, 0), 2),
            })

            current_date = next_date

        return schedule

    def generate_amortization_table(self,montant, taux, frequence, date_valeur, date_maturite, base_calcul, type_amort):
        # Initialisation
        if isinstance(date_valeur, str):
            date_valeur = datetime.strptime(date_valeur, '%Y-%m-%d').date()
        if isinstance(date_maturite, str):
            date_maturite = datetime.strptime(date_maturite, '%Y-%m-%d').date()

        freq_months = {'mensuel': 1, 'trimestriel': 3, 'semestriel': 6, 'annuel': 12}
        step = freq_months.get(frequence, 12)

        # 1. Calcul du nombre total d'échéances
        nb_echeances = 0
        tmp_date = date_valeur
        while tmp_date < date_maturite:
            tmp_date += relativedelta(months=step)
            nb_echeances += 1

        schedule = []
        capital_restant = montant
        current_date = date_valeur
        taux_periodique = (taux / 100) / (12 / step)

        for i in range(1, nb_echeances + 1):
            next_date = current_date + relativedelta(months=step)
            if next_date > date_maturite: next_date = date_maturite

            jours = (next_date - current_date).days
            interet = capital_restant * (taux / 100) * (jours / base_calcul)

            principal = 0

            if type_amort == 'in_fine':
                # Capital remboursé seulement à la dernière échéance
                principal = montant if i == nb_echeances else 0

            elif type_amort == 'constant_principal':
                # Capital divisé équitablement
                principal = montant / nb_echeances

            elif type_amort == 'constant_annuity':
                # Formule de l'annuité : A = P * r / (1 - (1+r)^-n)
                annuite_constante = montant * taux_periodique / (1 - (1 + taux_periodique) ** -nb_echeances)
                principal = annuite_constante - interet

            # Ajustement pour la dernière échéance (arrondis)
            if i == nb_echeances:
                principal = capital_restant

            annuite = principal + interet
            capital_restant -= principal

            schedule.append({
                'rang': i,
                'date': next_date,
                'principal': round(principal, 2),
                'interet': round(interet, 2),
                'annuite': round(annuite, 2),
                'capital_restant_fin': round(max(0, capital_restant), 2)
            })
            current_date = next_date

        return schedule

    def action_import_price_today(self):
        self.ensure_one()

        # Créer un wizard d'import simple pour cet instrument
        return {
            'name': _('Importer le cours'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.instrument.import.price.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_instrument_id': self.id,
                'default_price_date': fields.Date.today(),
            }
        }

    def action_open_simulation_wizard(self):
        return {
            'name': _('Simulation du Cours'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.bond.simulation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_bond_id': self.id,
                'default_date_start': fields.Date.today(),
            }
        }
