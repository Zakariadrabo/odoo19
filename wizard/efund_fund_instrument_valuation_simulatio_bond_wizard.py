from odoo import models, fields, api
from datetime import date

class InstrumentValuationSimulationWizard(models.TransientModel):
    _name = 'efund.fund.instrument.valuation.simulation.wizard'
    _description = 'Simulation de valorisation d’un instrument'

    instrument_id = fields.Many2one(
        'efund.fund.instrument',
        required=True,
        string="Instrument"
    )

    valuation_date = fields.Date(
        string="Date de valorisation",
        required=True,
        default=fields.Date.today
    )

    actuarial_value = fields.Monetary(
        string="Valeur actuarielle",
        currency_field='currency_id',
        compute='_compute_simulation'
    )

    linear_value = fields.Monetary(
        string="Valeur linéaire",
        currency_field='currency_id',
        compute='_compute_simulation'
    )

    effective_value = fields.Monetary(
        string="Valeur retenue",
        currency_field='currency_id',
        compute='_compute_simulation'
    )

    currency_id = fields.Many2one(
        related='instrument_id.currency_id',
        readonly=True
    )

    @api.depends('instrument_id', 'valuation_date')
    def _compute_simulation(self):
        for wiz in self:
            if not wiz.instrument_id or not wiz.valuation_date:
                wiz.actuarial_value = 0.0
                wiz.linear_value = 0.0
                wiz.effective_value = 0.0
                continue

            wiz.actuarial_value = wiz.instrument_id.compute_actuarial_value_at_date(
                wiz.valuation_date
            )

            wiz.linear_value = wiz.instrument_id.compute_linear_value_at_date(
                wiz.valuation_date
            )

            wiz.effective_value = wiz.instrument_id.compute_effective_value_at_date(
                wiz.valuation_date
            )
