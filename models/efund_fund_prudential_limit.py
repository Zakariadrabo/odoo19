from odoo import models, fields, api, _

class FundPrudentialLimit(models.Model):
    _name = 'efund.fund.prudential.limit'
    _description = 'Limite prudentielle'

    fund_type = fields.Selection([
        ('equity', 'Actions'),
        ('bond', 'Obligataire'),
        ('money_market', 'Monétaire'),
        ('diversified', 'Diversifié'),
    ], required=True, string='Type de fonds')

    ratio_id = fields.Many2one('efund.fund.prudential.ratio', required=True, string="Ratio")

    max_value = fields.Float(string="Valeur maximale")
    min_value = fields.Float(string="Valeur minimale")
