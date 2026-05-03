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
    fund_id = fields.Many2one('efund.vehicule.fund', string="Fonds", required=True, index=True)
    vehicule_id = fields.Many2one(related='fund_id.vehicule_id', store=True, )

    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    total_shares = fields.Float(string="Total de parts", related="part_account_id.total_parts", readonly=True)
    shares = fields.Float(string="Nombre de parts")

    net_amount = fields.Monetary(string="Montant utilisé", compute="_compute_redemption", store=True, readonly = False,)
    amount_remaining = fields.Monetary(string="Montant restitué", compute="_compute_redemption", store=True, readonly = False,)
    redemption_fee_amount = fields.Monetary(string="Frais de souscription", compute="_compute_redemption",store=True, readonly = False)

    buy_choice = fields.Selection([('amount', 'Montant'), ('share', 'Part')], string="Choix d'achat", default='amount')
    is_redemption_fee = fields.Boolean(string="Appliquer Frais de souscription", default=True, store=True)

    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées", related='fund_id.allow_fractional_parts', )
    total_parts_available = fields.Float(string=" Nombre total de parts", related="part_account_id.total_parts",
                                         readonly=True)
    nav_date = fields.Date(string="Date VL appliquée" )
    nav = fields.Float(string="VL estimée",)# compute="_compute_nav_value", help="Valeur Liquidative ", store=True,readonly = False,)
    redemption_fee_rate = fields.Float(string=" % Frais de rachat",)# compute="_compute_nav_value", store=True, readonly=False)
    exit_load = fields.Float(related="share_class_id.entry_load", string="Taux frais de souscription (%)", store=True)
    gross_amount = fields.Monetary(string="Montant", )


    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------
    part_account_id = fields.Many2one('efund.investor.part_account', string="Compte Titres",
                                      compute="_compute_accounts",
                                      store=True, readonly=True, precompute=True, required=True)
    cash_account_id = fields.Many2one('efund.investor.cash_account', string="Compte Espèces",
                                      compute="_compute_accounts",
                                      store=True, readonly=True, precompute=True, required=True)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", store=True)

    # Compartiments de la VL par part (à titre informatif ou saisie)
    # Capital
    vl_capital_init = fields.Float(related='share_class_id.vl_capital_init', string="VL Capital (Début Période)",
                                   digits=(12, 4))
    vl_non_distribuable = fields.Float(related='share_class_id.vl_non_distribuable', string="VL Sommes Non Distrib.",
                                       digits=(12, 4))

    # revenu
    vl_res_anterieurs = fields.Float(related='share_class_id.vl_res_anterieurs', string="VL Résult. Antérieurs",
                                     digits=(12, 4))
    vl_res_clos = fields.Float(related='share_class_id.vl_res_clos', string="VL Résult. Exercice Clos", digits=(12, 4))
    vl_res_en_cours = fields.Float(related='share_class_id.vl_res_en_cours', string="VL Résult. en Cours (ICNE)",
                                   digits=(12, 4))

    # Montants calculés pour le payload comptable
    amount_capital = fields.Monetary(string="Part Capital", compute="_compute_decomposition_amounts", store=True)
    amount_non_distribuable = fields.Monetary(string="Part Non Distrib.", compute="_compute_decomposition_amounts",
                                              store=True)
    amount_res_anterieurs = fields.Monetary(string="Part Résult. Antérieurs", compute="_compute_decomposition_amounts",
                                            store=True)
    amount_res_clos = fields.Monetary(string="Part Résult. Exercice Clos", compute="_compute_decomposition_amounts",
                                      store=True)
    amount_income_current = fields.Monetary(string="Part Résult. en Cours", compute="_compute_decomposition_amounts",
                                            store=True)



    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------
    #part_account_id = fields.Many2one('efund.investor.part', string="Compte Titre", required=True, readonly=True)
    #cash_account_id = fields.Many2one('efund.investor.cash', string="Compte Espèces", required=True, readonly=True)
    #fund_id = fields.Many2one(related='part_account_id.fund_id', string="Fonds", store=True)
    share_class_id = fields.Many2one('efund.fund.share.class', string="Classe de part",
                                     domain="[('fund_id', '=', fund_id)]")
    #investor_id = fields.Many2one(related='part_account_id.investor_id', store=True)
    #company_id = fields.Many2one(related='fund_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)

    #investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Cash Investisseur", readonly=True)
    #fund_cash_move_id = fields.Many2one('efund.fund.cash.move', string="Cash Fond", readonly=True)
    operation_fee_move_id = fields.Many2one('efund.investor.operation.fee', string="Frais souscription", readonly=True)

    # -----------------------------------------------------------------
    # LES METHODES
    # -----------------------------------------------------------------

    @api.depends('investor_id', 'fund_id')
    def _compute_accounts(self):
        for rec in self:
            if rec.investor_id and rec.fund_id:
                # On cherche le compte titre lié à cet investisseur pour ce véhicule
                rec.part_account_id = self.env['efund.investor.part_account'].search([
                    ('investor_id', '=', rec.investor_id.id),
                    ('vehicule_id', '=', rec.fund_id.vehicule_id.id)
                ], limit=1)

                # On cherche le compte espèces
                rec.cash_account_id = self.env['efund.investor.cash_account'].search([
                    ('investor_id', '=', rec.investor_id.id),
                    ('vehicule_id', '=', rec.fund_id.vehicule_id.id)
                ], limit=1)

    @api.depends('shares', 'gross_amount', 'vl_capital_init', 'vl_non_distribuable', 'vl_res_anterieurs', 'vl_res_clos',
                 'vl_res_en_cours')
    def _compute_decomposition_amounts(self):
        for rec in self:
            rec.amount_capital = rec.shares * rec.vl_capital_init
            rec.amount_non_distribuable = rec.shares * rec.vl_non_distribuable
            rec.amount_res_anterieurs = rec.shares * rec.vl_res_anterieurs
            rec.amount_res_clos = rec.shares * rec.vl_res_clos
            rec.amount_income_current = rec.shares * rec.vl_res_en_cours

    """
    @api.depends('gross_amount', 'is_redemption_fee')
    def _compute_redemption(self):
        for sub in self:
            if sub.gross_amount:
                nav = self.env['efund.service'].get_last_nav_value(sub.fund_id)
                if sub.buy_choice == 'amount':
                    result = self.calculate_shares(nav, sub.allow_fractional_parts, sub.gross_amount,
                                                   sub.entry_load, sub.is_redemption_fee)
                else:
                    result = self.calculate_amount(nav, sub.allow_fractional_parts, sub.shares,
                                                   sub.entry_load, sub.is_redemption_fee)

                # affectation des valeurs
                sub.net_amount = result.get('net_amount')
                sub.redemption_fee_amount = result.get('fees_amount')
                sub.amount_remaining = result.get('amount_remaining')
                sub.gross_amount = result.get('gross_amount')
                sub.shares = result.get('shares')
                sub.vehicule_id = sub.fund_id.vehicule_id
    
    """

    def calculate_shares(self, nav, allow_fractional_shares, gross_amount, fee_percent, apply_subscription_fees):
        """
        Calcule le nombre de parts à partir d'un montant de souscription.

        :param nav: Valeur liquidative
        :param allow_fractional_shares: bool - parts fractionnaires autorisées
        :param gross_amount: Montant brut souscrit
        :param fee_percent: Pourcentage de frais de souscription
        :param apply_subscription_fees: bool - appliquer ou non les frais
        """

        # 1️⃣ Calcul des frais
        if apply_subscription_fees:
            if fee_percent:
                fees_amount = gross_amount * fee_percent
            else:
                raise UserError(f"Merci de renseigner le taux de souscription dans la classe de part.")
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
            if shares < 0:
                raise UserError(
                    f"Le montant de souscription doit supérieur à {nav} en tenant en compte les frais le cas échéant")

        # 5️⃣ Montant réellement investi
        actual_amount_invested = shares * nav

        # 6️⃣ Reliquat (sur le montant NET)
        amount_remaining = net_amount_to_invest - actual_amount_invested
        net_amount = gross_amount - amount_remaining - fees_amount

        # Sécurité flottants
        if float_is_zero(amount_remaining, precision_rounding=0.01):
            amount_remaining = 0.0


        return {
            'gross_amount': gross_amount,
            'fees_amount': fees_amount,
            'net_amount': net_amount,
            'shares': shares,
            'amount_used': actual_amount_invested,
            'amount_remaining': amount_remaining,
            'fees_applied': apply_subscription_fees,
        }

    def calculate_amount(self, nav, allow_fractional_shares, shares_to_buy, fee_percent, apply_subscription_fees):
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

            gross_amount = net_amount / (1 - fee_percent)
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


    @api.depends('gross_amount', 'shares','is_redemption_fee')
    def _compute_redemption(self):
        for sub in self:
            nav = self.env['efund.service'].get_last_nav_value(sub.fund_id)
            share_class = self.env['efund.fund.share.class'].search([
                ('vehicule_fund_id', '=', sub.fund_id.id),
                ('is_default', '=', True)
            ])
            sub.exit_load = share_class.exit_load
            if sub.buy_choice == 'amount':
                result = self.calculate_redemption_update(nav, sub.allow_fractional_parts, sub.exit_load,sub.is_redemption_fee,
                                                   sub.gross_amount, None)
            else:
                result = self.calculate_redemption_update(nav, sub.allow_fractional_parts, sub.exit_load,sub.is_redemption_fee,
                                                   None, sub.shares)

            # affectation des valeurs
            sub.net_amount = result.get('net_amount_to_receive')
            sub.redemption_fee_amount = result.get('fees_amount')
            sub.gross_amount = result.get('gross_amount')
            sub.shares = result.get('shares_to_redeem')

    @api.depends('fund_id')
    def _compute_nav_value(self):
        for sub in self:
            if sub.fund_id:
                share_class = self.env['efund.fund.share.class'].search([
                    ('vehicule_fund_id', '=', sub.fund_id.id),
                    ('is_default', '=', True)
                ])
                if share_class:
                    nav = self.env['efund.service'].get_last_nav_value(sub.fund_id)
                    sub.nav = nav
                    sub.exit_load = share_class.exit_load
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
        effective_fee_rate = fee_percent if apply_redemption_fee else 0.0

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

    def action_account(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("La souscription doit être validée avant exécution."))

                # Solde disponible suffisant
            if self.part_account_id.total_parts < self.shares:
                raise UserError(_("Solde part insuffisant."))

            """

                # récupération des taux des droits
            share_class = self.env['efund.fund.share.class'].search([
                ('vehicule_fund_id', '=', rec.fund_id.id),
                ('is_default', '=', True)
            ])
            entry_load = share_class.entry_load
            nav = self.env['efund.service'].get_last_nav_value(rec.fund_id)       

            fund_cash = self.env['efund.vehicule.cash'].search([
                ('vehicule_id', '=', rec.fund_id.id),
            ])

            vl = nav
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if rec.total_parts_available < rec.parts_to_redeem:
                raise UserError(_("Nombre de parts insuffisant."))

            if fund_cash and fund_cash.balance < rec.gross_amount :
                raise UserError("Le fond n'a pas assez de liquidité pour le rachat. Merci de faire un désinvestissement ou de diminuer le montant ou le nombre de parts")
            """

            if rec.nav != rec.nav: # vl:
                return rec._open_confirmation_wizard(
                    message="la VL a changé depuis la soumission du rachat. La nouvelle VL sera appliquée, Voulez-vous continuer?",
                    method_name='action_execute_confirmed'
                )
            else:
                # RECALCULER les valeurs avant création
                fee_id = 0
                """
                if rec.buy_choice == 'amount':
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       rec.desired_amount, None)
                else:
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       None, rec.parts_to_redeem)

                shares = result.get('shares_to_redeem')
                gross_amount = result.get('gross_amount')
                fees_amount = result.get('fees_amount')
                rec.net_amount = result.get('net_amount_to_receive')
                rec.redemption_fee_amount = result.get('fees_amount')
                rec.net_amount = result.get('net_amount_to_receive')  
                """


                rec.write({
                    'shares': rec.shares,
                    'nav': rec.nav,
                    'gross_amount': rec.gross_amount,
                    'redemption_fee_amount': rec.redemption_fee_amount,
                    'net_amount': rec.net_amount,
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
                    'shares': rec.shares,
                    'state': 'reconciled',
                })
                rec.message_post(
                    body=_("Débit du compte du titre de l'investisseur de %s parts.") % (rec.shares),
                    subject="comptabilisation du rachat",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )
                # 2- Débit compte cash du fond
                fund_cash = self.env['efund.vehicule.cash'].search([
                    ('vehicule_id', '=', rec.fund_id.vehicule_id.id)
                ], limit=1)
                if not fund_cash:
                    fund_cash = self.env['efund.vehicule.cash'].create({
                        'name': f"Compte cash - {rec.fund_id.vehicule_id.name}",
                        'vehicule_id': rec.fund_id.vehicule_id.id,
                        'company_id': rec.fund_id.vehicule_id.company_id.id,
                    })

                fund_move = self.env['efund.vehicule.cash.move'].create({
                    'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                    'vehicule_cash_id': fund_cash.id,
                    'amount': rec.gross_amount,
                    'move_type': 'redemption_out',
                    'liquidity_type': 'liquid',
                    'state': 'reconciled',
                    'label': f"Rachat N°{rec.name} du fond {rec.fund_id.name} ",
                    'date': rec.date_valeur,
                    'value_date': rec.date_valeur,
                    #'investor_cash_move_id': investor_titre_move.id,
                    'investor_id': rec.investor_id.id,
                    'vehicule_id': rec.fund_id.vehicule_id.id,
                    'redemption_id': rec.id,
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
                        'fund_cash_move_id': fund_move.id,
                        'investor_id': rec.investor_id.id,
                        'redemption_id': rec.id,
                        'gross_amount': rec.gross_amount,
                        'base_amount': rec.net_amount,
                        'fee_rate': rec.redemption_fee_rate,
                        'fee_amount': rec.redemption_fee_amount,
                    })
                    rec.message_post(
                        body=_("Crédit du compte des frais au montant de %s francs") % (rec.redemption_fee_amount),
                        subject="comptabilisation du rachat",
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment"
                    )
                    fee_id = operation_fee_move.id

                # 5- Crédit du compte cash de l'investisseur
                investor_cash_move = self.env['efund.investor.cash_account.move'].create({
                    'cash_account_id': rec.cash_account_id.id,
                    'move_type': 'redemption_net',
                    'amount': rec.net_amount,
                    'fund_cash_move_id': fund_move.id,
                    'redemption_id' : rec.id,
                    'state': 'reconciled',
                })
                rec.message_post(
                    body=_("Crédit du compte investisseur au montant de %s pour le rachat") % (rec.net_amount),
                    subject="comptabilisation de la souscription",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

                #Mise à jour référence
                fund_move.write({
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
            fund_cash = self.env['efund.vehicule.cash'].search([
                ('vehicule_id', '=', rec.fund_id.id),
            ])

            if fund_cash and fund_cash.balance < rec.gross_amount:
                raise UserError(
                    "Le fond n'a pas assez de liquidité pour le rachat. Merci de faire un désinvestissement ou de diminuer le montant ou le nombre de parts")


            vl = self.env['efund.service'].get_last_nav_value(rec.fund_id)
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if rec.total_parts_available < rec.shares:
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
                                                       rec.gross_amount, None)
                else:
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       None, rec.shares)

                shares = result.get('shares_to_redeem')
                gross_amount = result.get('gross_amount')
                fees_amount = result.get('fees_amount')
                rec.net_amount = result.get('net_amount_to_receive')
                rec.redemption_fee_amount = fees_amount
                rec.shares = result.get('shares_to_redeem')

                rec.write({
                    'shares': shares,
                    'gross_amount': gross_amount,
                    'redemption_fee_amount': rec.redemption_fee_amount,
                    'net_amount': rec.net_amount,
                    'state': 'validated'
                })

    def action_execute_confirmed(self):
        for rec in self:
            # RECALCULER les valeurs avant création
            if rec.buy_choice == 'amount':
                result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                   rec.gross_amount, None)
            else:
                result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                   None, rec.shares)


            gross_amount = result.get('gross_amount')
            rec.net_amount = result.get('net_amount_to_receive')
            rec.redemption_fee_amount = result.get('fees_amount')
            rec.shares = result.get('shares_to_redeem')

            rec.write({
                'shares': rec.shares,
                'gross_amount': gross_amount,
                'redemption_fee_amount': rec.redemption_fee_amount,
                'net_amount': rec.net_amount,
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
            fund_cash = self.env['efund.vehicule.cash'].search([
                ('vehicule_id', '=', rec.fund_id.id),
            ])

            if fund_cash and fund_cash.balance < rec.gross_amount:
                raise UserError(
                    "Le fond n'a pas assez de liquidité pour le rachat. Merci de faire un désinvestissement ou de diminuer le montant ou le nombre de parts")

            vl = self.env['efund.service'].get_last_nav_value(rec.fund_id)
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if rec.total_parts_available < rec.shares:
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
                                                       rec.gross_amount, None)
                else:
                    result = self.calculate_redemption_update(rec.nav, rec.allow_fractional_parts, rec.redemption_fee_rate,rec.is_redemption_fee,
                                                       None, rec.shares)


                gross_amount = result.get('gross_amount')
                rec.shares = result.get('shares_to_redeem')
                rec.net_amount = result.get('net_amount_to_receive')
                rec.redemption_fee_amount = result.get('fees_amount')

                rec.write({
                    'shares': rec.shares,
                    'gross_amount': gross_amount,
                    'redemption_fee_amount': rec.redemption_fee_amount,
                    'net_amount': rec.net_amount,
                    'state': 'submitted'
                })

