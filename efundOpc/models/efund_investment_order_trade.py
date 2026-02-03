from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EfundInvestmentTradeOrder(models.Model):
    _name = 'efund.investment.order.trade'
    _description = "Ordre de Bourse"
    _inherits = {'efund.investment.order': 'order_id'}

    order_id = fields.Many2one('efund.investment.order', required=True, ondelete='cascade')

    price_type = fields.Selection([('market', 'Au marché'), ('limit', 'Prix limité')], default='market')
    limit_price = fields.Float(string="Prix limite", digits=(16, 6))
    validity_date = fields.Date(string="Date de validité", help="Date d'expiration de l'ordre")
    direction = fields.Selection([('buy', 'Achat'), ('sell', 'Vente')], string="Sens", required=True, default='buy')
    quantity = fields.Float(string="Quantité",required=True,digits=(16, 6))
    total_amount = fields.Monetary(compute='_compute_total_amount',currency_field='currency_id',store=True)

    @api.depends('quantity', 'limit_price')
    def _compute_total_amount(self):
        for rec in self:
            rec.total_amount = rec.quantity * (rec.limit_price or 0.0)