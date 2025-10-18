from odoo import models, fields, api


class SecteurActivite(models.Model):
    _name = 'efund.secteur.activite'
    _description = 'Secteur Activite'

    code = fields.Char(string='Code')
    name = fields.Char(string='Nom')
    description = fields.Text(string='Description')