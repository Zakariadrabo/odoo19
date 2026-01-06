from odoo import models, fields


class EfundManagementFeeAccrual(models.Model):
    _name = 'efund.management.fee.accrual'
    _description = 'Accrual des frais de gestion'
    _order = 'date desc'

    fund_id = fields.Many2one('efund.fund',required=True,ondelete='cascade')
    share_class_id = fields.Many2one('efund.fund.share.class',string="Classe de part",required=True)
    date = fields.Date(required=True)
    base_amount = fields.Monetary(string="Actif net de base",required=True)
    rate = fields.Float(string="Taux (%)",required=True)
    accrued_amount = fields.Monetary(string="Frais accrus",required=True)
    currency_id = fields.Many2one(related='fund_id.currency_id',store=True)
    state = fields.Selection([('accrued', 'Accru'), ('paid', 'Payé'),], default='accrued')
