from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class EfundAccountCashMove(models.Model):
    _name = 'efund.account.cash.move'
    _description = 'Mouvements compte espèces'

    cash_account_id = fields.Many2one('efund.account.cash', required=True)
    fund_id = fields.Many2one(related='cash_account_id.fund_id', store=True)
    mandate_id = fields.Many2one('efund.mandate', string="Mandat", index=True)
    currency_id = fields.Many2one(related='fund_id.currency_id')
    investor_id = fields.Many2one(related='cash_account_id.investor_id', store=True)
    move_type = fields.Selection(
        [('deposit', 'Dépôt'), ('withdraw', 'Rétrait'), ('refund', 'Remboursement'), ('coupon', 'Coupon mandat'),
         ('subscription_net', 'Souscription – montant investi'),('subscription_fee', 'Frais de souscription'),
         ('redemption_net', 'Rachat – montant payé'), ('redemption_fee', 'Frais de rachat'),
         ('capital_return', 'Remboursement capital'), ], required=True)

    amount = fields.Monetary(required=True, currency_field='currency_id')
    date = fields.Datetime(default=fields.Datetime.now)
