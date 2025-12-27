from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundAccountCash(models.Model):
    _name = 'efund.account.cash'
    _description = 'Compte Espèces Client'

    name = fields.Char(string="Libellé", required=True, copy=False)
    account_number=fields.Char(string="Numéro compte", required=True, copy=False)
    fund_id = fields.Many2one('efund.fund',string="Fonds",index=True,required=False)
    company_id = fields.Many2one('res.company', related='fund_id.company_id', store=True, index=True, readonly=True)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", ondelete='cascade')
    balance = fields.Float(string="Solde disponible", compute='_compute_balance',store=False)
    date_opened = fields.Date(string="Date d’ouverture", default=fields.Date.today)
    state = fields.Selection([
        ('draft', 'Non Activé'),
        ('active', 'Activé'),
        ('suspended', 'Désactivé'),
    ], string="Status", default='draft', )

    _account_number_fund_uniq = models.Constraint(
            'unique(account_number, fund_id)',
            'Numéro de compte espèces déjà utilisé pour ce fonds'
        )
    _investor_id_fund_uniq = models.Constraint(
            'unique(investor_id, fund_id)',
            'Un investisseur ne peut avoir qu’un compte espèces par fonds'
        )

    def _compute_balance(self):
        for acc in self:
            moves = self.env['efund.account.cash.move'].search([
                ('cash_account_id', '=', acc.id)
            ])
            acc.balance = sum(
                m.amount if m.move_type == 'deposit' else -m.amount
                for m in moves
            )

