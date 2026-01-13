from tokenize import String

from odoo import models, fields

class EFundInvestorRepresentative(models.Model):
    _name = "efund.investor.representative"
    _description = "Mandataire / Représentant légal"

    investor_id = fields.Many2one("efund.investor",string="Investisseur",required=True,ondelete="cascade",index=True)

    power_type = fields.Selection(
        [("mandate", "Mandataire"),
            ("guardian", "Tuteur / Curateur"),
            ("other", "Autre"),],string="Type de pouvoir ",
        required=True)

    full_name = fields.Char(string="Nom Complet", required=True)
    relationship = fields.Char(string="Lien avec le client ", required=True)
    phone = fields.Char( string="Numéro de téléphone ", required=True)
    adresse = fields.Char(string="Adresse")

    document_type = fields.Selection([
        ('id_card', 'Carte d\'identité'),
        ('passport', 'Passeport'),
        ('carte_sejour', 'Carte de séjour'),
        ('proof_of_address', 'Preuve d\'adresse'),
        ('company_doc', 'statut compagnie'),
        ('ubo', 'Document bénéficiaire effectif'),
        ('other', 'Autre')
    ], string="Type Document", required=True)
    id_number = fields.Char(string="Numéro de pièce")
    issued_date = fields.Date(string="Date d'émission")
    expiry_date = fields.Date(string="Date d'expiration")