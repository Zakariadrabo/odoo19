from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class CountryZone(models.Model):
    _name = 'efund.country.zone'
    _description = 'Zones géographiques pour les mandats'

    name = fields.Char(string="Nom de la zone", required=True)
    code = fields.Char(string="Code de la zone")
    country_ids = fields.Many2many('res.country', string="Pays inclus")