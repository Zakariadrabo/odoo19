# models/efund_bourse_order_execution_line.py
from odoo import models, fields

class FundBourseOrderExecutionLine(models.Model):
    _name = 'efund.bourse.order.execution.line'
    _description = 'Execution Line of Bourse Order'
    _order = 'execution_date desc'

    order_id = fields.Many2one('efund.bourse.order',required=True,ondelete='cascade')
    execution_date = fields.Date(required=True, string='Date d\'Execution ')
    quantity = fields.Float(required=True, string='Quantité')
    price = fields.Float(required=True, string='Prix')

    depositaire_sgi = fields.Many2one(related='order_id.depositaire_sgi',string="Dépositaire du fond",required=True)
    reference = fields.Char(string="Référence SGI")
    currency_id = fields.Many2one(related='order_id.currency_id',store=True)

    total_broker_commission = fields.Monetary(string="Commission de courtage", store=True)
    total_tob_commission = fields.Monetary(string="Taxe TVA", store=True)
    total_interest = fields.Monetary(string="intérêts courus", store=True)
    total_amount = fields.Monetary(string="Total montant", store=True)
