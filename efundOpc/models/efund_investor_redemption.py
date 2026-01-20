import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.tools import float_round, float_is_zero

_logger = logging.getLogger(__name__)


class FundRedemption(models.Model):
    _name = 'efund.investor.redemption'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _description = 'Opération de retrait de fonds'

    name = fields.Char(string="Référence", default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.redemption'))
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées",
                                            related='part_account_id.fund_id.allow_fractional_parts', )
    total_parts_available = fields.Float(string=" Nombre total de parts", related="part_account_id.total_parts",
                                         readonly=True)
    buy_choice = fields.Selection([('amount', 'Montant'), ('share', 'Part')], string="Choix d'achat", default='share')
    parts_to_redeem = fields.Float(string="Nombre de parts", store=True)
    nav_date = fields.Date(string="Date VL appliquée", default=fields.Date.context_today, required=True)
    nav = fields.Float(string="VL estimée", compute="_compute_nav_value", help="Valeur Liquidative ", store=True)
    net_amount = fields.Monetary(string="Montant à percevoir", readonly=True, )
    redemption_fee_amount = fields.Monetary(string="Frais de rachat", store=True, readonly=True)
    redemption_fee_rate = fields.Float(string=" % Frais de rachat", compute="_compute_nav_value", store=True,
                                       readonly=True)
    gross_amount = fields.Monetary(string="Montant + frais", )
    desired_amount = fields.Monetary(string="Montant souhaité")

    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------
    part_account_id = fields.Many2one('efund.investor.part', string="Compte Titre", required=True, readonly=True)
    cash_account_id = fields.Many2one('efund.investor.cash', string="Compte Espèces", required=True, readonly=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id', string="Fonds", store=True)
    share_class_id = fields.Many2one('efund.fund.share.class', string="Classe de part",
                                     domain="[('fund_id', '=', fund_id)]")
    investor_id = fields.Many2one(related='part_account_id.investor_id', store=True)
    company_id = fields.Many2one(related='fund_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)

    investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Cash Investisseur", readonly=True)
    fund_cash_move_id = fields.Many2one('efund.fund.cash.move', string="Cash Fond", readonly=True)
    operation_fee_move_id = fields.Many2one('efund.investor.operation.fee', string="Frais souscription", readonly=True)
    is_redemption_fee = fields.Boolean(string="Appliquer Frais", default=True)
    # -----------------------------------------------------------------
    # LES METHODES
    # -----------------------------------------------------------------
    @api.onchange('desired_amount', 'parts_to_redeem','is_redemption_fee')
    def _onchange_desired_amount_or_part(self):
        for sub in self:
            if sub.buy_choice == 'amount':
                result = self.calculate_redemption_update(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,sub.is_redemption_fee,
                                                   sub.desired_amount, None)
            else:
                result = self.calculate_redemption_update(sub.nav, sub.allow_fractional_parts, sub.redemption_fee_rate,sub.is_redemption_fee,
                                                   None, sub.parts_to_redeem)

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

    def calculate_redemption(self, nav, allow_fractional_shares, fee_percent, amount_net_target=None,
                             shares_to_redeem=None):
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
            _logger.info(
                f"***** Calculating redemption shares for net amount: {amount_net_target}, NAV: {nav}, fee_percent: {fee_percent}, shares: {raw_shares}")

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

    def action_account_redemption(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("Le rachat doit être validée avant exécution."))

            share_class = self.env['efund.fund.share.class'].search([
                ('fund_id', '=', rec.fund_id.id),
                ('is_default', '=', True)
            ])
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', rec.fund_id.id),
            ])

            vl = share_class.current_nav
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if rec.total_parts_available < rec.parts_to_redeem:
                raise UserError(_("Nombre de parts insuffisant."))

            if fund_cash and fund_cash.balance < rec.gross_amount :
                raise UserError("Le fond n'a pas assez de liquidité pour le rachat. Merci de faire un désinvestissement ou de diminuer le montant ou le nombre de parts")

            if rec.nav != vl:
                return rec._open_confirmation_wizard(
                    message="la VL a changé depuis la soumission du rachat. La nouvelle VL sera appliquée, Voulez-vous continuer?",
                    method_name='action_execute_confirmed'
                )
            else:
                # RECALCULER les valeurs avant création
                fee_id = 0
                if rec.buy_choice == 'amount':
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       rec.desired_amount, None)
                else:
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       None, rec.parts_to_redeem)

                shares = result.get('shares_to_redeem')
                gross_amount = result.get('gross_amount')
                fees_amount = result.get('fees_amount')
                net_amount_to_pay = result.get('net_amount_to_receive')

                rec.write({
                    'parts_to_redeem': shares,
                    'gross_amount': gross_amount,
                    'redemption_fee_amount': fees_amount,
                    'net_amount': net_amount_to_pay,
                    'date_valeur': fields.Datetime.now(),
                    'state': 'accounted'
                })

                rec.message_post(
                    body=_("Comptabilisation du rachat. Lancement de la réconciliation..."),
                    subject="comptabilisation du rachat",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

                # 1- Débit du compte titre de l'investisseur
                # 2️⃣ Sortie de parts
                investor_titre_move = self.env['efund.investor.part.move'].create({
                    'part_account_id': rec.part_account_id.id,
                    'move_type': 'redemption',
                    'redemption_id': rec.id,
                    'shares': shares,
                    'state': 'reconciled',
                })
                rec.message_post(
                    body=_("Débit du compte du titre de l'investisseur de %s parts.") % (shares),
                    subject="comptabilisation du rachat",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )
                # 2- Débit compte cash du fond
                fund_cash = self.env['efund.fund.cash'].search([
                    ('fund_id', '=', rec.fund_id.id)
                ], limit=1)
                if not fund_cash:
                    raise UserError(_("Le fond n'a pas de compte de caisse."))

                fund_cash_move = self.env['efund.fund.cash.move'].create({
                    'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                    'fund_cash_id': fund_cash.id,
                    'amount': rec.gross_amount,
                    'move_type': 'redemption_out',
                    'liquidity_type': 'liquid',
                    'state': 'reconciled',
                    'redemption_id': rec.id,
                    'investor_id': rec.investor_id.id,
                    'fund_id': rec.fund_id.id,

                })
                rec.message_post(
                    body=_("Débit du compte cash du fond au montant de %s francs") % (rec.gross_amount),
                    subject="comptabilisation du rachat",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

                # 4- Crédit du compte frais pour le montant investi
                if rec.redemption_fee_amount > 0:
                    # Enregistrement des frais de souscription
                    operation_fee_move = self.env['efund.investor.operation.fee'].create({
                        'name': self.env['ir.sequence'].next_by_code('efund.investor.operation.fee'),
                        'fee_type': 'redemption',
                        'fund_id': rec.fund_id.id,
                        'fund_cash_move_id': fund_cash_move.id,
                        'investor_id': rec.investor_id.id,
                        'redemption_id': rec.id,
                        'gross_amount': gross_amount,
                        'base_amount': net_amount_to_pay,
                        'fee_rate': rec.redemption_fee_rate,
                        'fee_amount': fees_amount,
                    })
                    rec.message_post(
                        body=_("Crédit du compte des frais au montant de %s francs") % (fees_amount),
                        subject="comptabilisation du rachat",
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment"
                    )
                    fee_id = operation_fee_move.id

                # 5- Crédit du compte cash de l'investisseur
                investor_cash_move = self.env['efund.investor.cash.move'].create({
                    'cash_account_id': rec.cash_account_id.id,
                    'move_type': 'redemption_net',
                    'amount': net_amount_to_pay,
                    'fund_cash_move_id': fund_cash_move.id,
                    'redemption_id' : rec.id,
                    'state': 'reconciled',
                })
                rec.message_post(
                    body=_("Crédit du compte investisseur au montant de %s pour le rachat") % (net_amount_to_pay),
                    subject="comptabilisation de la souscription",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

                #Mise à jour référence
                fund_cash_move.write({
                    'investor_cash_move_id': investor_cash_move.id,
                })
                # Post du résultat sur le chatter
                rec.message_post(
                    body=_("Réconciliation terminée avec succès."),
                    subject="Réconciliation réussie",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

                rec.write({
                    'state': 'reconciled',
                })

    def action_validate_redemption(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Le rachat doit être soumis avant la validation."))

            share_class = self.env['efund.fund.share.class'].search([
                ('fund_id', '=', rec.fund_id.id),
                ('is_default', '=', True)
            ])
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', rec.fund_id.id),
            ])

            if fund_cash and fund_cash.balance < rec.gross_amount:
                raise UserError(
                    "Le fond n'a pas assez de liquidité pour le rachat. Merci de faire un désinvestissement ou de diminuer le montant ou le nombre de parts")

            vl = share_class.current_nav
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if rec.total_parts_available < rec.parts_to_redeem:
                raise UserError(_("Nombre de parts insuffisant."))

            if rec.nav != vl:
                return rec._open_confirmation_wizard(
                    message="la VL a changé depuis la soumission du rachat. La nouvelle VL sera appliquée, Voulez-vous continuer?",
                    method_name='action_execute_confirmed'
                )
            else:
                # RECALCULER les valeurs avant création
                if rec.buy_choice == 'amount':
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       rec.desired_amount, None)
                else:
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       None, rec.parts_to_redeem)

                shares = result.get('shares_to_redeem')
                gross_amount = result.get('gross_amount')
                fees_amount = result.get('fees_amount')
                net_amount_to_pay = result.get('net_amount_to_receive')

                rec.write({
                    'parts_to_redeem': shares,
                    'gross_amount': gross_amount,
                    'redemption_fee_amount': fees_amount,
                    'net_amount': net_amount_to_pay,
                    'state': 'validated'
                })

    def action_execute_confirmed(self):
        for rec in self:
            # RECALCULER les valeurs avant création
            if rec.buy_choice == 'amount':
                result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                   rec.desired_amount, None)
            else:
                result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                   None, rec.parts_to_redeem)

            shares = result.get('shares_to_redeem')
            gross_amount = result.get('gross_amount')
            fees_amount = result.get('fees_amount')
            net_amount_to_pay = result.get('net_amount_to_receive')

            rec.write({
                'parts_to_redeem': shares,
                'gross_amount': gross_amount,
                'redemption_fee_amount': fees_amount,
                'net_amount': net_amount_to_pay,
                'state': 'validated'
            })

    def action_cancel_redemption(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("Le rachat ne peut plus être annulée."))

            rec.write({'state': 'cancelled', })

    def action_submit_redemption(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Le rachat doit être en brouillon avant sa soumission."))

            share_class = self.env['efund.fund.share.class'].search([
                ('fund_id', '=', rec.fund_id.id),
                ('is_default', '=', True)
            ])
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', rec.fund_id.id),
            ])

            if fund_cash and fund_cash.balance < rec.gross_amount:
                raise UserError(
                    "Le fond n'a pas assez de liquidité pour le rachat. Merci de faire un désinvestissement ou de diminuer le montant ou le nombre de parts")

            vl = share_class.current_nav
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if rec.total_parts_available < rec.parts_to_redeem:
                raise UserError(_("Nombre de parts insuffisant."))

            if rec.nav != vl:
                return rec._open_confirmation_wizard(
                    message="la VL a changé depuis la soumission du rachat. La nouvelle VL sera appliquée, Voulez-vous continuer?",
                    method_name='action_execute_confirmed'
                )
            else:
                # RECALCULER les valeurs avant création
                if rec.buy_choice == 'amount':
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       rec.desired_amount, None)
                else:
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       None, rec.parts_to_redeem)

                shares = result.get('shares_to_redeem')
                gross_amount = result.get('gross_amount')
                fees_amount = result.get('fees_amount')
                net_amount_to_pay = result.get('net_amount_to_receive')

                rec.write({
                    'parts_to_redeem': shares,
                    'gross_amount': gross_amount,
                    'redemption_fee_amount': fees_amount,
                    'net_amount': net_amount_to_pay,
                    'state': 'submitted'
                })

