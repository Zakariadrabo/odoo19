from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EfundInvestmentOpcvmOrder(models.Model):
    _name = 'efund.investment.order.opcvm'
    _description = "Ordre de Souscription/Rachat OPCVM"
    _inherits = {'efund.investment.order': 'order_id'}

    order_id = fields.Many2one('efund.investment.order', required=True, ondelete='cascade')

    amount_type = fields.Selection([('amount', 'Montant'), ('unit', 'Nombre de parts')], default='amount')
    order_amount = fields.Monetary(string="Montant brut souhaité")
    nav_date_expected = fields.Date(string="Date de VL cible", help="Date de la VL qui sera appliquée")
    direction = fields.Selection([('subscription', 'Souscription'), ('redemption', 'Rachat')],required=True)
    units_estimated = fields.Float(string="Parts estimées")
    total_amount = fields.Monetary(related='amount_requested',store=True)