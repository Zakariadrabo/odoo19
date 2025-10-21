from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundInstrument(models.Model):
    _name = "efund.fund.instrument"
    _description = "Instrument financier"



    name = fields.Char(string='Libellé', required=True)
    isin = fields.Char(string='Code ISIN', index=True)
    ticker = fields.Char()
    instrument_type = fields.Selection([('eq','Equity'),('bond','Bond'),('cash','Cash'),('other','Other')], default='other')
    currency_id = fields.Many2one('res.currency', string="Devise")
    custodian_code = fields.Char()
    market_price_source = fields.Char()