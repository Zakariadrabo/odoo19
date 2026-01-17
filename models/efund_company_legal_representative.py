from odoo import models, fields

class EFundCompanyLegalRepresentative(models.Model):
    _name = "efund.company.legal.representative"
    _description = "Représentant légal - Personne morale"

    investor_id = fields.Many2one("efund.investor", required=True, ondelete="cascade", domain=[("investor_type", "=", "company")] )
    full_name = fields.Char(string="Nom et prénoms", required=True)
    birth_date = fields.Date(string="Date de naissance")
    function = fields.Char(string="Fonction")
    nationality_id = fields.Many2one("res.country", string="Nationalité")
    marital_status = fields.Char(string="Statut matrimonial")
    phone = fields.Char(string="Contact")
    address = fields.Text(string="Adresse")
    email = fields.Char(string="Email")
