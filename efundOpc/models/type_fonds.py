from odoo import models, fields, api


class TypeFonds(models.Model):
    _name = 'efund.type.fonds'
    _description = 'Type de fond'

    code = fields.Char(string='Code')
    name = fields.Char(string='Nom')
    description = fields.Text(string='Description')