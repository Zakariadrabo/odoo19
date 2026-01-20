from odoo import models, fields, api, _


class FundInstrumentEquity(models.Model):
    _name = "efund.fund.instrument.core.equity"
    _description = "Instrument - Action"
    _inherits = {'efund.fund.instrument.core': 'instrument_id'}

    instrument_id = fields.Many2one('efund.fund.instrument.core', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='instrument_id.currency_id')

    # CHAMPS SPÉCIFIQUES AUX ACTIONS
    dividend_yield = fields.Float(string="Dividende")
    is_listed = fields.Boolean(string='Est Coté', default=False)
    listing_date = fields.Date(string='Date 1ère Cotation')
    sector = fields.Selection([
        ('agriculture', 'Agriculture'),
        ('industrie', 'Industrie')
    ])

    # MÉTHODES SPÉCIFIQUES
    def get_dividend_forecast(self):
        """Prévision des dividendes"""
        pass