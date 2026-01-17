from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundRepresentedPerson(models.Model):
    _name = 'efund.investor.heirs'
    _description = 'Héritiers et personnes à contact'

    investor_id = fields.Many2one(
        'efund.investor',
        string="investisseur",
        required=True,
        ondelete='cascade'
    )

    type_person = fields.Selection([('heirs', 'Héritié'),('person_to_contact', 'Personne à Contacter'),],)
    full_name = fields.Char(string="Nom et prénom(s)",)
    lien_client = fields.Char(string="Lien avec le client")
    phone = fields.Char(string="Téléphone")
    email = fields.Char(string="Email")
    birthday_place = fields.Char(string="Lieu naissance")
    birthday_date = fields.Date(string="Date de naissance")
    address = fields.Char(string="Adresse de résidence")
    address_country = fields.Many2one('res.country', string="Adresse de la country")




