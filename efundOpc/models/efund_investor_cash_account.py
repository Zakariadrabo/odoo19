import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class EfundAccountCash(models.Model):
    _name = 'efund.investor.cash_account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Compte Espèces Client'

    name = fields.Char(string="Libellé", required=True, copy=False)
    account_number=fields.Char(string="N° Compte Espèces", required=True, copy=False)
    vehicule_id = fields.Many2one('efund.vehicule', string="Véhicule", index=True)
    company_id = fields.Many2one(related='vehicule_id.company_id', store=True, index=True, readonly=True)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", ondelete='cascade')
    balance = fields.Float(string="Solde disponible", compute='_compute_balance',store=False)
    date_opened = fields.Date(string="Date d’ouverture", default=fields.Date.today)
    state = fields.Selection([('draft', 'Non Activé'),('active', 'Activé'),('suspended', 'Désactivé'),], string="Status", default='draft', )

    _account_number_fund_uniq = models.Constraint(
            'unique(account_number, vehicule_id, investor_id)',
            'Numéro de compte espèces déjà utilisé pour ce fonds'
        )


    def _compute_balance(self):
        for acc in self:
            moves = self.env['efund.investor.cash_account.move'].search([
                ('cash_account_id', '=', acc.id)
            ])
            acc.balance = sum(
                m.amount if m.move_type in('deposit','refund','redemption_net') else -m.amount
                for m in moves
            )

    def action_open_cash_deposit_wizard(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Aucun compte espèces n’est associé à cet investisseur."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Dépôt sur compte espèces"),
            "res_model": "efund.investor.deposit.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_cash_account_id": self.id,
                "default_move_type": "deposit",
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
                'default_mandat_id': self.mandate_id.id,
                'default_investor_id': self.investor_id.id,
                'force_company': self.company_id.id,
            }
        }

    def action_open_cash_withdraw_wizard(self):
        self.ensure_one()
        if self.state != 'active':
            raise UserError(_("Aucun compte espèces n’est associé à cet investisseur."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Retrait sur compte espèces"),
            "res_model": "efund.investor.deposit.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_cash_account_id": self.id,
                "default_move_type": "withdraw",
                "company_id": self.company_id.id,
            }
        }

    def get_cash_account_id_investor_by_vehicule_and_investor_id(self, vehicule_id, investor_id):
        investor = self.env['efund.investor.cash_account'].search([('vehicule_id', '=', vehicule_id), ('investor_id', '=', investor_id)])
        if investor:
            return investor.id
        else:
            raise UserError(_("Investisseur non trouvé pour le véhicule spécifié."))

    def get_balance_by_investor(self, investor_id, vehicule_id):
        investor_account = self.env['efund.investor.cash_account'].search([('investor_id', '=', investor_id),('vehicule_id','=',vehicule_id)], limit=1)
        if investor_account:
            return investor_account.balance
        else:
            return 0





