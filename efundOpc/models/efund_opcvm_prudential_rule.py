from odoo import models, fields, api, _

class EfundPrudentialRule(models.Model):
    _name = 'efund.prudential.rule'
    _description = 'Règle prudentielle OPCVM'

    opcvm_type_id = fields.Many2one('efund.opcvm.type',required=True)
    rule_scope = fields.Selection([('issuer', 'Par émetteur'),('state_single', 'État unique'),('state_global', 'Ensemble des États'),
    ], required=True)
    threshold = fields.Float(string="Seuil (%)", required=True)
    base = fields.Selection([('total_assets', 'Actifs totaux'),('assets_ex_cash', 'Actifs hors liquidités'),
    ], required=True)
j