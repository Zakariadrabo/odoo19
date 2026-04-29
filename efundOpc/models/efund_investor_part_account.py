import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class EfundAccountPart(models.Model):
    _name = 'efund.investor.part_account'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Compte Parts / Actions'

    name = fields.Char(string="Libellé", required=True, copy=False)
    account_number = fields.Char(string="N° Compte Titre", required=True, copy=False)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", ondelete='cascade')
    vehicule_id = fields.Many2one('efund.vehicule', string="Fonds", ondelete='cascade')
    currency_id = fields.Many2one(related='vehicule_id.currency_id', store=True)
    company_id = fields.Many2one('res.company', related='vehicule_id.company_id', store=True, index=True, readonly=True)
    date_opened = fields.Date(string="Date d’ouverture")
    total_parts = fields.Float(compute='_compute_total_parts', store=False)
    total_invested_amount = fields.Monetary(string="Montant total investi", compute='_compute_cmp', store=False)
    cmp = fields.Monetary(string="Coût moyen pondéré (CMP)", compute='_compute_cmp', store=False)
    total_value = fields.Float(string="Valeur totale (FCFA)", store=False)
    state = fields.Selection([('draft', 'Non Activé'), ('active', 'Activé'), ('suspended', 'Désactivé'), ],
                             string="Status", default='draft', )

    _account_number_fund_uniq = models.Constraint(
        'unique(account_number, vehicule_id,investor_id)',
        'Numéro de compte titres déjà utilisé pour ce fonds'
    )
    _investor_id_fund_uniq = models.Constraint(
        'unique(investor_id, vehicule_id)',
        'Un investisseur ne peut avoir qu’un compte titres par fonds'
    )

    def get_fund_portfolio_data(self):
        """
        Retourne les données du portefeuille POUR CE FONDS
        """
        self.ensure_one()

        # Compte cash associé à ce fonds
        cash_account = self.env['efund.investor.cash'].search([
            ('investor_id', '=', self.investor_id.id),
        ], limit=1)

        cash_balance = cash_account.balance if cash_account else 0.0

        # VL courante
        share_class = self.env['efund.fund.share.class'].search([
            ('fund_id', '=', self.fund_id.id),
            ('is_default', '=', True)
        ], limit=1)

        nav = share_class.current_nav if share_class else 0.0

        acquisition_cost = self.total_parts * self.cmp
        valuation = self.total_parts * nav
        gain = valuation - acquisition_cost

        return {
            'fund_name': self.fund_id.name,
            'parts': self.total_parts,
            'cmp': self.cmp,
            'nav': nav,
            'acquisition_cost': acquisition_cost,
            'cash_balance': cash_balance,
            'valuation': valuation,
            'gain': gain,
            'currency': self.fund_id.currency_id.symbol,
        }

    def action_redeem_parts(self):
        self.ensure_one()

        if self.state != 'active':
            raise UserError(_("Le compte titres n’est pas actif."))

        if self.total_parts <= 0:
            raise UserError(_("Aucune part disponible pour le rachat."))

        if self.investor_id.compliance_status != 'compliant':
            raise UserError(_("Investisseur non conforme KYC."))

        cash_account = self.env['efund.investor.cash'].search([('investor_id', '=', self.investor_id.id),
                                                               ('fund_id', '=', self.fund_id.id), ])
        if not cash_account:
            raise UserError(_("Aucun compte cash n’est associé à cet investisseur."))

        # ouvrir le wizard de rachat
        return {
            'type': 'ir.actions.act_window',
            'name': _("Rachat de parts"),
            'res_model': 'efund.investor.redemption.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_part_account_id': self.id,
                "default_cash_account_id": cash_account.id,
                'default_company_id': self.company_id.id,
            }
        }

    def _compute_total_parts(self):
        for acc in self:
            moves = self.env['efund.investor.part.move'].search([
                ('part_account_id', '=', acc.id),
                ('state', '=', 'reconciled')
            ])

            acc.total_parts = sum(
                m.shares if m.move_type == 'subscription' else -m.shares
                for m in moves if m.move_type in ('subscription', 'redemption')
            )

    def _compute_cmp(self):
        for acc in self:
            # 1️⃣ Total des parts (on réutilise le calcul existant)
            total_parts = acc.total_parts

            # 2️⃣ Montant total NET investi (hors frais)
            cash_moves = self.env['efund.investor.cash.move'].search([
                ('investor_id', '=', acc.investor_id.id),
                ('fund_id', '=', acc.fund_id.id),
                ('move_type', '=', 'subscription_net'),
                ('state', 'in', ('accounted', 'reconciled')),
            ])
            total_invested = sum(m.amount for m in cash_moves)
            acc.total_invested_amount = total_invested

            # 3️⃣ CMP
            acc.cmp = total_parts and (total_invested / total_parts) or 0.0

    def action_open_subscription_wizard(self):
        self.ensure_one()

        if self.state != 'active':
            raise UserError(_("Aucun compte titre n’est associé à cet investisseur."))

        cash_account = self.env['efund.investor.cash'].search([('investor_id', '=', self.investor_id.id),
                                                               ('fund_id', '=', self.fund_id.id), ])
        if not cash_account:
            raise UserError(_("Aucun compte cash n’est associé à cet investisseur."))

        return {
            "type": "ir.actions.act_window",
            "name": _("Nouvelle demande de souscription"),
            "res_model": "efund.investor.subscription.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                'default_account_model': 'part',
                "default_part_account_id": self.id,
                "default_cash_account_id": cash_account.id,
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
                'default_account_model': 'part',
                'default_part_account_id': self.id,
                'default_fund_id': self.fund_id.id,
                'default_investor_id': self.investor_id.id,
                "company_id": self.company_id.id,
            }
        }
