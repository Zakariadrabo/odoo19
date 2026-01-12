import logging
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from dateutil.relativedelta import relativedelta
import math

_logger = logging.getLogger(__name__)


class BondAmortizationWizardLine(models.TransientModel):
    """Lignes pour échéancier personnalisé"""
    _name = "efund.bond.amortization.wizard.line"
    _description = "Ligne d'échéancier personnalisé"
    _order = "period_number"

    wizard_id = fields.Many2one('efund.bond.amortization.wizard', required=True)
    period_number = fields.Integer(string="Période", required=True)
    fixed_principal_amount = fields.Float(string="Montant Principal Fixe")
    percentage_principal = fields.Float(string="Pourcentage du Principal (%)")

    @api.onchange('fixed_principal_amount')
    def _onchange_fixed_principal_amount(self):
        if self.fixed_principal_amount:
            self.percentage_principal = 0.0

    @api.onchange('percentage_principal')
    def _onchange_percentage_principal(self):
        if self.percentage_principal:
            self.fixed_principal_amount = 0.0


class BondAmortizationWizard(models.TransientModel):
    _name = "efund.bond.amortization.wizard"
    _description = "Generate Bond Amortization Schedule"

    instrument_id = fields.Many2one('efund.fund.instrument', required=True)
    currency_id = fields.Many2one(related='instrument_id.currency_id', string="Devise")
    nominal_amount = fields.Monetary(required=True, string="Montant nominal")
    coupon_rate = fields.Float(string="Taux coupon (%)", required=True)
    maturity_years = fields.Integer(required=True, string="maturité en Années ")

    # Ajout du type d'amortissement
    amortization_type = fields.Selection([
        ('in_fine', "In Fine (Bullet)"),
        ('constant_annuity', "Annuités Constantes"),
        ('constant_principal', "Amortissement Constant"),
        ('american', "Américain (Balloon)"),
        ('custom_schedule', "Échéancier Personnalisé"),
    ], string="Type d'Amortissement", default="in_fine", required=True)

    frequency = fields.Selection([
        ('annual', "Annual"),
        ('semiannual', "Semi-Annual"),
        ('quarterly', "Quarterly"),
        ('monthly', "Monthly"),
    ], default="annual", string="Fréquence des paiements")

    start_date = fields.Date(required=True, string="Date de début")

    # Champs conditionnels pour certains types d'amortissement
    balloon_percentage = fields.Float(
        string="Pourcentage Balloon",
        help="Pourcentage du principal remboursé à l'échéance finale",
        default=100.0
    )

    grace_period = fields.Integer(
        string="Période de grâce (années)",
        help="Période sans remboursement de principal",
        default=0
    )
    """
    # Pour l'amortissement personnalisé
    custom_schedule_line_ids = fields.One2many(
        'efund.bond.amortization.wizard.line',
        'wizard_id',
        string="Échéancier Personnalisé"
    )
    """

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')

        if active_id:
            try:
                inst = self.env['efund.fund.instrument'].browse(int(active_id))
                if inst:
                    vals.update({
                        'instrument_id': inst.id,
                        'currency_id': inst.currency_id.id,
                        'nominal_amount': inst.face_value,
                        'coupon_rate': inst.coupon_rate,
                        'maturity_years': inst.maturity_years,
                        'frequency': inst.coupon_frequency,
                        'start_date': inst.issue_date,
                        'amortization_type': inst.amortization_type or 'in_fine',
                        'grace_period': inst.grace_period or 0,
                        'balloon_percentage': inst.balloon_percentage or 100.0,
                    })
            except Exception as e:
                _logger.error(f"Erreur dans default_get: {e}")

        return vals

    @api.onchange('amortization_type')
    def _onchange_amortization_type(self):
        """Ajuster les champs visibles selon le type d'amortissement"""
        if self.amortization_type == 'american':
            self.balloon_percentage = 100.0
        elif self.amortization_type == 'in_fine':
            self.balloon_percentage = 100.0
            self.grace_period = self.maturity_years

    def _calculate_constant_annuity_schedule(self, principal, period_rate, total_periods):
        """Calcul pour annuités constantes"""
        if period_rate == 0:
            annuity = principal / total_periods
        else:
            annuity = principal * period_rate / (1 - (1 + period_rate) ** -total_periods)

        schedule = []
        remaining_principal = principal

        for period in range(1, total_periods + 1):
            interest = remaining_principal * period_rate
            principal_repayment = annuity - interest
            closing_principal = remaining_principal - principal_repayment

            # Ajustement pour la dernière période
            if period == total_periods:
                principal_repayment = remaining_principal
                closing_principal = 0
                annuity = interest + principal_repayment

            schedule.append({
                'period': period,
                'interest': interest,
                'principal_repayment': principal_repayment,
                'total_payment': interest + principal_repayment,
                'opening_principal': remaining_principal,
                'closing_principal': closing_principal,
            })

            remaining_principal = closing_principal

        return schedule

    def _calculate_constant_principal_schedule(self, principal, period_rate, total_periods):
        """Calcul pour amortissement constant du principal"""
        principal_repayment_per_period = principal / total_periods
        schedule = []
        remaining_principal = principal

        for period in range(1, total_periods + 1):
            interest = remaining_principal * period_rate
            closing_principal = remaining_principal - principal_repayment_per_period

            schedule.append({
                'period': period,
                'interest': interest,
                'principal_repayment': principal_repayment_per_period,
                'total_payment': interest + principal_repayment_per_period,
                'opening_principal': remaining_principal,
                'closing_principal': closing_principal,
            })

            remaining_principal = closing_principal

        return schedule

    def _calculate_in_fine_schedule(self, principal, period_rate, total_periods, grace_periods=0):
        """Calcul pour amortissement in fine (bullet)"""
        schedule = []
        remaining_principal = principal

        for period in range(1, total_periods + 1):
            interest = remaining_principal * period_rate

            # Déterminer le remboursement du principal
            if period <= grace_periods:
                principal_repayment = 0
            elif period == total_periods:
                principal_repayment = remaining_principal
            else:
                principal_repayment = 0

            closing_principal = remaining_principal - principal_repayment

            schedule.append({
                'period': period,
                'interest': interest,
                'principal_repayment': principal_repayment,
                'total_payment': interest + principal_repayment,
                'opening_principal': remaining_principal,
                'closing_principal': closing_principal,
            })

            remaining_principal = closing_principal

        return schedule

    def _calculate_american_schedule(self, principal, period_rate, total_periods, balloon_percentage):
        """Calcul pour amortissement américain (balloon)"""
        schedule = []
        remaining_principal = principal
        final_balloon = principal * (balloon_percentage / 100.0)

        for period in range(1, total_periods + 1):
            interest = remaining_principal * period_rate

            if period == total_periods:
                principal_repayment = final_balloon
            else:
                principal_repayment = 0

            closing_principal = remaining_principal - principal_repayment

            schedule.append({
                'period': period,
                'interest': interest,
                'principal_repayment': principal_repayment,
                'total_payment': interest + principal_repayment,
                'opening_principal': remaining_principal,
                'closing_principal': closing_principal,
            })

            remaining_principal = closing_principal

        return schedule

    def _calculate_custom_schedule(self, principal, period_rate, total_periods):
        """Calcul basé sur l'échéancier personnalisé"""
        if not self.custom_schedule_line_ids:
            raise UserError(_("Veuillez définir l'échéancier personnalisé"))

        schedule = []
        remaining_principal = principal

        # Trier les lignes par période
        sorted_lines = self.custom_schedule_line_ids.sorted(key=lambda r: r.period_number)

        for line in sorted_lines:
            if line.period_number > total_periods:
                continue

            interest = remaining_principal * period_rate

            if line.fixed_principal_amount > 0:
                principal_repayment = line.fixed_principal_amount
            elif line.percentage_principal > 0:
                principal_repayment = principal * (line.percentage_principal / 100.0)
            else:
                principal_repayment = 0

            # Limiter le remboursement au principal restant
            principal_repayment = min(principal_repayment, remaining_principal)
            closing_principal = remaining_principal - principal_repayment

            schedule.append({
                'period': line.period_number,
                'interest': interest,
                'principal_repayment': principal_repayment,
                'total_payment': interest + principal_repayment,
                'opening_principal': remaining_principal,
                'closing_principal': closing_principal,
            })

            remaining_principal = closing_principal

        return schedule

    def _get_due_date(self, start_date, period, frequency_key, periods_per_year):
        """Calcul de la date d'échéance selon la fréquence"""
        if frequency_key == 'annual':
            return start_date + relativedelta(years=period)
        elif frequency_key == 'semiannual':
            return start_date + relativedelta(months=6 * period)
        elif frequency_key == 'quarterly':
            return start_date + relativedelta(months=3 * period)
        elif frequency_key == 'monthly':
            return start_date + relativedelta(months=period)
        else:
            return start_date + relativedelta(years=period)

    def action_generate_schedule(self):
        """Génère le tableau d'amortissement selon le type sélectionné"""
        self.ensure_one()
        instrument = self.instrument_id

        # Nettoyer les anciennes lignes
        instrument.bond_amortization_ids.unlink()

        # Mapping des fréquences
        freq_map = {
            'annual': 1,
            'semiannual': 2,
            'quarterly': 4,
            'monthly': 12,
        }

        frequency_key = self.frequency
        periods_per_year = freq_map.get(frequency_key, 1)
        total_periods = int(self.maturity_years * periods_per_year)

        # Calculer le nombre de périodes de grâce
        grace_periods = int(self.grace_period * periods_per_year)

        period_interest_rate = (self.coupon_rate / 100.0) / periods_per_year
        principal = self.nominal_amount

        # Sélectionner la méthode de calcul selon le type d'amortissement
        if self.amortization_type == 'constant_annuity':
            schedule_data = self._calculate_constant_annuity_schedule(
                principal, period_interest_rate, total_periods
            )
        elif self.amortization_type == 'constant_principal':
            schedule_data = self._calculate_constant_principal_schedule(
                principal, period_interest_rate, total_periods
            )
        elif self.amortization_type == 'in_fine':
            schedule_data = self._calculate_in_fine_schedule(
                principal, period_interest_rate, total_periods, grace_periods
            )
        elif self.amortization_type == 'american':
            schedule_data = self._calculate_american_schedule(
                principal, period_interest_rate, total_periods, self.balloon_percentage
            )
        elif self.amortization_type == 'custom_schedule':
            schedule_data = self._calculate_custom_schedule(
                principal, period_interest_rate, total_periods
            )
        else:
            raise UserError(_("Type d'amortissement non supporté"))

        # Créer les lignes d'amortissement
        amortization_lines = []
        for data in schedule_data:
            due_date = self._get_due_date(
                self.start_date,
                data['period'],
                frequency_key,
                periods_per_year
            )

            line_vals = {
                'instrument_id': instrument.id,
                'installment_number': data['period'],
                'due_date': due_date,
                'opening_principal': data['opening_principal'],
                'coupon_amount': data['interest'],
                'principal_repayment': data['principal_repayment'],
                'closing_principal': data['closing_principal'],
                'total_payment': data['total_payment'],
                'amortization_type': self.amortization_type,
            }

            amortization_lines.append(line_vals)

        # Créer toutes les lignes en une seule opération
        self.env["efund.bond.amortization"].create(amortization_lines)

        # Message de succès avec résumé
        total_interest = sum(line['coupon_amount'] for line in amortization_lines)
        total_principal = sum(line['principal_repayment'] for line in amortization_lines)

        message = _("""
        Tableau d'amortissement généré avec succès !

        Récapitulatif :
        • Nombre de périodes : %(periods)d
        • Type d'amortissement : %(amort_type)s
        • Intérêts totaux : %(interest).2f %(currency)s
        • Principal total : %(principal).2f %(currency)s
        • Montant total : %(total).2f %(currency)s
        """) % {
            'periods': total_periods,
            'amort_type': dict(self._fields['amortization_type'].selection).get(self.amortization_type),
            'interest': total_interest,
            'principal': total_principal,
            'total': total_interest + total_principal,
            'currency': self.currency_id.symbol,
        }

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Tableau généré'),
                'message': message,
                'type': 'success',
                'sticky': True,
                'next': {
                    'type': 'ir.actions.act_window_close'
                }
            }
        }