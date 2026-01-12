from odoo import models, fields, api, _
class EfundOpcvmType(models.Model):
    _name = 'efund.opcvm.type'
    _description = 'Type réglementaire OPCVM'

    code = fields.Selection([
        ('equity', 'OPCVM Actions'),
        ('bond', 'OPCVM Obligations'),
        ('money_market', 'OPCVM Monétaire'),
        ('diversified', 'OPCVM Diversifié'),
        ('contractual', 'OPCVM Contractuel'),
    ], required=True)

    name = fields.Char(required=True)
