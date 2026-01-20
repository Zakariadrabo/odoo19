import logging
import math

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round, float_is_zero

_logger = logging.getLogger(__name__)


class FundRedemptionWizard(models.TransientModel):
    _name = 'efund.investor.redemption.wizard'
    _description = 'Wizard de rachat'

    part_account_id = fields.Many2one('efund.investor.part', string="Compte Titre", required=True, readonly=True)
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    cash_account_id = fields.Many2one('efund.investor.cash', required=True, readonly=True)
    total_parts_available = fields.Float(string="Nombre total de parts", related="part_account_id.total_parts",
                                         readonly=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id', string="Fonds", store=True)
    investor_id = fields.Many2one(related='part_account_id.investor_id', string="Investisseur", store=True)
    company_id = fields.Many2one(related='fund_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées",related='part_account_id.fund_id.allow_fractional_parts', )
    # rachat
    parts_to_redeem = fields.Float(string="Nombre de parts", store=True)
    buy_choice = fields.Selection([('amount', 'Montant'), ('share', 'Part')], string="Choix d'achat", default='share')

    # info VL (prévisionnelle)
    nav_date = fields.Date(string="Date VL appliquée", default=fields.Date.context_today, required=True)
    nav = fields.Float(string="VL estimée", compute="_compute_nav_value", help="VL indicative (à confirmer)", store=True )

    net_amount = fields.Monetary(string="Montant à percevoir", readonly=True, )
    # frais rachat
    redemption_fee_amount = fields.Monetary(string="Frais de rachat",store=True, readonly=True)
    redemption_fee_rate = fields.Float(string=" % Frais de rachat",compute="_compute_nav_value", store=True, readonly=True)
    gross_amount = fields.Monetary(string="Montant + frais", )
    desired_amount = fields.Monetary(string="Montant souhaité")
    share_class_id = fields.Many2one('efund.fund.share.class', string="Classe de part", compute="_compute_nav_value", store=True)
    is_redemption_fee = fields.Boolean(string="Appliquer Frais", default=True)

    # -------------------------
    # COMPUTE
    # -------------------------
    @api.onchange('desired_amount', 'parts_to_redeem', 'is_redemption_fee')
    def _onchange_desired_amount_or_part(self):
        for sub in self:
            if sub.buy_choice == 'amount':
                result = self.calculate_redemption_update(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,sub.is_redemption_fee,
                                                         sub.desired_amount,None)
            else:
                result = self.calculate_redemption_update(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,sub.is_redemption_fee,
                                                         None,sub.parts_to_redeem)

            # affectation des valeurs
            sub.net_amount = result.get('net_amount_to_receive')
            sub.redemption_fee_amount = result.get('fees_amount')
            sub.gross_amount = result.get('gross_amount')
            sub.parts_to_redeem = result.get('shares_to_redeem')

    @api.depends('fund_id')
    def _compute_nav_value(self):
        for sub in self:
            share_class = self.env['efund.fund.share.class'].search([
                ('fund_id', '=', sub.fund_id.id),
                ('is_default', '=', True)
            ])
            if share_class:
                sub.nav = share_class.current_nav
                sub.redemption_fee_rate = share_class.redemption_fee_rate
                sub.share_class_id = share_class.id
            else:
                raise UserError("Besoin d'avoir la classe de parts par défaut pour le fonds")

    def calculate_redemption_update(
            self,
            nav,
            allow_fractional_shares,
            fee_percent,
            apply_redemption_fee=True,
            amount_net_target=None,
            shares_to_redeem=None
    ):
        """
        Calcule un rachat de parts (OPCVM / FCP)

        - Soit à partir d'un montant net à recevoir
        - Soit à partir d'un nombre de parts à racheter
        """

        # --- CONTRÔLES DE BASE ---
        if nav <= 0:
            return {'error': "La valeur liquidative doit être strictement supérieure à 0."}

        if apply_redemption_fee and fee_percent >= 100:
            return {'error': "Les frais de rachat ne peuvent pas atteindre 100%."}

        # Taux de frais effectif
        effective_fee_rate = (fee_percent / 100.0) if apply_redemption_fee else 0.0

        # --- DÉTERMINATION DU NOMBRE DE PARTS ---
        if amount_net_target is not None:
            if amount_net_target <= 0:
                return {'error': "Le montant net doit être supérieur à 0."}

            # Net = Gross * (1 - fee)
            # Gross = Shares * NAV
            # => Shares = Net / (NAV * (1 - fee))
            denominator = nav * (1 - effective_fee_rate)

            if float_is_zero(denominator, precision_rounding=0.0000001):
                return {'error': "Paramètres invalides pour le calcul du rachat."}

            raw_shares = amount_net_target / denominator

            if allow_fractional_shares:
                shares = float_round(raw_shares, precision_digits=6)
            else:
                # Arrondi supérieur pour garantir AU MOINS le montant net demandé
                shares = int(raw_shares)
                if not float_is_zero(raw_shares - shares, precision_rounding=0.000001):
                    shares += 1

        elif shares_to_redeem is not None:
            if shares_to_redeem <= 0:
                return {'error': "Le nombre de parts à racheter doit être supérieur à 0."}

            shares = shares_to_redeem
            if not allow_fractional_shares:
                shares = int(shares)

        else:
            return {'error': "Veuillez préciser soit un montant net cible, soit un nombre de parts à racheter."}

        # --- CALCULS FINANCIERS ---
        gross_amount = shares * nav
        fees_amount = gross_amount * effective_fee_rate
        net_amount_to_receive = gross_amount - fees_amount

        # --- ARRONDIS MONÉTAIRES ---
        currency_precision = 6

        return {
            'shares_to_redeem': shares,
            'gross_amount': float_round(gross_amount, precision_digits=currency_precision),
            'fees_amount': float_round(fees_amount, precision_digits=currency_precision),
            'net_amount_to_receive': float_round(net_amount_to_receive, precision_digits=currency_precision),
            'fee_applied': apply_redemption_fee,
            'fee_rate_percent': fee_percent if apply_redemption_fee else 0.0,
        }


    def action_confirm(self):
        self.ensure_one()
        for sub in self:
            # RECALCULER les valeurs avant création
            if sub.buy_choice == 'amount':
                result = self.calculate_redemption_update(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,sub.is_redemption_fee,
                                                   sub.desired_amount, None)
            else:
                result = self.calculate_redemption_update(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate, sub.is_redemption_fee,
                                                   None, sub.parts_to_redeem)

            shares = result.get('shares_to_redeem')
            gross_amount = result.get('gross_amount')
            fees_amount = result.get('fees_amount')
            net_amount_to_pay = result.get('net_amount_to_receive')


            if shares > sub.total_parts_available:
                raise UserError(_("Nombre de parts insuffisant."))



            # Investisseur validé pour le fonds
            fund_inv = self.env['efund.fund.investor'].search([
                ('investor_id', '=', sub.investor_id.id),
                ('fund_id', '=', self.fund_id.id),
                ('state', '=', 'validated')
            ], limit=1)

            if not fund_inv:
                raise UserError(_("Investisseur non validé pour ce fonds."))


            # Création de l’ORDRE de rachat
            self.env['efund.investor.redemption'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.investor.redemption'),
                'fund_id': sub.fund_id.id,
                'investor_id': sub.investor_id.id,
                'cash_account_id': sub.cash_account_id.id,
                'part_account_id': sub.part_account_id.id,
                'date_operation': sub.date_operation,
                'nav_date': sub.nav_date,
                'nav': sub.nav,
                'net_amount': net_amount_to_pay,
                'parts_to_redeem': shares,
                'gross_amount': gross_amount,
                'redemption_fee_amount': fees_amount,
                'redemption_fee_rate': sub.redemption_fee_rate,
                'share_class_id': sub.share_class_id.id,
                'is_redemption_fee': sub.is_redemption_fee,
                'state': 'draft',
            })
