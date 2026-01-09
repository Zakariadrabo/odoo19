from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundInterventionMode(models.Model):
    _name = 'efund.investor.intervention.mode'
    _description = 'Mode d’intervention'

    investor_id = fields.Many2one('efund.investor',string="Produits / Services sollicités",required=True, readonly=True ,ondelete='cascade')
    #name = fields.Char(required=True)
    code = fields.Selection([
        ('individual', 'Gestion Individuelle'),
        ('collective', 'Gestion Collective'),
        ('advisory', 'Conseil en investissement'),
    ], required=True, string="Produits / Services sollicités")
    active = fields.Boolean(default=True)
