import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class EfundCashDepositWizard(models.TransientModel):
    _name = "efund.cash.deposit.wizard"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = "Wizard Dépôt sur compte espèces"

    cash_account_id = fields.Many2one(
        'efund.account.cash', required=True, readonly=True
    )

    fund_id = fields.Many2one(
        related='cash_account_id.fund_id',
        store=True
    )

    investor_id = fields.Many2one(
        related='cash_account_id.investor_id',
        store=True
    )

    amount = fields.Monetary(required=True)
    currency_id = fields.Many2one(
        related='cash_account_id.company_id.currency_id'
    )
    # 🔹 Champ manquant : date_operation
    date_operation = fields.Date(
        string="Date de l'opération",
        required=True,
        default=fields.Date.context_today,
    )

    payment_mode = fields.Selection(
        [
            ('bank', 'Virement bancaire'),
            ('cheque', 'Chèque'),
            ('cash', 'Espèces'),
        ],
        string="Mode de paiement",
        default='bank',
        required=True,
    )
    #### Rappel dans la gestion de la comptabilité
    """
 
    journal_id = fields.Many2one(
        'account.journal',
        string="Journal de trésorerie",
        required=True,
        domain="[('type', 'in', ['bank', 'cash']), ('company_id', '=', company_id)]",
    )
    """
    reference_payment = fields.Char(
        string="Référence paiement / justificatif",
    )

    note = fields.Text(string="Note interne")

    def action_confirm(self):
        self.ensure_one()

        # Sécurité multi-company
        if self.env.company != self.fund_id.company_id:
            raise UserError(_("Contexte société incorrect."))

        # Compte actif
        if self.cash_account_id.state != 'active':
            raise UserError(_("Compte espèces inactif."))

        # Création de l’ORDRE de deposit
        self.env['efund.fund.cash.deposit'].create({
            'fund_id': self.fund_id.id,
            'investor_id': self.investor_id.id,
            'cash_account_id': self.cash_account_id.id,
            'amount': self.amount,
            'state': 'draft',
        })

        """
        # Création du mouvement
        self.env['efund.account.cash.move'].create({
            'cash_account_id': self.cash_account_id.id,
            'move_type': 'deposit',
            'amount': self.amount,
        })
        """

    """ @api.onchange('investor_id')
     def _onchange_investor_id(self):
         #Pré-sélectionner un compte espèces si un seul est actif pour l’investisseur.
         for wizard in self:
             if wizard.investor_id:
                 accounts = wizard.investor_id.account_cash_ids.filtered(lambda a: a.state == 'active')
                 if len(accounts) == 1:
                     wizard.cash_account_id = accounts[0]
     """

    def action_confirm_deposit(self):
        """Valide le dépôt : crédite le compte espèces et optionnellement crée une opération comptable."""
        self.ensure_one()

        if self.amount <= 0:
            raise ValidationError(_("Le montant du dépôt doit être strictement positif."))

        if not self.cash_account_id:
            raise UserError(_("Veuillez sélectionner un compte espèces."))

        # 1) Mettre à jour le solde du compte espèces
        _lo
        self.cash_account_id.sudo().write({
            'balance': (self.cash_account_id.balance or 0.0) + self.amount,
        })

        # 2) (Optionnel) créer une écriture comptable simple dans la société du fonds ou de la société
        #    → à adapter selon la structure de ton plan comptable
        """
        if self.fund_id and self.fund_id.cash_account_id and self.fund_id.subscription_journal_id:
            move_vals = {
                'date': self.date_operation,
                'journal_id': self.fund_id.subscription_journal_id.id,
                'company_id': self.fund_id.company_id.id if self.fund_id.company_id else self.company_id.id,
                'ref': _("Dépôt espèces investisseur %s") % (self.investor_id.display_name or ''),
                'line_ids': [
                    # Débit banque / caisse du fonds
                    (0, 0, {
                        'name': _("Dépôt espèces - %s") % (self.investor_id.display_name or ''),
                        'account_id': self.fund_id.cash_account_id.id,
                        'debit': self.amount,
                        'credit': 0.0,
                    }),
                    # Crédit compte de tiers (à paramétrer si tu veux un compte de dettes vis-à-vis du porteur)
                    # Ici on laisse à adapter (ou à commenter si non utilisé)
                ]
            }
            self.env['account.move'].create(move_vals)
        """

        # 3) message dans le chatter de l'investisseur
        if self.investor_id:
            self.investor_id.message_post(
                body=_(
                    "Dépôt espèces enregistré :<br/>"
                    "- Montant : %(amt).2f<br/>"
                    "- Compte : %(acc)s<br/>"
                    "- Date : %(date)s"
                ) % {
                         'amt': self.amount,
                         'acc': self.cash_account_id.account_number or self.cash_account_id.name,
                         'date': self.date_operation or '',
                     },
                subject=_("Dépôt sur compte espèces"),
            )

        return {'type': 'ir.actions.act_window_close'}
