import logging
import math

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round, float_is_zero

_logger = logging.getLogger(__name__)


class FundRedemptionWizard(models.TransientModel):
    _name = 'efund.investor.redemption.wizard'
    _description = 'Wizard de rachat'

    part_account_id = fields.Many2one('efund.investor.part', required=True, readonly=True)
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    cash_account_id = fields.Many2one('efund.investor.cash', required=True, readonly=True)
    total_parts_available = fields.Float(string="Nombre total de parts", related="part_account_id.total_parts",
                                         readonly=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id', store=True)
    investor_id = fields.Many2one(related='part_account_id.investor_id', store=True)
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

    # -------------------------
    # COMPUTE
    # -------------------------
    @api.onchange('desired_amount', 'parts_to_redeem')
    def _onchange_desired_amount_or_part(self):
        for sub in self:
            if sub.buy_choice == 'amount':
                result = self.calculate_redemption(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,
                                                         sub.desired_amount,None)
            else:
                result = self.calculate_redemption(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,
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

    def calculate_redemption(self, nav,allow_fractional_shares, fee_percent, amount_net_target=None, shares_to_redeem=None):
        if nav <= 0:
            return {'error': "La valeur liquidative doit être supérieure à 0."}
        if fee_percent >= 100:
            return {'error': "Les frais de rachat ne peuvent pas atteindre 100%."}

        # --- SCÉNARIO A : ON VEUT UN MONTANT NET PRÉCIS ---
        if amount_net_target:
            # Formule : Net = Brut - (Brut * %frais) => Net = Brut * (1 - %frais)
            # Et Brut = NbParts * NAV
            # Donc : NbParts = Net / (NAV * (1 - %frais))
            raw_shares = amount_net_target / (nav * (1 - (fee_percent / 100.0)))
            _logger.info(f"***** Calculating redemption shares for net amount: {amount_net_target}, NAV: {nav}, fee_percent: {fee_percent}, shares: {raw_shares}")

            if allow_fractional_shares:
                shares = float_round(raw_shares, 6)
            else:
                # On arrondit au supérieur car pour avoir AU MOINS le montant net,
                # il faut souvent racheter la part entière du dessus
                shares = int(raw_shares) if float_is_zero(raw_shares % 1, precision_rounding=0.001) else int(
                    raw_shares) + 1

        # --- SCÉNARIO B : ON VEUT RACHETER UN NOMBRE DE PARTS PRÉCIS ---
        elif shares_to_redeem:
            shares = shares_to_redeem
            if not allow_fractional_shares:
                shares = int(shares)

        else:
            return {'error': "Veuillez préciser soit un montant net, soit un nombre de parts."}

        # --- CALCULS FINAUX (BASÉS SUR LE NOMBRE DE PARTS RETENU) ---
        gross_amount = shares * nav
        fees_amount = gross_amount * (fee_percent / 100.0)
        net_amount_to_pay = gross_amount - fees_amount

        # Arrondi monétaire
        currency_precision = 6

        return {
            'shares_to_redeem': shares,
            'gross_amount': float_round(gross_amount, precision_digits=currency_precision),
            'fees_amount': float_round(fees_amount, precision_digits=currency_precision),
            'net_amount_to_receive': float_round(net_amount_to_pay, precision_digits=currency_precision),
        }


    def action_confirm(self):
        self.ensure_one()
        for sub in self:
            # RECALCULER les valeurs avant création
            if sub.buy_choice == 'amount':
                result = self.calculate_redemption(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,
                                                   sub.desired_amount, None)
            else:
                result = self.calculate_redemption(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,
                                                   None, sub.parts_to_redeem)

            shares = result.get('shares_to_redeem')
            gross_amount = result.get('gross_amount')
            fees_amount = result.get('fees_amount')
            net_amount_to_pay = result.get('net_amount_to_receive')

            _logger.info("********************* Valeur net_amount_to_pay : %s", shares)


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
                'state': 'draft',
            })
