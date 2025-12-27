from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundAccountCash(models.Model):
    _name = 'efund.account.cash'
    _description = 'Compte Espèces Client'

    name = fields.Char(string="Libellé", required=True, copy=False)
    account_number=fields.Char(string="Numéro compte", required=True, copy=False)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", ondelete='cascade')
    balance = fields.Float(string="Solde disponible")
    date_opened = fields.Date(string="Date d’ouverture", default=fields.Date.today)
    state = fields.Selection([
        ('draft', 'Non Activé'),
        ('active', 'Activé'),
        ('suspended', 'Désactivé'),
    ], string="Status", default='draft', )
