from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EfundFundCash(models.Model):
    _name = 'efund.vehicule.cash'
    _description = 'Compte espèces du fonds'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Libellé", required=True, tracking=True)
    vehicule_id = fields.Many2one('efund.vehicule', string="Fonds", required=True, index=True, ondelete='cascade')
    company_id = fields.Many2one('res.company', related='vehicule_id.company_id', store=True)
    bank_id = fields.Many2one('res.bank', string="Banque / Dépositaire")
    account_number = fields.Char(string="N° Compte espèce")
    currency_id = fields.Many2one(related='vehicule_id.currency_id', store=True, readonly=True)
    balance = fields.Monetary(string="Solde", compute='_compute_balance', currency_field='currency_id')
    state = fields.Selection([('active', 'Actif'), ('inactive', 'Inactif')], default='active')

    _uniq_account_fund = models.Constraint(
        'unique(account_number, vehicule_id)',
        'Ce compte espèces existe déjà pour ce fonds.'
    )

    def _compute_balance(self):
        for acc in self:
            moves = self.env['efund.vehicule.cash.move'].search([
                ('vehicule_cash_id', '=', acc.id)
            ])
            acc.balance = sum(
                m.amount if '_in' in m.move_type else -m.amount
                for m in moves
            )

    @api.model
    def get_vehicule_cash_id_by_vehicule_id(self, vehicule_id):
        vehicule = self.search([('vehicule_id', '=', vehicule_id)], limit=1)
        if vehicule:
            return vehicule.id
        else:
            return False

    def get_balance_by_vehicule_id(self, vehicule_id):
        return self.balance
