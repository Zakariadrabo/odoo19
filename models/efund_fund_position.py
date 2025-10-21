from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FundPosition(models.Model):
    _name = "efund.fund.position"
    _description = "Position d'un fonds sur un instrument"
    _rec_name = "display_name"

    fund_id = fields.Many2one('res.company', domain="[('company_type','=','fonds')]", required=True, index=True)
    instrument_id = fields.Many2one('efund.fund.instrument', required=True, index=True)
    quantity = fields.Float(default=0.0)
    avg_cost = fields.Monetary(currency_field='currency_id')
    market_value = fields.Monetary(currency_field='currency_id', compute='_compute_market_value', store=True)
    valuation_date = fields.Date(index=True)
    currency_id = fields.Many2one('res.currency', string="Devise")
    display_name = fields.Char(compute='_compute_display')

    @api.depends('quantity', 'avg_cost')
    def _compute_market_value(self):
        for pos in self:
            pos.market_value = pos.quantity * (pos.avg_cost or 0.0)

    def _compute_display(self):
        for rec in self:
            rec.display_name = f"{rec.fund_id.name} / {rec.instrument_id.name}"
