from odoo import models, fields, api


class FormeJuridique(models.Model):
    _name = 'efund.forme.juridique'
    _description = 'Forme de juridique'

    code = fields.Char(string='Code')
    name = fields.Char(string='Nom')
    description = fields.Text(string='Description')