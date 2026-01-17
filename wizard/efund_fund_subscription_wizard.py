import logging
import math

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round, float_is_zero

_logger = logging.getLogger(__name__)


class FundSubscriptionWizard(models.TransientModel):
    _name = 'efund.investor.subscription.wizard'
    _description = 'Wizard de souscription'

    cash_account_id = fields.Many2one('efund.investor.cash',string="Compte Espèces", required=True, readonly=True)

    part_account_id = fields.Many2one('efund.investor.part', string="Compte Titre", required=True, readonly=True)
    total_shares = fields.Float(string="Nombre total de parts", related="part_account_id.total_parts", readonly=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id', string="Fonds", store=True)
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées",
                                            related='cash_account_id.fund_id.allow_fractional_parts', )
    investor_id = fields.Many2one(related='part_account_id.investor_id', string="Investisseur", store=True)
    company_id = fields.Many2one(related='fund_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    buy_choice = fields.Selection([('amount', 'Montant'), ('share', 'Part')], string="Choix d'achat", default='amount')
    gross_amount = fields.Monetary(string="Montant à souscrire", required=True)
    nav = fields.Float(string="VL appliquée", compute="_compute_nav_value", readonly=True, store=True)
    amount_remaining = fields.Monetary(string="Montant restant")
    subscription_fee_rate = fields.Float(string="Taux Frais de souscription", compute="_compute_nav_value",readonly=True, store=True)
    subscription_fee_amount = fields.Monetary(string="Frais de souscription", store=True)
    net_amount = fields.Monetary(string="Montant net", store=True)
    parts = fields.Float(string="Nombre de parts", store=True)
    share_class_id = fields.Many2one('efund.fund.share.class', string="Classe de part",  compute="_compute_nav_value", store=True)
    is_subscription_fee = fields.Boolean(string="Appliquer Frais de souscription", default=True)

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        cash_account_id = res.get('cash_account_id')
        if cash_account_id:
            account = self.env['efund.investor.cash'].browse(cash_account_id)
            res['gross_amount'] = account.balance

        return res

    @api.onchange('gross_amount', 'parts','is_subscription_fee')
    def _onchange_gross_amount(self):
        for sub in self:
            if sub.buy_choice == 'amount':
                result = self.calculate_shares(sub.nav, sub.allow_fractional_parts, sub.gross_amount,
                                                         sub.subscription_fee_rate,sub.is_subscription_fee)
            else:
                result = self.calculate_amount(sub.nav, sub.allow_fractional_parts, sub.parts,
                                                           sub.subscription_fee_rate, sub.is_subscription_fee)

            # affectation des valeurs
            sub.net_amount = result.get('net_amount')
            sub.subscription_fee_amount = result.get('fees_amount')
            sub.amount_remaining = result.get('amount_remaining')
            sub.gross_amount = result.get('gross_amount')
            sub.parts = result.get('shares')

    @api.depends('fund_id')
    def _compute_nav_value(self):
        for sub in self:
            share_class = self.env['efund.fund.share.class'].search([
                ('fund_id', '=', sub.fund_id.id),
                ('is_default', '=', True)
            ])
            if share_class:
                sub.nav = share_class.current_nav
                sub.subscription_fee_rate = share_class.subscription_fee_rate
                sub.share_class_id = share_class.id
            else:
                raise UserError("Besoin d'avoir la classe de parts par défaut pour le fonds")

    def calculate_shares(self,nav,allow_fractional_shares,gross_amount,fee_percent,apply_subscription_fees):
        """
        Calcule le nombre de parts à partir d'un montant de souscription.

        :param nav: Valeur liquidative
        :param allow_fractional_shares: bool - parts fractionnaires autorisées
        :param gross_amount: Montant brut souscrit
        :param fee_percent: Pourcentage de frais de souscription
        :param apply_subscription_fees: bool - appliquer ou non les frais
        """

        # 1️⃣ Calcul des frais
        if apply_subscription_fees and fee_percent:
            fees_amount = gross_amount * (fee_percent / 100.0)
        else:
            fees_amount = 0.0

        # 2️⃣ Montant net à investir
        net_amount_to_invest = gross_amount - fees_amount

        # Sécurité
        if net_amount_to_invest < 0:
            net_amount_to_invest = 0.0

        # 3️⃣ Calcul théorique des parts
        raw_shares = net_amount_to_invest / nav if nav else 0.0

        # 4️⃣ Application des règles du fonds
        if allow_fractional_shares:
            shares = float_round(raw_shares, precision_digits=6)
        else:
            shares = int(raw_shares)  # troncature volontaire

        # 5️⃣ Montant réellement investi
        actual_amount_invested = shares * nav

        # 6️⃣ Reliquat (sur le montant NET)
        amount_remaining = net_amount_to_invest - actual_amount_invested

        # Sécurité flottants
        if float_is_zero(amount_remaining, precision_rounding=0.01):
            amount_remaining = 0.0

        return {
            'gross_amount': gross_amount,
            'fees_amount': fees_amount,
            'net_amount': net_amount_to_invest,
            'shares': shares,
            'amount_used': actual_amount_invested,
            'amount_remaining': amount_remaining,
            'fees_applied': apply_subscription_fees,
        }
    def calculate_amount(self,nav,allow_fractional_shares,shares_to_buy,fee_percent,apply_subscription_fees):
        """
        Calcule les montants (brut, net, frais) à partir d'un nombre de parts.
        """

        # 1️⃣ Sécurité NAV
        if nav <= 0:
            return {'error': "La valeur liquidative (NAV) doit être positive."}

        # 2️⃣ Validation du nombre de parts
        if not allow_fractional_shares:
            shares_to_buy = int(shares_to_buy)

        # 3️⃣ Montant net (investissement pur)
        net_amount = shares_to_buy * nav

        # 4️⃣ Calcul des frais et du montant brut
        if apply_subscription_fees and fee_percent:
            if fee_percent >= 100:
                return {'error': "Les frais ne peuvent pas être égaux ou supérieurs à 100%."}

            gross_amount = net_amount / (1 - (fee_percent / 100.0))
            fees_amount = gross_amount - net_amount
        else:
            gross_amount = net_amount
            fees_amount = 0.0

        # 5️⃣ Reliquat (par construction = 0 ici)
        amount_remaining = gross_amount - net_amount - fees_amount

        if float_is_zero(amount_remaining, precision_rounding=0.01):
            amount_remaining = 0.0

        return {
            'shares': shares_to_buy,
            'net_amount': float_round(net_amount, precision_digits=4),
            'fees_amount': float_round(fees_amount, precision_digits=4),
            'gross_amount': float_round(gross_amount, precision_digits=4),
            'amount_remaining': float_round(amount_remaining, precision_digits=4),
            'fees_applied': apply_subscription_fees,
        }


    def action_confirm(self):
        self.ensure_one()
        for sub in self:
            # RECALCULER les valeurs avant création
            if sub.buy_choice == 'amount':
                #result = self.calculate_shares_with_fees(
                result = self.calculate_shares(
                    sub.nav,
                    sub.allow_fractional_parts,
                    sub.gross_amount,
                    sub.subscription_fee_rate,
                    sub.is_subscription_fee)
            else:
                #result = self.calculate_amount_from_shares(
                result=self.calculate_amount(
                    sub.nav,
                    sub.allow_fractional_parts,
                    sub.parts,
                    sub.subscription_fee_rate,
                    sub.is_subscription_fee
                )

            # Utiliser les valeurs recalculées
            net_amount = result.get('net_amount', 0.0)
            subscription_fee_amount = result.get('fees_amount', 0.0)
            amount_remaining = result.get('amount_remaining', 0.0)
            gross_amount = result.get('gross_amount', sub.gross_amount)
            parts = result.get('shares', 0.0)

            # Sécurité multi-company
            # if self.env.company != self.company_id:
            #    raise UserError(_("Contexte société incorrect."))

            # Investisseur validé pour le fonds
            fund_inv = self.env['efund.fund.investor'].search([
                ('investor_id', '=', sub.investor_id.id),
                ('fund_id', '=', sub.fund_id.id),
                ('state', '=', 'validated')
            ], limit=1)

            if not fund_inv:
                raise UserError(_("Investisseur non validé pour ce fonds."))

            # Solde disponible suffisant
            if sub.cash_account_id.balance < sub.gross_amount:
                raise UserError(_("Solde espèces insuffisant."))

            # Création de l’ORDRE de souscription
            self.env['efund.investor.subscription'].create({
                'fund_id': sub.fund_id.id,
                'investor_id': sub.investor_id.id,
                'cash_account_id': sub.cash_account_id.id,
                'part_account_id': sub.part_account_id.id,
                'gross_amount': gross_amount,
                'amount_remaining': amount_remaining,
                'subscription_fee_amount': subscription_fee_amount,
                'share_class_id': sub.share_class_id.id,
                'net_amount': net_amount,
                'shares': parts,
                'nav': sub.nav,
                'is_subscription_fee': sub.is_subscription_fee,
                'state': 'draft',
            })
