from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundRedemptionWizard(models.TransientModel):
    _name = 'efund.fund.redemption.wizard'
    _description = 'Wizard de rachat'

    part_account_id = fields.Many2one(
        'efund.account.part',
        required=True,
        readonly=True
    )

    cash_account_id = fields.Many2one(
        'efund.account.cash',
        required=True,
        readonly=True
    )

    fund_id = fields.Many2one(
        related='part_account_id.fund_id',
        store=True
    )

    investor_id = fields.Many2one(
        related='part_account_id.investor_id',
        store=True
    )

    company_id = fields.Many2one(
        related='fund_id.company_id',
        store=True
    )

    currency_id = fields.Many2one(
        related='company_id.currency_id',
        store=True
    )

    parts = fields.Float(
        string="Nombre de parts à racheter",
        required=True
    )

    def action_confirm(self):
        self.ensure_one()

        # Sécurité multi-company
        if self.env.company != self.company_id:
            raise UserError(_("Contexte société incorrect."))

        # Investisseur validé pour le fonds
        fund_inv = self.env['efund.fund.investor'].search([
            ('investor_id', '=', self.investor_id.id),
            ('fund_id', '=', self.fund_id.id),
            ('state', '=', 'validated')
        ], limit=1)

        if not fund_inv:
            raise UserError(_("Investisseur non validé pour ce fonds."))

        # Parts suffisantes
        if self.part_account_id.total_parts < self.parts:
            raise UserError(_("Nombre de parts insuffisant."))

        # Création de l’ORDRE de rachat
        self.env['efund.fund.redemption'].create({
            'fund_id': self.fund_id.id,
            'investor_id': self.investor_id.id,
            'cash_account_id': self.cash_account_id.id,
            'part_account_id': self.part_account_id.id,
            'parts': self.parts,
            'state': 'draft',
        })
