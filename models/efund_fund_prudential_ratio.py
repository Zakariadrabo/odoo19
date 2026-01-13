from odoo import models, fields, api, _

class FundPrudentialRatio(models.Model):
    _name = 'efund.fund.prudential.ratio'
    _description = 'Ratio prudentiel'

    name = fields.Char(required=True, string="Nom")
    code = fields.Char(required=True, string="Code")
    description = fields.Text(string="Description")

    calculation_method = fields.Selection([
        ('exposure_issuer', 'Exposition par émetteur'),
        ('concentration', 'Concentration'),
        ('maturity', 'Maturité moyenne'),
        ('duration', 'Duration'),
        ('liquidity', 'Liquidité'),
    ], required=True, string="Méthode de calcul")
    limit_ids = fields.One2many('efund.fund.prudential.limit', 'ratio_id', string="Limites prudentielles")
