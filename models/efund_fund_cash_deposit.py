from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class CashDeposit(models.Model):
    _name = 'efund.fund.cash.deposit'
    _inherit = 'efund.operation.base'

    cash_account_id = fields.Many2one('efund.account.cash', required=True)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')
    amount = fields.Monetary(string="montant", currency_field="currency_id", required=True)
    payment_mode = fields.Selection([('bank', 'Bank Transfer'), ('cheque', 'Cheque'), ('cash', 'Cash')],
                                    string='Mode de paiement')

    def action_execute(self):
        self.env['efund.account.cash.move'].create({
            'cash_account_id': self.cash_account_id.id,
            'move_type': 'deposit',
            'amount': self.amount,
        })

