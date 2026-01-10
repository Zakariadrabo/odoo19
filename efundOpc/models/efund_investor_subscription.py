import logging
import math
from datetime import timedelta
from math import floor

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round, float_is_zero

_logger = logging.getLogger(__name__)


class FundSubscription(models.Model):
    _name = 'efund.investor.subscription'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _description = 'Opération de souscription à un fond'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.subscription'))

    is_initial = fields.Boolean(string='Initial Subscription', default=False)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    gross_amount = fields.Monetary(string="montant", currency_field="currency_id")
    shares = fields.Float(string="Nombre de parts")
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées",
                                            related='cash_account_id.fund_id.allow_fractional_parts',
                                            help="Si décoché, les souscriptions sont arrondies à l'entier inférieur.")
    nav = fields.Monetary(string="VL appliquée", readonly=True, compute="_compute_nav_value", store=True)
    net_amount = fields.Monetary(string="Montant utilisé", compute='_compute_subscription', store=True)
    amount_remaining = fields.Monetary(string="Montant restitué", compute='_compute_subscription', readonly=True,
                                       store=True)
    subscription_fee_rate = fields.Float(string="Taux frais de souscription (%)", compute="_compute_nav_value",
                                         readonly=True, store=True)
    subscription_fee_amount = fields.Monetary(string="Frais de souscription", compute='_compute_subscription',
                                              store=True)
    buy_choice = fields.Selection([('amount', 'Montant'), ('share', 'Part')], string="Choix d'achat", default='amount')

    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------
    cash_account_id = fields.Many2one('efund.investor.cash', required=True, readonly=True)
    part_account_id = fields.Many2one('efund.investor.part', required=True, readonly=True)
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    fund_id = fields.Many2one(related='cash_account_id.fund_id', store=True)
    total_shares = fields.Float(string="Total de parts", related="part_account_id.total_parts", readonly=True)
    investor_id = fields.Many2one(related='cash_account_id.investor_id', store=True)
    share_class_id = fields.Many2one('efund.fund.share.class', string="Classe de part",  # required=True,
                                     domain="[('fund_id', '=', fund_id)]")
    investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Cash Investisseur", readonly=True)
    fund_cash_move_id = fields.Many2one('efund.fund.cash.move', string="Cash Fond", readonly=True)
    operation_fee_move_id = fields.Many2one('efund.investor.operation.fee', string="Frais souscription", readonly=True)


    # -----------------------------------------------------------------
    # LES METHODES
    # -----------------------------------------------------------------
    @api.onchange('gross_amount', 'shares')
    def _onchange_gross_amount(self):
        for sub in self:
            sub.net_amount = 0
            sub.subscription_fee_amount = 0
            if sub.buy_choice == 'amount':
                result = self.calculate_shares_with_fees(sub.nav, sub.allow_fractional_parts, sub.gross_amount,
                                                         sub.subscription_fee_rate)
            else:
                result = self.calculate_amount_from_shares(sub.nav, sub.allow_fractional_parts, sub.shares,
                                                           sub.subscription_fee_rate)

            # affectation des valeurs
            sub.net_amount = result.get('net_amount')
            sub.subscription_fee_amount = result.get('fees_amount')
            sub.amount_remaining = result.get('amount_remaining')
            sub.gross_amount = result.get('gross_amount')
            sub.shares = result.get('shares')

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
            else:
                raise UserError("Besoin d'avoir la classe de parts par défaut pour le fonds")

    @api.model
    def calculate_shares_with_fees(self, nav, allow_fractional_shares, gross_amount, fee_percent):
        # 1. Calcul des frais et du montant net
        # Formule : Montant Net = Montant Brut / (1 + Frais%)
        # Ou plus commun : Frais = Brut * (Frais% / 100)
        fees_amount = gross_amount * (fee_percent / 100.0)
        net_amount_to_invest = gross_amount - fees_amount

        # 2. Calcul théorique des parts sur la base du net
        raw_shares = net_amount_to_invest / nav

        # 3. Arrondi selon les règles du fonds
        if allow_fractional_shares:
            shares = float_round(raw_shares, precision_digits=6)
        else:
            shares = int(raw_shares)

        # 4. Calcul des montants réels
        # On recalcule le montant réellement converti en parts
        actual_amount_invested = shares * nav

        # Le amount_remaining est ce qui reste du montant NET après achat des parts
        amount_remaining = net_amount_to_invest - actual_amount_invested

        # Sécurité flottants
        if float_is_zero(amount_remaining, precision_rounding=0.01):
            amount_remaining = 0.0

        return {
            'gross_amount': gross_amount,
            'fees_amount': fees_amount,
            'net_amount': net_amount_to_invest,
            'shares': shares,
            'amount_used': actual_amount_invested,  # Montant converti en parts
            'amount_remaining': amount_remaining  # amount_remaining dû aux arrondis de parts
        }

    @api.model
    def calculate_amount_from_shares(self, nav, allow_fractional_shares, shares_to_buy, fee_percent):

        if nav <= 0:
            return {'error': "La valeur liquidative (NAV) doit être positive."}

        # 1. Validation du nombre de parts (entier vs décimal)
        if not allow_fractional_shares:
            # Si le fonds n'autorise pas les virgules, on s'assure que l'entrée est entière
            shares_to_buy = int(shares_to_buy)

        # 2. Calcul du montant net (Investissement pur)
        net_amount = shares_to_buy * nav

        # 3. Calcul du montant brut (avec frais)
        # Formule : Net = Brut * (1 - %frais) => Brut = Net / (1 - %frais)
        if fee_percent >= 100:
            return {'error': "Les frais ne peuvent pas être égaux ou supérieurs à 100%."}

        gross_amount = net_amount / (1 - (fee_percent / 100.0))
        # 4. Calcul des frais en valeur monétaire
        fees_amount = gross_amount - net_amount
        amount_remaining = gross_amount - net_amount - fees_amount

        return {
            'shares': shares_to_buy,
            'net_amount': float_round(net_amount, precision_digits=4),
            'fees_amount': float_round(fees_amount, precision_digits=4),
            'gross_amount': float_round(gross_amount, precision_digits=4),
            'amount_remaining': float_round(amount_remaining, precision_digits=4),
        }

    # @api.depends('amount', 'subscription_fee_rate', 'unit_value', 'cash_used', 'parts','share_class_id')
    def _compute_subscription_fee_amount(self):
        for sub in self:
            prix_unitaire_ttc = sub.nav * (1 + sub.share_class_id.subscription_fee_rate / 100)
            if sub.allow_fractional_parts:
                # On calcule avec des décimales (souvent 4 pour les OPCVM)
                sub.shares = round(sub.amount / prix_unitaire_ttc, 4)
            else:
                # On force l'entier inférieur
                sub.shares = math.floor(sub.amount / prix_unitaire_ttc)

            montant_reel = sub.shares * prix_unitaire_ttc
            amount_remaining = sub.amount - montant_reel

            sub.net_amount = sub.shares * sub.unit_value
            sub.subscription_fee_amount = sub.shares * sub.nav * sub.share_class_id.subscription_fee_rate / 100
            sub.amount_remaining = amount_remaining

    @api.onchange('shares')
    def _onchange_parts(self):
        a_des_decimales = self.parts % 1 != 0
        if a_des_decimales and not self.allow_fractional_parts:
            raise UserError(_("Ce fonds n'accepte que des nombres de parts entières."))

    def action_account(self):
        for rec in self:
            # Déclare varaible
            fee_id = 0
            # A revoir pour la date valeur
            #if rec.date_valeur < rec.date_operation:
            #    raise UserError(_("La date de l'opération ne peut pas être supérieure à la date de valeur"))

            if rec.state != 'validated':
                raise UserError(_("La souscription doit être validée avant exécution."))

            # Solde disponible suffisant
            if self.cash_account_id.balance < self.gross_amount:
                raise UserError(_("Solde espèces insuffisant."))

            if rec.buy_choice == 'amount':
                result = self.calculate_shares_with_fees(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.gross_amount,
                    rec.subscription_fee_rate
                )
            else:
                result = self.calculate_amount_from_shares(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.shares,
                    rec.subscription_fee_rate
                )

            # Utiliser les valeurs recalculées
            net_amount = result.get('net_amount', 0.0)
            subscription_fee_amount = result.get('fees_amount', 0.0)
            amount_remaining = result.get('amount_remaining', 0.0)
            gross_amount = result.get('gross_amount', rec.gross_amount)
            shares = result.get('shares', 0.0)

            if not rec.allow_fractional_parts and shares <= 0:
                raise UserError(
                    _("Le montant est insuffisant pour souscrire au moins une part.")
                )

            # 🧾 Mise à jour
            rec.write({
                'nav': rec.nav,
                'shares': shares,
                'net_amount': net_amount,
                'amount_remaining': amount_remaining,
                'date_valeur': fields.Datetime.now(),
                'state': 'accounted',
            })

            rec.message_post(
                body=_("Comptabilisation de la souscription. Lancement de la réconciliation..."),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )
            # 1- Débit du compte investisseur pour le montant investi
            investor_cash_move = self.env['efund.investor.cash.move'].create({
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'subscription_net',
                'amount': net_amount,
            })
            rec.message_post(
                body=_("Débit du compte investisseur au montant de %s pour la souscription") % (rec.net_amount),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # 2- Débit du compte investisseur pour les frais montant investi
            if rec.subscription_fee_amount > 0:
                # Enregistrement des frais de souscription
                self.env['efund.investor.cash.move'].create({
                    'cash_account_id': rec.cash_account_id.id,
                    'move_type': 'subscription_fee',
                    'amount': self.subscription_fee_amount,
                })
                rec.message_post(
                    body=_("Débit du compte investisseur des frais de souscription au montant de %s francs") % (rec.subscription_fee_amount),
                    subject="comptabilisation de la souscription",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # 3- Crédit du compte du fond pour le montant investi
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', rec.fund_id.id)
            ], limit=1)
            if not fund_cash:
                fund_cash = self.env['efund.fund.cash'].create({
                    'name': f"Trésorerie - {rec.fund_id.name}",
                    'fund_id': rec.fund_id.id,
                    'company_id': rec.fund_id.company_id.id,
                })

            fund_move = self.env['efund.fund.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'amount': rec.net_amount,
                'move_type': 'subscription_in',
                'liquidity_type': 'liquid',
                'state': 'posted',
                'investor_cash_move_id': investor_cash_move.id,
                'investor_id': rec.investor_id.id,
                'fund_id': rec.fund_id.id,
            })
            rec.message_post(
                body=_("Crédit du compte du fond au montant de %s francs") % (rec.net_amount),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # 4- Crédit du compte frais pour le montant investi
            if rec.subscription_fee_amount > 0:
                # Enregistrement des frais de souscription
                operation_fee_move = self.env['efund.investor.operation.fee'].create({
                    'name': self.env['ir.sequence'].next_by_code('efund.investor.operation.fee'),
                    'fee_type': 'subscription',
                    'fund_id': rec.fund_id.id,
                    'investor_cash_move_id': investor_cash_move.id,
                    'investor_id': rec.investor_id.id,
                    'subscription_id': rec.id,
                    'gross_amount': rec.gross_amount,
                    'base_amount': rec.net_amount,
                    'fee_rate': rec.subscription_fee_rate,
                    'fee_amount': rec.subscription_fee_amount,
                })
                rec.message_post(
                    body=_("Crédit du compte des frais au montant de %s francs")% (rec.subscription_fee_amount),
                    subject="comptabilisation de la souscription",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )
                fee_id = operation_fee_move.id

            # 5- Crédit du compte titre de l'investisseur
            self.env['efund.investor.part.move'].create({
                'part_account_id': rec.part_account_id.id,
                'move_type': 'subscription',
                'shares': shares,
            })
            rec.message_post(
                body=_("Crédit du compte titre de l'investisseur au montant de %s part(s).") % (rec.shares),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # Fin de la réconciliation
            if rec.subscription_fee_amount > 0:
                rec.write({
                    'investor_cash_move_id': investor_cash_move.id,
                    'fund_cash_move_id': fund_move.id,
                    'operation_fee_move_id': fee_id,
                    'state': 'reconciled',
                })
            else:
                rec.write({
                    'investor_cash_move_id': investor_cash_move.id,
                    'fund_cash_move_id': fund_move.id,
                    'state': 'reconciled',
                })


            # Post du résultat sur le chatter
            rec.message_post(
                body=_("Réconciliation terminée avec succès."),
                subject="Réconciliation réussie",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )


    def action_validate_subscription(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("La souscription doit être soumise avant la validation."))
            # Solde disponible suffisant
            if rec.cash_account_id.balance < rec.gross_amount:
                raise UserError(_("Solde espèces insuffisant."))

            if rec.buy_choice == 'amount':
                result = rec.calculate_shares_with_fees(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.gross_amount,
                    rec.subscription_fee_rate
                )
            else:
                result = rec.calculate_amount_from_shares(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.shares,
                    rec.subscription_fee_rate
                )

            # Utiliser les valeurs recalculées
            net_amount = result.get('net_amount', 0.0)
            subscription_fee_amount = result.get('fees_amount', 0.0)
            amount_remaining = result.get('amount_remaining', 0.0)
            gross_amount = result.get('gross_amount', rec.gross_amount)
            shares = result.get('shares', 0.0)

            rec.write({
                'nav': rec.nav,
                'shares': shares,
                'net_amount': net_amount,
                'amount_remaining': amount_remaining,
                'subscription_fee_amount': subscription_fee_amount,
                'gross_amount': gross_amount,
                'state': 'validated',
            })


    def action_cancel_subscription(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("La souscription ne peut plus être annulée."))


    def action_submit_subscription(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("La souscription doit être en brouillon avant sa soumission."))
            # Solde disponible suffisant
            if rec.cash_account_id.balance < rec.gross_amount:
                raise UserError(_("Solde espèces insuffisant."))

            if rec.buy_choice == 'amount':
                result = rec.calculate_shares_with_fees(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.gross_amount,
                    rec.subscription_fee_rate
                )
            else:
                result = rec.calculate_amount_from_shares(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.shares,
                    rec.subscription_fee_rate
                )

                # Utiliser les valeurs recalculées
            net_amount = result.get('net_amount', 0.0)
            subscription_fee_amount = result.get('fees_amount', 0.0)
            amount_remaining = result.get('amount_remaining', 0.0)
            gross_amount = result.get('gross_amount', rec.gross_amount)
            shares = result.get('shares', 0.0)

            rec.write({
                'nav': rec.nav,
                'shares': shares,
                'net_amount': net_amount,
                'amount_remaining': amount_remaining,
                'subscription_fee_amount': subscription_fee_amount,
                'gross_amount': gross_amount,
                'state': 'submitted',
            })
