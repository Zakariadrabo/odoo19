import logging
import math

from odoo import models, fields, api, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)

class FundRedemptionWizard(models.TransientModel):
    _name = 'efund.fund.redemption.wizard'
    _description = 'Wizard de rachat'

    part_account_id = fields.Many2one('efund.account.part',required=True,readonly=True)
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    cash_account_id = fields.Many2one('efund.account.cash',required=True,readonly=True)
    total_parts_available = fields.Float(string="Nombre de parts", related="part_account_id.total_parts", readonly=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id',store=True)
    investor_id = fields.Many2one(related='part_account_id.investor_id',store=True)
    company_id = fields.Many2one(related='fund_id.company_id',store=True)
    currency_id = fields.Many2one(related='company_id.currency_id',store=True)
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées",
                                            related='part_account_id.fund_id.allow_fractional_parts',)
    # rachat
    redemption_type = fields.Selection([('partial', 'Rachat partiel'),('total', 'Rachat total'),],string="Type de rachat",default='partial',required=True)
    parts_to_redeem = fields.Float(string="Nombre de parts")

    # info VL (prévisionnelle)
    nav_date = fields.Date(string="Date VL appliquée",default=fields.Date.context_today, required=True)
    estimated_nav = fields.Float(string="VL estimée", related="fund_id.current_vl", help="VL indicative (à confirmer)",)
    estimated_amount = fields.Monetary(string="Montant à percevoir", readonly=True,)
    #frais rachat
    redemption_fee_amount = fields.Monetary(string="Frais de rachat",
                                              compute="_compute_redemption_fee_amount", readonly=True)
    redemption_fee_rate = fields.Float(string=" % Frais de rachat", related="fund_id.redemption_fee_rate",
                                         readonly=True)
    amount = fields.Float(string="Montant + frais", )
    cash_refund = fields.Float(string="Montant souhaité")

    # -------------------------
    # COMPUTE
    # -------------------------
    @api.depends('parts_to_redeem')
    def _compute_redemption_fee_amount(self):
        for sub in self:
            if not sub.allow_fractional_parts and sub.parts_to_redeem % 1 != 0:
                raise  UserError(_("Ce fond n'accepte que des rachats de parts entières."))

            sub.amount = sub.estimated_nav * sub.parts_to_redeem
            sub.redemption_fee_amount = sub.amount * sub.redemption_fee_rate / 100
            sub.estimated_amount = sub.amount - sub.redemption_fee_amount


    @api.onchange('cash_refund')
    def _onchange_cash_refund(self):
        for sub in self:

            sub.amount = sub.cash_refund * (1 + sub.redemption_fee_rate / 100)
            sub.parts_to_redeem = sub.cash_refund / sub.estimated_nav
            if sub.allow_fractional_parts:
                sub.parts_to_redeem = round(sub.parts_to_redeem, 4)
            else:
                sub.parts_to_redeem = math.floor(sub.parts_to_redeem)

            sub.redemption_fee_amount = sub.cash_refund * sub.redemption_fee_rate / 100
            sub.estimated_amount = sub.amount - sub.redemption_fee_amount


    @api.onchange('redemption_type')
    def _onchange_redemption_type(self):
        for rec in self:
            if rec.redemption_type == 'total' and rec.part_account_id:
                rec.parts_to_redeem = rec.part_account_id.total_parts
            elif rec.redemption_type == 'partial':
                rec.parts_to_redeem = 0.0


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
        if self.total_parts_available < self.parts_to_redeem:
            raise UserError(_("Nombre de parts insuffisant."))

        # Création de l’ORDRE de rachat
        self.env['efund.fund.redemption'].create({
            'fund_id': self.fund_id.id,
            'investor_id': self.investor_id.id,
            'cash_account_id': self.cash_account_id.id,
            'part_account_id': self.part_account_id.id,
            'date_operation': self.date_operation,
            'nav_date': self.nav_date,
            'estimated_nav': self.estimated_nav,
            'estimated_amount': self.estimated_amount,
            'total_parts_available': self.part_account_id.total_parts,
            'parts_to_redeem': self.parts_to_redeem,
            'redemption_type': self.redemption_type,
            'amount': self.amount,
            'redemption_fee_amount': self.redemption_fee_amount,
            'redemption_fee_rate': self.redemption_fee_rate,
            'state': 'draft',
        })
