from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundRepresentedPerson(models.Model):
    _name = 'efund.investor.represented'
    _description = 'Personne représentée (Mineur / Tiers)'

    investor_id = fields.Many2one(
        'efund.investor',
        string="Représentant légal",
        required=True,
        ondelete='cascade'
    )

    full_name = fields.Char(string="Nom complet",)
    birthdate = fields.Date(string="Date de naissance")
    relationship = fields.Selection([
        ('child', 'Enfant'),
        ('ward', 'Personne sous tutelle'),
        ('other', 'Autre')
    ], string="Bénéficiaire effectif",)

    birth_certificate_ref = fields.Char(string="Référence acte de naissance")
    note = fields.Text(string="Observations")
