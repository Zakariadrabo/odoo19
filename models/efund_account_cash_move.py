from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundAccountCashMove(models.Model):
    _name = 'efund.account.cash.move'
    _description = 'Mouvements compte espèces'

    cash_account_id = fields.Many2one(
        'efund.account.cash', required=True
    )

    fund_id = fields.Many2one(
        related='cash_account_id.fund_id',
        store=True
    )
    currency_id = fields.Many2one(related='fund_id.currency_id')

    investor_id = fields.Many2one(
        related='cash_account_id.investor_id',
        store=True
    )

    move_type = fields.Selection([
        ('deposit','Dépôt'),
        ('subscription','Souscription'),
        ('redemption','Rachat'),
        ('refund', 'Remboursement'),
    ], required=True)

    amount = fields.Monetary(required=True, currency_field='currency_id')
    date = fields.Datetime(default=fields.Datetime.now)
