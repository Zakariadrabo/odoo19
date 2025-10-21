from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FundValuationLine(models.Model):
    _name = "efund.fund.valuation.line"
    _description = "Fund Valuation Line"

    valuation_id = fields.Many2one("efund.fund.valuation", required=True, ondelete="cascade")
    instrument_id = fields.Many2one("efund.fund.instrument", string="Instrument", required=True)
    quantity = fields.Float(string="Quantity", required=True)
    unit_price = fields.Monetary(string="Market Price", required=True, currency_field='currency_id')
    market_value = fields.Monetary(string="Market Value", compute="_compute_market_value", store=True, currency_field='currency_id')
    currency_id = fields.Many2one(related='valuation_id.currency_id', store=True, readonly=True)

    @api.depends('quantity', 'unit_price')
    def _compute_market_value(self):
        for rec in self:
            rec.market_value = rec.quantity * rec.unit_price
