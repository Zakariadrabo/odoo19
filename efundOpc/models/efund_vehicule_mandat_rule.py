from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class EfundMandateRule(models.Model):
    _name = 'efund.vehicule.mandate.rule'
    _description = 'Règles de conformité du Mandat'

    name = fields.Char(string="Nom de la règle", required=True)
    mandate_id = fields.Many2one('efund.vehicule.mandate', string="Mandat associé")

    # Critères de contrôle
    allowed_asset_types = fields.Many2many('efund.asset.class', string="Types d'actifs autorisés")
    allowed_zones = fields.Many2many( 'efund.country.zone', string="Zones géographiques autorisées")
    max_concentration = fields.Float(string="Limite de concentration (%)")
    min_liquidite = fields.Float(string="Limite de liquidité (%)")
