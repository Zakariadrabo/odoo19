from odoo import models, fields


class EFundInvestorHeir(models.Model):
    _name = "efund.investor.heir"
    _description = "Héritier / Ayant droit"

    investor_id = fields.Many2one("efund.investor",required=True,ondelete="cascade")

    full_name_heir = fields.Char(string="Nom et prénoms", required=True)
    birthdate = fields.Date(string="Date de naissance")
    birthplace = fields.Char(string="Lieu de naissance")
    birth_country_id = fields.Many2one("res.country", string="Pays de naissance")
    sex = fields.Selection([('male', 'Homme'), ('female', 'Femme')], string="Sexe")
    relationship = fields.Char(string="Lien de parenté")
    email = fields.Char(string="Adresse Email")
    phone = fields.Char(string="Numéro de Téléphone")
