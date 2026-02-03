from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class EfundAccountCashMove(models.Model):
    _name = 'efund.investor.cash_account.move'
    _description = 'Mouvements compte espèces'

    name = fields.Char(string="Référence", default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.cash_account.move'))
    cash_account_id = fields.Many2one('efund.investor.cash_account', string="Compte Espèces", required=True)
    vehicule_id = fields.Many2one(related='cash_account_id.vehicule_id', store=True)
    currency_id = fields.Many2one(related='vehicule_id.currency_id')
    investor_id = fields.Many2one(related='cash_account_id.investor_id', store=True)
    move_type = fields.Selection(
        [('deposit', 'Dépôt'),('deposit_out','Déposit sur le mandat'), ('withdraw', 'Rétrait'), ('refund', 'Remboursement'),
         ('subscription', 'Souscription'),('subscription_fee', 'Frais de souscription'),
         ('redemption_net', 'Rachat – montant payé'), ('redemption_fee', 'Frais de rachat'),
         ('capital_return', 'Remboursement capital'),('coupon', 'Coupon') ], required=True)
    label = fields.Char(string="Libellé",)
    amount = fields.Monetary(required=True, currency_field='currency_id')
    date = fields.Datetime(default=fields.Datetime.now)
    state = fields.Selection([('accounted', 'Comptabilisé'), ('reconciled', 'Reconcilié')], default='accounted')

    # reconcilie investor cash move with fund cash move
    fund_cash_move_id = fields.Many2one('efund.fund.cash.move', string="Mouvement fund cash")
    subscription_id = fields.Many2one('efund.investor.subscription', string="Ordre de Souscription")
    redemption_id = fields.Many2one('efund.investor.redemption', string="Ordre de Rachat")
    deposit_id = fields.Many2one('efund.investor.deposit', string="Déposit")
    withdraw_id = fields.Many2one('efund.investor.withdraw', string="Retrait")

