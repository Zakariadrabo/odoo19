from datetime import date, timedelta

from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _

class FundInstrumentBond(models.Model):
    _name = "efund.fund.instrument.core.bond"
    _inherits = {'efund.fund.instrument.core': 'instrument_id'}

    instrument_id = fields.Many2one('efund.fund.instrument.core', required=True,ondelete='cascade')

    bond_type = fields.Selection([ ('ota', 'OTA'),('bta', 'BTA'),('op', 'Obligation Privée')])
    currency_id = fields.Many2one(related='instrument_id.currency_id')
    face_value = fields.Monetary(string="Valeur nominale")
    issue_date = fields.Date(string="Date d'émission")
    value_date = fields.Date(string="Date de valeur")
    coupon_rate = fields.Float(string="Taux du Coupon (%)")
    maturity_date = fields.Date(string="Échéance")
    remaining_date_to_maturity = fields.Char(string="Jours restants à la maturité", compute='_compute_days_to_next_coupon', store=True)
    remaining_date_to_coupon = fields.Char(string="Jours restants au prochain coupon", compute='_compute_days_to_next_coupon', store=True)
    valuation_method = fields.Selection([('actuarial', 'Actuarielle'), ('linear', 'Linéaire')])
    coupon_frequency = fields.Selection( [('annual', 'Annuel'), ('semi_annual', 'Semestriel'), ('quarterly', 'Trimestriel'),
         ('monthly', 'Mensuel'), ('at_maturity', 'A Maturité'), ], string='Fréquence des Coupons', default='annual', )
    coupon_calculation_date = fields.Date(string='Date dernier calcul des coupons', default=fields.Date.today, help="Date du dernier calcul des coupons")
    next_coupon_date = fields.Date(string='Date prochain Coupon', compute='_compute_coupon_schedule', store=True, help="Date du prochain paiement de coupon")


    #coupon_ids = fields.One2many(...)
    #amortization_ids = fields.One2many(...)

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

    @api.depends('next_coupon_date')
    def _compute_days_to_next_coupon(self):
        today = date.today()
        for rec in self:
            if rec.next_coupon_date:
                result = rec.date_diff_ymd(today, rec.next_coupon_date)
                result1 = rec.date_diff_ymd(today, rec.maturity_date)

                rec.remaining_date_to_coupon = f"{result.get('years')} ans {result.get('months')} mois {result.get('days')} jours"
                rec.remaining_date_to_maturity = f"{result1.get('years')} ans {result1.get('months')} mois {result1.get('days')} jours"

