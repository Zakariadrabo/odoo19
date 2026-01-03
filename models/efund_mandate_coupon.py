from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EfundMandateCoupon(models.Model):
    _name = 'efund.mandate.coupon'
    _description = 'Coupon annuel de mandat'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'year'

    mandate_id = fields.Many2one('efund.mandate',required=True,ondelete='cascade')
    company_id = fields.Many2one(related='mandate_id.management_company_id.company_id',store=True)
    #cash_account_id = fields.Many2one('efund.account.cash',required=True,string="Compte espèces du mandat")
    year = fields.Integer(string="Année",required=True)
    amount = fields.Monetary(string="Montant du coupon",required=True)
    currency_id = fields.Many2one(related='company_id.currency_id',store=True)
    payment_date = fields.Date()
    state = fields.Selection([
        ('planned', 'Prévu'),
        ('paid', 'Payé'),
        ('cancelled', 'Annulé'),
    ], default='planned', tracking=True)



    def action_pay(self):
        """Paiement effectif du coupon"""
        for rec in self:
            if rec.state != 'planned':
                continue

            self.env['efund.account.cash.move'].create({
                'mandate_id': rec.mandate_id.id,
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'coupon',
                'amount': rec.amount,
            })

            rec.write({
                'state': 'paid',
                'payment_date': fields.Date.today(),
            })
