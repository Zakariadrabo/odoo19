from odoo import models, fields, api, _


class CountryZone(models.Model):
    _name = 'efund.account.template'
    _description = 'Liste des compte comptable'

    name = fields.Char(string="Nom du compte", required=True)
    code = fields.Char(string="Code du compte")