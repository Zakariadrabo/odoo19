from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundAccountCash(models.Model):
    _name = 'efund.account.cash'
    _inherit = ['mail.thread', 'mail.activity.mixin']
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
                m.amount if m.move_type in('deposit','refund') else -m.amount
                for m in moves
            )

    def action_open_cash_deposit_wizard(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Aucun compte espèces n’est associé à cet investisseur."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Dépôt sur compte espèces"),
            "res_model": "efund.cash.deposit.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_cash_account_id": self.id,
                "company_id": self.company_id.id,
            }
        }

    def action_active_account_wizard(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Activation du compte',
            'res_model': 'efund.account.activate.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_account_model': 'cash',
                'default_cash_account_id': self.id,
                'default_fund_id': self.fund_id.id,
                'default_investor_id': self.investor_id.id,
                'force_company': self.company_id.id,
            }
        }



