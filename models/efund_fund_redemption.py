from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundRedemption(models.Model):
    _name = 'efund.fund.redemption'
    _inherit = 'efund.operation.base'

    cash_account_id = fields.Many2one('efund.account.cash', required=True)
    part_account_id = fields.Many2one('efund.account.part', required=True)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')
    amount = fields.Monetary(string="montant", currency_field="currency_id")
    parts = fields.Float(string="Nombre de parts")

    def action_execute(self):
        self.env['efund.account.part.move'].create({
            'part_account_id': self.part_account_id.id,
            'move_type': 'redemption',
            'parts': self.parts,
        })
        self.env['efund.account.cash.move'].create({
            'cash_account_id': self.cash_account_id.id,
            'move_type': 'redemption',
            'amount': self.amount,
        })
        self.state = 'executed'
