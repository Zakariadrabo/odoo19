from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EfundFeeType(models.Model):
    _name = 'efund.investor.operation.fee'
    _description = 'Frais calculé'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.operation.fee'))
    fee_type = fields.Selection([('subscription','Soucription'),('redemption','Rachat'),('management','Gestion')])
    vehicule_id = fields.Many2one('efund.vehicule', required=True)
    company_id = fields.Many2one('res.company', related='vehicule_id.company_id', store=True, index=True, readonly=True)
    currency_id = fields.Many2one(related='vehicule_id.currency_id')

    # Reconciliation
    investor_cash_move_id = fields.Many2one('efund.investor.cash_account.move', string="Cash Investisseur", readonly=True)
    fund_cash_move_id = fields.Many2one('efund.vehicule.cash.move', string="Cash Fonds", readonly=True)
    investor_id = fields.Many2one('efund.investor')

    # Récociliation Opération
    #subscription_id = fields.Many2one('efund.investor.subscription', string="Ordre de Souscription")
    cash_operation_id = fields.Many2one('efund.vehicule.cash.operation', string="Ordre de Rachat")


    base_amount = fields.Monetary()
    gross_amount = fields.Monetary()
    fee_rate = fields.Float()
    fee_amount = fields.Monetary()
