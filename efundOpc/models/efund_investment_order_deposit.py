from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EfundInvestmentDepositOrder(models.Model):
    _name = 'efund.investment.order.deposit'
    _description = "Ordre de placement DAT"
    _inherits = {'efund.investment.order': 'order_id'}

    order_id = fields.Many2one('efund.investment.order', required=True, ondelete='cascade')

    deposit_amount = fields.Monetary(string="Montant à placer", required=True)
    negotiated_rate = fields.Float(string="Taux négocié (%)")
    maturity_date = fields.Date(string="Échéance prévue")
    start_date = fields.Date(required=True)
    total_amount = fields.Monetary(related='principal_amount', store=True)