import logging
import math

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FundSubscriptionWizard(models.TransientModel):
    _name = 'efund.fund.subscription.wizard'
    _description = 'Wizard de souscription'

    cash_account_id = fields.Many2one('efund.account.cash',required=True,readonly=True)
    balance = fields.Float(string="Solde",related="cash_account_id.balance",readonly=True)
    part_account_id = fields.Many2one('efund.account.part',required=True,readonly=True)
    total_parts = fields.Float(string="Nombre de parts",related="part_account_id.total_parts",readonly=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id',store=True)
    subscription_fee_rate = fields.Float(string=" % Frais de souscription",related="fund_id.subscription_fee_rate",readonly=True)
    subscription_fee_amount = fields.Monetary(string="Montant frais de souscription",compute="_compute_subscription_fee_amount",readonly=True)
    net_amount = fields.Monetary(string="Montant net",compute="_compute_subscription_fee_amount",readonly=True)
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées",related='cash_account_id.fund_id.allow_fractional_parts',)
    parts = fields.Float(string="Nombre de parts")
    investor_id = fields.Many2one(related='part_account_id.investor_id',store=True)
    company_id = fields.Many2one(related='fund_id.company_id',store=True)
    currency_id = fields.Many2one(related='company_id.currency_id',store=True)
    amount = fields.Monetary(string="Montant à souscrire",required=True)
    unit_value = fields.Float(string="VL appliquée", related="fund_id.current_vl", readonly=True)
    reliquat = fields.Monetary(string="Reliquat",compute="_compute_subscription_fee_amount",readonly=True)


    @api.depends('amount', 'subscription_fee_rate', 'unit_value', 'net_amount', 'parts')
    def _compute_subscription_fee_amount(self):
        for sub in self:

            if sub.unit_value <= 0:
                raise UserError("La valeur liquidative doit être positive")

            prix_unitaire_ttc = sub.unit_value * (1 + sub.subscription_fee_rate/100)

            if sub.allow_fractional_parts:
                # On calcule avec des décimales (souvent 4 pour les OPCVM)
                sub.parts = round(sub.amount / prix_unitaire_ttc, 4)
            else:
                # On force l'entier inférieur
                sub.parts = math.floor(sub.amount / prix_unitaire_ttc)

            montant_reel = sub.parts * prix_unitaire_ttc
            reliquat = sub.amount - montant_reel


            sub.net_amount = montant_reel
            sub.subscription_fee_amount = sub.parts * sub.unit_value * sub.subscription_fee_rate /100
            sub.reliquat = reliquat

    @api.onchange('parts')
    def _onchange_parts(self):
        a_des_decimales = self.parts % 1 != 0
        if a_des_decimales and not self.allow_fractional_parts:
            raise UserError(_("Ce fonds n'accepte que des nombres de parts entières."))

        self.net_amount = self.parts * self.unit_value
        self.subscription_fee_amount = self.parts * self.unit_value * self.subscription_fee_rate / 100
        self.amount = self.net_amount + self.subscription_fee_amount
        self.net_amount = 0


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

        # Solde disponible suffisant
        if self.cash_account_id.balance < self.amount:
            raise UserError(_("Solde espèces insuffisant."))

        # Création de l’ORDRE de souscription
        self.env['efund.fund.subscription'].create({
            'fund_id': self.fund_id.id,
            'investor_id': self.investor_id.id,
            'cash_account_id': self.cash_account_id.id,
            'part_account_id': self.part_account_id.id,
            'amount': self.amount,
            'cash_refund': self.reliquat,
            'subscription_fee_amount': self.subscription_fee_amount,
            'cash_used': self.net_amount,
            'parts': self.parts,
            'unit_value': self.unit_value,
            'state': 'draft',
        })
