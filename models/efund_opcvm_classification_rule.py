from odoo import models, fields, api, _

class EfundOpcvmClassificationRule(models.Model):
    _name = 'efund.opcvm.classification.rule'
    _description = 'Règle de classification OPCVM'

    opcvm_type_id = fields.Many2one('efund.opcvm.type',required=True,ondelete='cascade')
    asset_type = fields.Selection([('equity', 'Actions'),('bond', 'Obligations'),('money_market', 'Monétaire'),
        ('opcvm_equity', 'OPCVM Actions'), ('opcvm_bond', 'OPCVM Obligations'),], required=True)
    operator = fields.Selection([('>=', 'Supérieur ou égal'),('<=', 'Inférieur ou égal'),('=', 'Égal'),
    ], required=True)
    threshold = fields.Float(string="Seuil (%)",required=True, help="Calculé hors liquidités")
