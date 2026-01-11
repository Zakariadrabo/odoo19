from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EfundFeeType(models.Model):
    _name = 'efund.investor.operation.fee'
    _description = 'Frais calculé'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.operation.fee'))
    fee_type = fields.Selection([('subscription','Soucription'),('redemption','Rachat'),('management','Gestion')])
    fund_id = fields.Many2one('efund.fund', required=True)
    company_id = fields.Many2one('res.company', related='fund_id.company_id', store=True, index=True, readonly=True)
    currency_id = fields.Many2one(related='fund_id.currency_id')

    # Reconciliation
    investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Cash Investisseur", readonly=True)
    fund_cash_move_id = fields.Many2one('efund.fund.cash.move', string="Cash Fonds", readonly=True)
    investor_id = fields.Many2one('efund.investor')

    # Récociliation Opération
    subscription_id = fields.Many2one('efund.investor.subscription', string="Ordre de Souscription")
    redemption_id = fields.Many2one('efund.investor.redemption', string="Ordre de Rachat")


    base_amount = fields.Monetary()
    gross_amount = fields.Monetary()
    fee_rate = fields.Float()
    fee_amount = fields.Monetary()
