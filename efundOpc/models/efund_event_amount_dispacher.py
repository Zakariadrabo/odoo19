from odoo import models, fields, api, _


class CountryZone(models.Model):
    _name = 'efund.event.amount.dispacher'
    _description = 'Liste des compte comptable'

    code = fields.Char(string="Code", required=True)
    name = fields.Char(string="Libellé", required=True)
