from odoo import models, fields, api, _

class FundInstrumentFeeRule(models.Model):
    _name = 'efund.fund.instrument.fee.rule'
    _description = 'Règle de frais sur transaction instrument'

    name = fields.Char(required=True)

    # Ciblage instrument
    instrument_id = fields.Many2one('efund.fund.instrument',string="Instrument spécifique")
    fee_category = fields.Selection([('brokerage', 'Commission de courtage'),('market_tax', 'Taxe de marché'),('vat', 'TVA'),('other', 'Autre'),
    ], required=True)
    calculation_method = fields.Selection([('percentage', '% du montant'),('fixed', 'Montant fixe'),('per_unit', 'Par titre'),], required=True)
    rate = fields.Float(string="Taux (%)")
    amount = fields.Monetary(string="Montant fixe")
    currency_id = fields.Many2one( related='instrument_id.currency_id',store=True)

    # PRU
    capitalizable = fields.Boolean(string="À capitaliser dans le PRU", default=False )
    is_active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            'rule_scope_check',
            "CHECK (instrument_id IS NOT NULL OR instrument_type IS NOT NULL)",
            "La règle doit cibler un instrument ou un type d’instrument."
        )
    ]
