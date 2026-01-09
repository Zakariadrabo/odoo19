from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundCompanyRepresented(models.Model):
    _name = 'efund.investor.company.represented'
    _description = 'Réprésentant de la société'

    investor_id = fields.Many2one(
        'efund.investor',
        string="Réprésentant",
        required=True,
        ondelete='cascade'
    )

    full_name = fields.Char(string="Nom complet",)
    birthdate = fields.Date(string="Date de naissance")
    fonction = fields.Char(string="Fonction")
    power = fields.Char(string="Pouvoir")
    birth_certificate_ref = fields.Char(string="Référence acte de naissance")
    note = fields.Text(string="Observations")
