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

    full_name = fields.Char(string="Nom et prénom(s)",)
    lien_client = fields.Char(string="Lien avec le client")
    address = fields.Char(string="Adresse")
    phone = fields.Char(string="Téléphone")
    document_type = fields.Selection([
        ('passport', 'Passeport'),
        ('id_card', 'Carte d\'identité'),
        ('birth_certificate', 'Acte de naissance'),
        ('other', 'Autre')
    ], string="Type de document",)
    document_number = fields.Char(string="N° ")
    document_date_delivered = fields.Date(string="Date de validité")
    document_date_expiry = fields.Date(string="Date d'expiration")
    document_deliverd_place = fields.Char(string="Lieu de délivrance")

    relationship = fields.Selection([
        ('mandataire', 'Mandataire'),
        ('tuteur', 'Tuteur'),
        ('curateur', 'Curateur'),
        ('other', 'Autre')
    ], string="Type de pouvoir",)
