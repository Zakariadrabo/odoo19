from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FundValuationFee(models.Model):
    _name = "efund.fund.valuation.fee"
    _description = "Fund Valuation Fee"

    valuation_id = fields.Many2one("efund.fund.valuation", required=True, ondelete="cascade")
    fee_type = fields.Selection([
        ('management', 'Management Fee'),
        ('custody', 'Custody Fee'),
        ('audit', 'Audit Fee'),
        ('other', 'Other')
    ], string="Fee Type", required=True)
    description = fields.Char()
    amount = fields.Monetary(currency_field='currency_id')
    currency_id = fields.Many2one(related='valuation_id.currency_id', store=True, readonly=True)
