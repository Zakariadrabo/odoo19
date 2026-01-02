from odoo import models, fields, api


class StatutOperationnel(models.Model):
    _name = 'efund.statut.operationnel'
    _description = 'Status Operationnel'

    code = fields.Char(string='Code')
    name = fields.Char(string='Nom')
    description = fields.Text(string='Description')