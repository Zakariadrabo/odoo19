import logging

from odoo import models, fields, api
from datetime import timedelta
from dateutil.relativedelta import relativedelta
_logger = logging.getLogger(__name__)

class BondAmortizationWizard(models.TransientModel):
    _name = "efund.bond.amortization.wizard"
    _description = "Generate Bond Amortization Schedule"

    instrument_id = fields.Many2one('efund.fund.instrument', required=True)
    currency_id = fields.Many2one('res.currency', string="Devise", required=True)
    nominal_amount = fields.Monetary(required=True)
    coupon_rate = fields.Float(string="Annual Coupon Rate (%)", required=True)
    maturity_years = fields.Integer(required=True)
    frequency = fields.Selection([
        ('annual', "Annual"),
        ('semiannual', "Semi-Annual"),
        ('quarterly', "Quarterly"),
    ], default="annual")

    start_date = fields.Date(required=True)

    @api.model
    def default_get(self, fields_list):
        vals = super().default_get(fields_list)
        active_id = self.env.context.get('active_id')
        _logger.info(f"************ valeur Active_id : {active_id}")

        if active_id:
            try:
                active_id = int(active_id)  # Conversion explicite en entier
                inst = self.env['efund.fund.instrument'].browse(active_id)

                if inst:
                    _logger.info(f"instancie de bond {active_id} : {inst}")
                    vals.update({
                        'instrument_id': inst.id,
                        'currency_id': inst.currency_id.id,
                        'nominal_amount': inst.face_value,
                        'coupon_rate': inst.coupon_rate,
                        'maturity_years': inst.maturity_years,
                        'frequency': inst.coupon_frequency,
                        'start_date': inst.issue_date,
                    })
                else:
                    # Gérer le cas où l'instrument n'est pas trouvé
                    # Vous pouvez logger un avertissement ou lever une exception
                    self.env.logger.warning("Instrument avec l'ID %s non trouvé.", active_id)
                    # Ou, si c'est une erreur critique :
                    # raise UserError("Instrument avec l'ID %s non trouvé." % active_id)

            except ValueError:
                # Gérer le cas où active_id n'est pas un entier valide
                self.env.logger.warning("active_id n'est pas un entier valide: %s", active_id)
                # Ou, si c'est une erreur critique :
                # raise UserError("L'active_id n'est pas un entier valide: %s" % active_id)
            except Exception as e:
                # Gérer d'autres exceptions possibles (par exemple, si browse() échoue)
                self.env.logger.exception("Erreur lors de la récupération de l'instrument avec l'ID %s: %s", active_id,
                                          e)
                # Ou, si c'est une erreur critique :
                # raise UserError("Erreur lors de la récupération de l'instrument: %s" % e)
        else:
            # Gérer le cas où active_id est absent du contexte
            # Cela peut être normal dans certains cas, donc un avertissement peut suffire
            self.env.logger.warning("active_id est absent du contexte.")

        return vals

    def action_generate_schedule(self):
        instrument = self.instrument_id

        # Remove previous lines
        instrument.bond_amortization_ids.unlink()

        # Frequency mapping
        freq_map = {
            'annual': 1,
            'semi_annual': 2,
            'quarterly': 4,
            'monthly': 12,
        }

        # Note: Utilisez les mêmes clés que dans votre modèle efund.fund.instrument
        frequency_key = self.frequency
        # Si nécessaire, convertissez les clés
        if frequency_key == 'semiannual':
            frequency_key = 'semi_annual'  # Correspond à la sélection du modèle

        periods_per_year = freq_map.get(frequency_key, 1)
        total_periods = int(self.maturity_years * periods_per_year)
        period_interest_rate = (self.coupon_rate / 100) / periods_per_year

        principal = self.nominal_amount
        payment_per_period = principal * period_interest_rate  # Coupon only (bullet bond)

        _logger.info(
            f"**********nombre de période : {total_periods} : taux: {period_interest_rate} : paiement par periode : {payment_per_period}")

        for period in range(1, total_periods + 1):
            # Correction du calcul de la date
            if frequency_key == 'annual':
                due_date = self.start_date + relativedelta(years=period)
            elif frequency_key == 'semi_annual':
                due_date = self.start_date + relativedelta(months=6 * period)
            elif frequency_key == 'quarterly':
                due_date = self.start_date + relativedelta(months=3 * period)
            elif frequency_key == 'monthly':
                due_date = self.start_date + relativedelta(months=period)
            else:
                due_date = self.start_date + relativedelta(years=period)

            _logger.info(f"***** Période {period} : Date échéance: {due_date}")

            # Last period → repay principal
            principal_repayment = principal if period == total_periods else 0

            closing_principal = principal - principal_repayment

            self.env["efund.bond.amortization"].create({
                'instrument_id': instrument.id,
                'installment_number': period,
                'due_date': due_date,
                'opening_principal': principal,
                'coupon_amount': payment_per_period,
                'principal_repayment': principal_repayment,
                'closing_principal': closing_principal,
            })

            principal = closing_principal

        # Retourner une action pour fermer le wizard et afficher un message
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Tableau généré',
                'message': f"Le tableau d'amortissement a été généré avec {total_periods} périodes.",
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window_close'
                }
            }
        }

    """

    def action_generate_schedule(self):
        instrument = self.instrument_id

        # Remove previous lines
        instrument.bond_amortization_ids.unlink()

        # Frequency mapping
        freq_map = {
            'annual': 1,
            'semiannual': 2,
            'quarterly': 4,
            'monthly': 12,
        }

        periods_per_year = freq_map[self.frequency]
        total_periods = self.maturity_years * periods_per_year
        period_interest_rate = (self.coupon_rate / 100) / periods_per_year

        principal = self.nominal_amount
        payment_per_period = principal * period_interest_rate  # Coupon only (bullet bond)

        _logger.info(f"**********nombre de période : {total_periods} : taux: {period_interest_rate} : periode par an : {payment_per_period}")

        for period in range(1, total_periods + 1):
            due_date = self.start_date + relativedelta(months=12 * period / periods_per_year)
            _logger.info(f"***** je suis rentré dans le for:  {period} : {period_interest_rate}")

            # Last period → repay principal
            principal_repayment = principal if period == total_periods else 0

            closing_principal = principal - principal_repayment

            self.env["efund.bond.amortization"].create({
                'instrument_id': instrument.id,
                'installment_number': period,
                'due_date': due_date,
                'opening_principal': principal,
                'coupon_amount': payment_per_period,
                'principal_repayment': principal_repayment,
                'closing_principal': closing_principal,
            })
            _logger.info(f"********** j'ecris dans la table amortissement")

            principal = closing_principal
        """
