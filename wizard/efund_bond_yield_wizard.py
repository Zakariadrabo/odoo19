from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import math


class FundBondYieldWizard(models.TransientModel):
    _name = 'efund.bond.yield.wizard'
    _description = 'Bond Yield Calculation Wizard'

    # === PARAMÈTRES D'ENTRÉE ===
    instrument_id = fields.Many2one('efund.fund.instrument', required=True)

    calculation_date = fields.Date(
        string='Calculation Date',
        required=True,
        default=fields.Date.context_today
    )

    market_price = fields.Monetary(
        string='Market Price',
        currency_field='currency_id',
        required=True,
        help="Prix de marché actuel (en % de la valeur nominale)"
    )

    currency_id = fields.Many2one(
        related='instrument_id.currency_id',
        string='Currency'
    )

    # === RÉSULTATS DE CALCUL ===
    ytm = fields.Float(
        string='Yield to Maturity (YTM)',
        digits=(16, 4),
        compute='_compute_yields',
        help="Rendement à l'échéance en %"
    )

    current_yield = fields.Float(
        string='Current Yield',
        digits=(16, 4),
        compute='_compute_yields',
        help="Rendement courant = coupon / prix marché"
    )

    modified_duration = fields.Float(
        string='Modified Duration',
        digits=(16, 6),
        compute='_compute_duration',
        help="Sensibilité du prix aux variations de taux"
    )

    macaulay_duration = fields.Float(
        string='Macaulay Duration',
        digits=(16, 6),
        compute='_compute_duration',
        help="Durée moyenne pondérée des flux"
    )

    convexity = fields.Float(
        string='Convexity',
        digits=(16, 6),
        compute='_compute_convexity',
        help="Mesure de la courbure de la relation prix/rendement"
    )

    # === INFORMATIONS D'AFFICHAGE ===
    dirty_price = fields.Monetary(
        string='Dirty Price',
        currency_field='currency_id',
        compute='_compute_dirty_price',
        help="Prix incluant les intérêts courus"
    )

    accrued_interest = fields.Monetary(
        string='Accrued Interest',
        currency_field='currency_id',
        compute='_compute_dirty_price'
    )

    days_to_maturity = fields.Integer(
        string='Days to Maturity',
        compute='_compute_days'
    )

    years_to_maturity = fields.Float(
        string='Years to Maturity',
        digits=(16, 4),
        compute='_compute_days'
    )

    # === MÉTHODES DE CALCUL ===

    @api.depends('calculation_date', 'instrument_id', 'market_price')
    def _compute_yields(self):
        """Calcule les différents types de yield"""
        for wizard in self:
            if not wizard.instrument_id or not wizard.market_price:
                wizard.ytm = 0.0
                wizard.current_yield = 0.0
                return

            bond = wizard.instrument_id

            # 1. Current Yield (simple)
            if wizard.market_price > 0:
                wizard.current_yield = (bond.coupon_rate / wizard.market_price) * 100
            else:
                wizard.current_yield = 0.0

            # 2. Yield to Maturity (YTM) - calcul itératif
            wizard.ytm = wizard._calculate_ytm()

    def _calculate_ytm(self):
        """Calcule le Yield to Maturity par approximation itérative"""
        bond = self.instrument_id

        # Prix en valeur nominale (ex: 102.5 pour 102.5% du nominal)
        price_percent = self.market_price

        # Flux de trésorerie
        cash_flows = self._get_cash_flows()

        if not cash_flows:
            return 0.0

        # Utilise la méthode de Newton-Raphson pour résoudre l'équation
        # P = Σ(CF_t / (1+YTM)^t)

        # Estimation initiale
        ytm_guess = bond.coupon_rate / 100.0  # Commence par le taux du coupon
        tolerance = 0.000001  # Précision à 0.0001%
        max_iterations = 100

        for i in range(max_iterations):
            # Calcul du prix avec le YTM estimé
            calculated_price = sum(
                cf['amount'] / ((1 + ytm_guess) ** cf['years'])
                for cf in cash_flows
            )

            # Calcul de la dérivée (duration modifiée)
            derivative = sum(
                -cf['years'] * cf['amount'] / ((1 + ytm_guess) ** (cf['years'] + 1))
                for cf in cash_flows
            )

            # Erreur
            price_error = calculated_price - price_percent

            # Critère de convergence
            if abs(price_error) < tolerance:
                break

            # Mise à jour Newton-Raphson: ytm_new = ytm_old - f(ytm)/f'(ytm)
            if derivative != 0:
                ytm_guess = ytm_guess - price_error / derivative
            else:
                # Fallback: méthode de la bissection
                ytm_guess = ytm_guess * 0.99

        # Convertir en pourcentage
        return ytm_guess * 100

    def _get_cash_flows(self):
        """Génère les flux de trésorerie de l'obligation"""
        cash_flows = []
        bond = self.instrument_id

        # Date de calcul
        calc_date = self.calculation_date

        # Générer les coupons
        coupon_dates = self._generate_coupon_dates()

        for coupon_date in coupon_dates:
            if coupon_date <= calc_date:
                continue  # Coupons passés

            # Années jusqu'au paiement
            years = (coupon_date - calc_date).days / 365.0

            if coupon_date == bond.maturity_date:
                # Dernier flux: coupon + principal
                amount = bond.face_value * (bond.coupon_rate / 100) + bond.face_value
            else:
                # Coupon normal
                amount = bond.face_value * (bond.coupon_rate / 100)

            cash_flows.append({
                'date': coupon_date,
                'years': years,
                'amount': amount,
                'type': 'maturity' if coupon_date == bond.maturity_date else 'coupon'
            })

        return cash_flows

    def _generate_coupon_dates(self):
        """Génère toutes les dates de coupon jusqu'à maturité"""
        dates = []
        bond = self.instrument_id
        current_date = bond.value_date

        while current_date < bond.maturity_date:
            next_date = bond._get_next_coupon_date(current_date)
            if next_date > bond.maturity_date:
                dates.append(bond.maturity_date)
                break
            dates.append(next_date)
            current_date = next_date

        # S'assurer que la maturité est incluse
        if bond.maturity_date not in dates:
            dates.append(bond.maturity_date)

        return dates

    @api.depends('calculation_date', 'instrument_id', 'market_price', 'ytm')
    def _compute_duration(self):
        """Calcule les différentes mesures de duration"""
        for wizard in self:
            if not wizard.instrument_id or wizard.ytm == 0:
                wizard.modified_duration = 0.0
                wizard.macaulay_duration = 0.0
                continue

            bond = wizard.instrument_id
            ytm_decimal = wizard.ytm / 100.0
            cash_flows = wizard._get_cash_flows()

            if not cash_flows:
                wizard.modified_duration = 0.0
                wizard.macaulay_duration = 0.0
                continue

            # Calcul du prix
            price = sum(
                cf['amount'] / ((1 + ytm_decimal) ** cf['years'])
                for cf in cash_flows
            )

            # Macaulay Duration
            macaulay_sum = sum(
                cf['years'] * cf['amount'] / ((1 + ytm_decimal) ** cf['years'])
                for cf in cash_flows
            )

            wizard.macaulay_duration = macaulay_sum / price if price > 0 else 0.0

            # Modified Duration
            wizard.modified_duration = wizard.macaulay_duration / (1 + ytm_decimal)

    @api.depends('calculation_date', 'instrument_id', 'market_price', 'ytm')
    def _compute_convexity(self):
        """Calcule la convexité de l'obligation"""
        for wizard in self:
            if not wizard.instrument_id or wizard.ytm == 0:
                wizard.convexity = 0.0
                continue

            bond = wizard.instrument_id
            ytm_decimal = wizard.ytm / 100.0
            cash_flows = wizard._get_cash_flows()

            if not cash_flows:
                wizard.convexity = 0.0
                continue

            # Calcul du prix
            price = sum(
                cf['amount'] / ((1 + ytm_decimal) ** cf['years'])
                for cf in cash_flows
            )

            # Calcul de la convexité
            convexity_sum = sum(
                cf['years'] * (cf['years'] + 1) * cf['amount'] / ((1 + ytm_decimal) ** (cf['years'] + 2))
                for cf in cash_flows
            )

            wizard.convexity = convexity_sum / price if price > 0 else 0.0

    @api.depends('calculation_date', 'instrument_id', 'market_price')
    def _compute_dirty_price(self):
        """Calcule le dirty price (prix + intérêts courus)"""
        for wizard in self:
            if not wizard.instrument_id:
                wizard.dirty_price = 0.0
                wizard.accrued_interest = 0.0
                continue

            bond = wizard.instrument_id
            calc_date = wizard.calculation_date

            # Calcul des intérêts courus
            days_in_year = 360  # Convention Actual/360
            if bond.value_date <= calc_date:
                days_accrued = (calc_date - bond.value_date).days
                daily_rate = bond.coupon_rate / 100 / days_in_year
                wizard.accrued_interest = bond.face_value * daily_rate * days_accrued
            else:
                wizard.accrued_interest = 0.0

            # Dirty price = clean price + intérêts courus
            wizard.dirty_price = wizard.market_price + wizard.accrued_interest

    @api.depends('calculation_date', 'instrument_id')
    def _compute_days(self):
        """Calcule les jours/années jusqu'à maturité"""
        for wizard in self:
            if not wizard.instrument_id:
                wizard.days_to_maturity = 0
                wizard.years_to_maturity = 0.0
                continue

            bond = wizard.instrument_id
            calc_date = wizard.calculation_date

            if calc_date >= bond.maturity_date:
                wizard.days_to_maturity = 0
                wizard.years_to_maturity = 0.0
            else:
                wizard.days_to_maturity = (bond.maturity_date - calc_date).days
                wizard.years_to_maturity = wizard.days_to_maturity / 365.0

    # === ACTIONS ===
    def action_calculate(self):
        """Lance le calcul et affiche les résultats"""
        self.ensure_one()

        # Forcer le recalcul
        self._compute_yields()
        self._compute_duration()
        self._compute_convexity()
        self._compute_dirty_price()
        self._compute_days()

        # Retourne la même vue (pour afficher les résultats)
        return {
            'type': 'ir.actions.act_window',
            'name': f'Yield Calculation - {self.instrument_id.name}',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def action_export_results(self):
        """Exporte les résultats vers PDF/Excel"""
        self.ensure_one()

        # Vous pourriez implémenter l'export ici
        raise ValidationError(_("Export feature not yet implemented."))