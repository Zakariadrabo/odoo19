from odoo import models, fields, api, _

class FundExpenseAccrual(models.Model):
    _name = "efund.fund.expense.accrual"
    _description = "Constatation des charges"

    vehicule_id = fields.Many2one('efund.vehicule', required=True, string='Fonds')
    expense_id = fields.Many2one('efund.vehicule.expense', required=True, string='Charge')
    accrual_date = fields.Date(required=True, string='Date de constatation')
    base_amount = fields.Monetary(string="Base de calcul")
    expense_amount = fields.Monetary(string="Montant de la charge")
    currency_id = fields.Many2one(related="vehicule_id.currency_id",  string='Devise')
    state = fields.Selection([('draft', 'Brouillon'),('validated', 'Validé'),('archived', 'Archivé'),], default='draft', string='Statut')

