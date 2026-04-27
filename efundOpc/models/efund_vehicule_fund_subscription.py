import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools import float_round, float_is_zero

_logger = logging.getLogger(__name__)


class FundSubscription(models.Model):
    _name = 'efund.investor.subscription'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _description = 'Opération de souscription à un fond'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.subscription'))
    fund_id = fields.Many2one('efund.vehicule.fund', string="Fonds", required=True, index=True)
    vehicule_id = fields.Many2one(related='fund_id.vehicule_id',store=True, )


    is_initial = fields.Boolean(string='Souscription Initiale', default=False)
    currency_id = fields.Many2one(related='fund_id.vehicule_id.currency_id')
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    gross_amount = fields.Monetary(string="Montant", currency_field="currency_id")
    shares = fields.Float(string="Nombre de parts")

    allow_fractional_parts = fields.Boolean(string="Parts fractionnées", related='fund_id.allow_fractional_parts', )
    nav = fields.Monetary(string="VL appliquée", compute="_compute_nav_value", store=True, readonly = False, )
    entry_load = fields.Float(related="share_class_id.entry_load", string="Taux frais de souscription (%)", store=True)

    net_amount = fields.Monetary(string="Montant utilisé", compute="_compute_subscription", store=True, readonly=False)
    amount_remaining = fields.Monetary(string="Montant restitué", compute="_compute_subscription", store=True, readonly=False)
    subscription_fee_amount = fields.Monetary(string="Frais de souscription", compute="_compute_subscription", store=True, readonly=False)
    buy_choice = fields.Selection([('amount', 'Montant'), ('share', 'Part')], string="Choix d'achat", default='amount')
    is_subscription_fee = fields.Boolean(string="Appliquer Frais de souscription", default=True, store=True)

    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------
    part_account_id = fields.Many2one('efund.investor.part_account', string="Compte Titres",compute="_compute_accounts",
        store=True,readonly=False, precompute=True, )
    cash_account_id = fields.Many2one('efund.investor.cash_account',string="Compte Espèces", compute="_compute_accounts",
        store=True, readonly=False, precompute=True, )

    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)

    total_shares = fields.Float(string="Total de parts", related="part_account_id.total_parts", readonly=True)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", store=True)
    share_class_id = fields.Many2one('efund.fund.share.class', string="Classe de part", compute='_compute_get_share_class_id', store=True )
    investor_cash_move_id = fields.Many2one('efund.investor.cash_account.move', string="Cash Investisseur", readonly=True)
    fund_cash_move_id = fields.Many2one('efund.vehicule.cash.move', string="Cash Fond", readonly=True)
    operation_fee_move_id = fields.Many2one('efund.investor.operation.fee', string="Frais souscription", readonly=True)

    # Compartiments de la VL par part (à titre informatif ou saisie)
    # Capital
    vl_capital_init = fields.Float(related='share_class_id.vl_capital_init', string="VL Capital (Début Période)", digits=(12, 4))
    vl_non_distribuable = fields.Float(related='share_class_id.vl_non_distribuable', string="VL Sommes Non Distrib.", digits=(12, 4))

    # revenu
    vl_res_anterieurs = fields.Float(related='share_class_id.vl_res_anterieurs', string="VL Résult. Antérieurs",  digits=(12, 4))
    vl_res_clos = fields.Float(related='share_class_id.vl_res_clos', string="VL Résult. Exercice Clos", digits=(12, 4))
    vl_res_en_cours = fields.Float(related='share_class_id.vl_res_en_cours', string="VL Résult. en Cours (ICNE)",digits=(12, 4))

    # Montants calculés pour le payload comptable
    amount_capital = fields.Monetary(string="Part Capital", compute="_compute_decomposition_amounts", store=True)
    amount_non_distribuable = fields.Monetary(string="Part Non Distrib.", compute="_compute_decomposition_amounts", store=True)
    amount_res_anterieurs = fields.Monetary(string="Part Résult. Antérieurs", compute="_compute_decomposition_amounts", store=True)
    amount_res_clos = fields.Monetary(string="Part Résult. Exercice Clos", compute="_compute_decomposition_amounts", store=True)
    amount_income_current = fields.Monetary(string="Part Résult. en Cours", compute="_compute_decomposition_amounts", store=True)

    event_id = fields.Many2one('efund.accounting.event', string="Événement", readonly=True)

    # -----------------------------------------------------------------
    @api.onchange('gross_amount')
    def on_change_gross_amount(self):
        for rec in self:
            if rec.vehicule_id and rec.fund_id:
                if rec.gross_amount > rec.balance:
                    raise ValidationError("Le montant brut ne peut pas être supérieur au solde.")

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

                # Afficher la dernière valeur liquidative du fond
                nav = self.env['efund.service'].get_last_nav_value(rec.fund_id)
                if nav:
                    rec.nav = nav
                else:
                    raise ValidationError('Impossible de trouver la valeur liquidative du fond.')


    @api.depends('fund_id','shares')
    def _compute_get_share_class_id(self):
        if self.fund_id:
            shared_class = self.env['efund.fund.share.class'].search([
                ('vehicule_fund_id', '=', self.fund_id.id),
                ('is_default', '=', True)
            ], limit=1)

            if shared_class:
                self.share_class_id = shared_class
            else:
                # Optionnel : remettre à faux si aucun compte n'est trouvé
                self.share_class_id = False

    @api.depends('shares', 'gross_amount','vl_capital_init', 'vl_non_distribuable','vl_res_anterieurs', 'vl_res_clos', 'vl_res_en_cours')
    def _compute_decomposition_amounts(self):
        for rec in self:
            rec.amount_capital = rec.shares * rec.vl_capital_init
            rec.amount_non_distribuable = rec.shares * rec.vl_non_distribuable
            rec.amount_res_anterieurs = rec.shares * rec.vl_res_anterieurs
            rec.amount_res_clos = rec.shares * rec.vl_res_clos
            rec.amount_income_current = rec.shares * rec.vl_res_en_cours

    # LES METHODES
    @api.depends('gross_amount', 'is_subscription_fee')
    def _compute_subscription(self):
        for sub in self:
            if sub.gross_amount:
                nav = self.env['efund.service'].get_last_nav_value(sub.fund_id)
                if sub.buy_choice == 'amount':
                    result = self.calculate_shares(nav, sub.allow_fractional_parts, sub.gross_amount,
                                                   sub.entry_load, sub.is_subscription_fee)
                else:
                    result = self.calculate_amount(nav, sub.allow_fractional_parts, sub.shares,
                                                   sub.entry_load, sub.is_subscription_fee)

                # affectation des valeurs
                sub.net_amount = result.get('net_amount')
                sub.subscription_fee_amount = result.get('fees_amount')
                sub.amount_remaining = result.get('amount_remaining')
                sub.gross_amount = result.get('gross_amount')
                sub.shares = result.get('shares')
                sub.vehicule_id = sub.fund_id.vehicule_id

    # -----------------------------------------------------------------

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
                    sub.entry_load = share_class.entry_load
                else:
                    raise UserError("Besoin d'avoir la classe de parts par défaut pour le fonds")

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

    @api.onchange('shares')
    def _onchange_parts(self):
        a_des_decimales = self.shares % 1 != 0
        if a_des_decimales and not self.allow_fractional_parts:
            raise UserError(_("Ce fonds n'accepte que des nombres de parts entières."))

    def action_account(self):
        for rec in self:
            fee_id = 0
            if rec.state != 'validated':
                raise UserError(_("La souscription doit être validée avant exécution."))

            # Solde disponible suffisant
            if self.cash_account_id.balance < self.gross_amount:
                raise UserError(_("Solde espèces insuffisant."))

            # récupération des taux des droits
            share_class = self.env['efund.fund.share.class'].search([
                ('vehicule_fund_id', '=', rec.fund_id.id),
                ('is_default', '=', True)
            ])
            entry_load = share_class.entry_load
            nav = self.env['efund.service'].get_last_nav_value(rec.fund_id)



            if rec.buy_choice == 'amount':
                result = self.calculate_shares(
                    nav,
                    rec.allow_fractional_parts,
                    rec.gross_amount,
                    entry_load,
                    rec.is_subscription_fee
                )
            else:
                result = self.calculate_amount(
                    nav,
                    rec.allow_fractional_parts,
                    rec.shares,
                    entry_load
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
            })

            rec.message_post(
                body=_("Comptabilisation de la souscription. Lancement de la réconciliation..."),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )
            # 1- Débit du compte investisseur pour le montant investi
            investor_cash_move = self.env['efund.investor.cash_account.move'].create({
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'subscription',
                'amount': gross_amount,
                'label': f"Souscription N°{rec.name} du fond {rec.fund_id.name} ",
                'date': rec.date_operation,
                'value_date': rec.date_operation,
                'state': 'reconciled',
            })
            rec.message_post(
                body=_("Débit du compte investisseur au montant de %s pour la souscription") % (rec.gross_amount),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )
            # 3- Crédit du compte du fond pour le montant investi
            fund_cash = self.env['efund.vehicule.cash'].search([
                ('vehicule_id', '=', rec.fund_id.vehicule_id.id)
            ], limit=1)
            if not fund_cash:
                fund_cash = self.env['efund.vehicule.cash'].create({
                    'name': f"Trésorerie - {rec.fund_id.vehicule_id.name}",
                    'vehicule_id': rec.fund_id.vehicule_id.id,
                    'company_id': rec.fund_id.vehicule_id.company_id.id,
                })

            fund_move = self.env['efund.vehicule.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                'vehicule_cash_id': fund_cash.id,
                'amount': rec.net_amount,
                'move_type': 'subscription_in',
                'liquidity_type': 'liquid',
                'state': 'reconciled',
                'label': f"Souscription N°{rec.name} du fond {rec.fund_id.name} ",
                'date': rec.date_valeur,
                'value_date': rec.date_valeur,
                'investor_cash_move_id': investor_cash_move.id,
                'investor_id': rec.investor_id.id,
                'vehicule_id': rec.fund_id.vehicule_id.id,
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
                    'vehicule_id': rec.fund_id.vehicule_id.id,
                    'investor_cash_move_id': investor_cash_move.id,
                    'investor_id': rec.investor_id.id,
                    'subscription_id': rec.id,
                    'gross_amount': rec.gross_amount,
                    'base_amount': rec.net_amount,
                    'label': f"Souscription N°{rec.name} du fond {rec.fund_id.name} ",
                    'date': rec.date_valeur,
                    'value_date': rec.date_valeur,
                    'fee_rate': rec.entry_load,
                    'fee_amount': rec.subscription_fee_amount,
                })
                rec.message_post(
                    body=_("Crédit du compte des frais au montant de %s francs") % (rec.subscription_fee_amount),
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
                'state': 'reconciled',
                'label': f"Souscription N°{rec.name} du fond {rec.fund_id.name} ",
                'date': rec.date_operation,
                'value_date': rec.date_valeur,
                'subscription_id': rec.id,
                'fund_id': rec.fund_id.id,
            })
            rec.message_post(
                body=_("Crédit du compte titre de l'investisseur au montant de %s part(s).") % (rec.shares),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # 5- Retour du reliquat après souscription
            if rec.amount_remaining > 0:
                # Enregistrement des frais de souscription
                self.env['efund.investor.cash_account.move'].create({
                    'cash_account_id': rec.cash_account_id.id,
                    'move_type': 'refund',
                    'amount': rec.amount_remaining,
                    'subscription_id': rec.id,
                    'state': 'reconciled',
                    'date': rec.date_valeur,
                    'value_date': rec.date_valeur,
                })
                rec.message_post(
                    body=_("Crédit du compte investisseur du réliquat de la souscription au montant de %s francs") % (
                        rec.amount_remaining),
                    subject="comptabilisation de la souscription",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )
            # Créer de l'évènement et comptabilisation
            serviceEngine = self.env['efund.service']
            payload = {
            'gross': rec.gross_amount,
            'net': rec.net_amount + rec.subscription_fee_amount,
            'capital_init': rec.amount_capital,
            'non_distribuable': rec.amount_non_distribuable,
            'res_anterieurs': rec.amount_res_anterieurs,
            'res_clos': rec.amount_res_clos,
            'res_en_cours': rec.amount_income_current,
            'entry_load': rec.subscription_fee_amount,
            'quantity': rec.shares,
            }
            event = self.env['efund.accounting.event'].create(
                serviceEngine.build_event_payload('SUB_VALIDATED', rec.vehicule_id.id, 'Souscription - ' + rec.name,
                                                  rec.date_operation, payload))
            rec.event_id = event.id
            self.env['efund.accounting.engine'].process_event(event)

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
                result = rec.calculate_shares(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.gross_amount,
                    rec.entry_load,
                    rec.is_subscription_fee
                )
            else:
                result = rec.calculate_amount(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.shares,
                    rec.entry_load,
                    rec.is_subscription_fee
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
                result = rec.calculate_shares(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.gross_amount,
                    rec.entry_load,
                    rec.is_subscription_fee
                )
            else:
                result = rec.calculate_amount(
                    rec.nav,
                    rec.allow_fractional_parts,
                    rec.shares,
                    rec.entry_load,
                    rec.is_subscription_fee
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

    def write(self, vals):
        for record in self:
            if record.state == 'reconciled':
                raise UserError("Vous ne pouvez pas modifier une opération cash déjà comptabilisée.")
        return super(FundSubscription, self).write(vals)
