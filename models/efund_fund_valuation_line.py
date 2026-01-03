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
    accrued_interest = fields.Monetary(string="Accrued Interest",currency_field='currency_id',help="Interest accrued but not yet received on interest-bearing instruments (bonds, deposits, etc.)")

    @api.depends("quantity", "unit_price", "accrued_interest")
    def _compute_market_value(self):
        for rec in self:
            q = rec.quantity or 0.0
            up = rec.unit_price or 0.0
            acc = rec.accrued_interest or 0.0
            rec.market_value = q * up + acc

    def name_get(self):
        res = []
        for rec in self:
            name = "%s - %s" % (rec.instrument_id.name or rec.isin or "Instrument", rec.valuation_id.name or "")
            res.append((rec.id, name))
        return res
