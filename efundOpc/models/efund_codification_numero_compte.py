from odoo import fields, models, _

class CodificationNumeroCompte(models.Model):
    _name = 'efund.company.number'
    _description = 'Codification Numéro de Compte'

    code_teneur_compte = fields.Char(string="Code teneur de compte", help="composé de 4 caractères")
    code_agence = fields.Char(string="Code agence", help="composé de 2 caractères")
    code_type_compte = fields.Char(string="Code type compte", help="composé de 2 caractères")