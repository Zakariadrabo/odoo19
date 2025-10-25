from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundAccountPart(models.Model):
    _name = 'efund.account.part'
    _description = 'Compte Parts / Actions'

    name = fields.Char(string="Libellé", required=True, copy=False)
    account_number = fields.Char(string="Numéro du compte titre", required=True, copy=False)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", ondelete='cascade')
    total_parts = fields.Float(string="Nombre de parts détenues", digits=(16,6))
    total_value = fields.Float(string="Valeur totale (FCFA)")
    state = fields.Selection([
        ('draft', 'Non Activé'),
        ('active', 'Activé'),
        ('suspended', 'Désactivé'),
    ], string="Status", default='draft',)
