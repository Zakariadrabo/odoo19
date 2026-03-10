import calendar
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class EfundInvestmentOrder(models.Model):
    _name = 'efund.investment.order'
    _description = "Ordre d'Investissement"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Référence", required=True, default=lambda self: self.env['ir.sequence'].next_by_code('efund.investment.order'))

    # Liens vers le portefeuille et l'instrument
    vehicule_id = fields.Many2one('efund.vehicule', string="Fonds / Mandat", required=True,
                                  ondelete='restrict')  # Référence à votre modèle de base
    instrument_id = fields.Many2one('efund.vehicule.instrument.core', string="Instrument", required=True)
    currency_id = fields.Many2one(related='instrument_id.currency_id', store=True)
    operation_type = fields.Selection([('trade', 'Transaction de marché'), ('opcvm', 'OPCVM'), ('deposit', 'Placement bancaire'),
                                       ('maturity', 'Échéance'), ], string="Type d'opération", required=True,tracking=True)

    order_date = fields.Date(string="Date de commande", default=fields.Date.context_today)
    direction = fields.Selection([('buy', 'Achat'), ('sell', 'Vente')], string="Sens", )
    state = fields.Selection([('draft', 'Brouillon'), ('validated', 'Validé'), ('sent', 'Envoyé'),
                              ('partially_executed', 'Partiellement exécuté'), ('executed', 'Exécuté'),
                              ('cancelled', 'Annuler')], default='draft', string="Statut")
    broker_tax = fields.Float(string="Commission courtier")

    total_broker_commission = fields.Monetary(string="Commission Courtage",compute='_compute_accrured_interest', store=True)
    total_tob_commission = fields.Monetary(string="Taxe",compute='_compute_accrured_interest', store=True)
    total_interest = fields.Monetary(string="Intérêts courus",compute='_compute_accrured_interest', store=True)
    total_amount = fields.Monetary(string="Total TTC",compute='_compute_accrured_interest', store=True)


    # les données de trade
    price_type = fields.Selection([('market', 'Au marché'), ('limit', 'Prix limité')], default='market')
    limit_price = fields.Float(string="Prix limite", digits=(16, 6))
    validity_date = fields.Date(string="Date de validité", help="Date d'expiration de l'ordre")
    quantity = fields.Float(string="Quantité", digits=(16, 6))
    total_amount_trade = fields.Monetary(compute='_compute_total_amount', currency_field='currency_id',string='Total HT', store=True)

    # les données de opcvm
    amount_type = fields.Selection([('amount', 'Montant'), ('unit', 'Nombre de parts')], string='Type', default='amount')
    order_amount = fields.Monetary(string="Montant brut souhaité", store=True)
    nav = fields.Float(string="VL",compute='_compute_nav', inverse='_inverse_nav',store=True, readonly=False, digits=(16, 6))
    nav_date_expected = fields.Date(string="Date de VL cible", help="Date de la VL qui sera appliquée")
    units_estimated = fields.Float(string="Parts estimées",  store=True)
    direction_opcvm = fields.Selection([('subscription', 'Souscription'), ('redemption', 'Rachat')], string="Sens")


    # les données de DAT
    deposit_amount = fields.Monetary(string="Montant à placer", )
    negotiated_rate = fields.Float(string="Taux négocié (%)")
    maturity_date = fields.Date(string="Échéance prévue")
    start_date = fields.Date(string="Date de début")

    # Suivi des exécutions
    executed_qty = fields.Float(string="Quantité exécutée", compute='_compute_execution', store=True)
    remaining_qty = fields.Float(string="Quantité restante", compute='_compute_execution', store=True)

    # Relations avec transaction
    execution_line_ids = fields.One2many('efund.investment.transaction', 'order_id',)

    @api.depends('instrument_id', 'operation_type')
    def _compute_nav(self):
        for rec in self:
            if rec.operation_type =='opcvm' and rec.instrument_id:
                opcvm = self.env['efund.vehicule.instrument.core.opcvm'].search([('instrument_id', '=', rec.instrument_id.id)], limit=1)
                if opcvm:
                    if hasattr(opcvm, 'nav'):
                        rec.nav = opcvm.nav
                    else:
                        rec.nav = 0.0

    def _inverse_nav(self):
        """ Cette méthode est vide mais nécessaire pour autoriser la saisie manuelle sur un champ compute """
        pass

    @api.onchange('amount_type', 'order_amount', 'units_estimated', 'nav')
    def _onchange_order_calculations(self):
        for rec in self:
            if not rec.nav or rec.nav <= 0:
                return

            if rec.amount_type == 'amount':
                # Si on saisit le montant, on calcule les parts
                rec.units_estimated = rec.order_amount / rec.nav
            elif rec.amount_type == 'unit':
                # Si on saisit les parts, on calcule le montant
                rec.order_amount = rec.units_estimated * rec.nav


    @api.depends('execution_line_ids.quantity')
    def _compute_execution(self):
        for order in self:
            order.executed_qty = sum(order.execution_line_ids.mapped('quantity'))

    # --- CALCUL DES DIRECTIONS ---
    @api.depends('instrument_id')
    def _compute_instrument_ids(self):
        for rec in self:
            if rec.instrument_id.instrument_type == 'equity':
                rec.operation_type = False
                rec.operation_type = 'trade'
                rec.sous_categorie = False  # Réinitialise la valeur si le type change
                return {'domain': {'sous_categorie': [('id', 'in', self._get_transaction_direction())]},
                        'selection': self._get_transaction_direction()}



    """ Calcule le montant financier théorique de l'ordre selon son type """

    @api.depends('quantity', 'limit_price', 'order_amount', 'deposit_amount', 'operation_type')
    def _compute_total_amount(self):

        for order in self:
            if order.operation_type == 'trade':
                order.total_amount_trade = order.quantity * order.limit_price
            elif order.operation_type in ['subscription', 'redemption']:
                # Le montant demandé est déjà le total pour un OPCVM
                pass
            elif order.operation_type == 'deposit':
                # Le montant du placement est le total
                pass

    # --- LOGIQUE DE VALIDATION (ACTION VALIDATE) ---
    def action_validate(self):
        """Validation avec vérification d'état"""
        for order in self:
            if order.state != 'draft':
                raise UserError(_(
                    "Seuls les ordres en brouillon peuvent être validés. "
                    "État actuel : %s"
                ) % dict(self._fields['state'].selection).get(order.state))

            # Vérifications supplémentaires
            if order.operation_type == 'trade':
                if not order.quantity > 0:
                    raise ValidationError(_("La quantité doit être positive."))
            elif order.operation_type =='opcvm':
                if not order.nav > 0:
                    raise ValidationError(_("Le nombre de part doit être positif."))
                if not order.order_amount > 0:
                    raise ValidationError(_("Le montant total doit être positif."))

            order.state = 'validated'

    def action_cancel(self):
        """Annulation avec vérification d'état"""
        for order in self:
            if order.state == 'partially_executed':
                raise UserError(_(
                    "Impossible d'annuler un ordre exécuté. "
                    "L'ordre %s a déjà été exécuté à %s%%."
                ) % (order.name, (order.executed_qty / order.quantity) * 100))

            if order.state == 'cancelled':
                continue  # Déjà annulé

            order.state = 'cancelled'


    @api.model
    def _check_mandate_compliance(self):
        self.ensure_one()

        mandate = self.env['efund.vehicule.mandate'].search([('vehicule_id', '=', self.vehicule_id.id)], limit=1)
        if not mandate:
            raise UserError(_("Le mandat n'existe pas pour ce fonds."))

        rule = mandate.rule_ids
        # 1. Contrôle de la Zone Géographique
        if rule.allowed_zones and self.instrument_id.issuer_id.country_id not in rule.allowed_zones.mapped('country_ids'):
            raise ValidationError(_( "Incohérence : L'actif %s n'appartient pas à la zone d'investissement autorisée.") % self.self.instrument_id.name)
        # 2. Contrôle du Type d'Actif
        if rule.allowed_asset_types and self.instrument_id.asset_class_id not in rule.allowed_asset_types:
            raise ValidationError(_("Incohérence : Le type d'actif %s est interdit pour ce mandat. ") % self.instrument_id.asset_class_id.name)

        self.write({'state': 'confirmed'})
        """
        # 1. Estimation pour OPCVM (VL Inconnue)
        if order.operation_type in ['subscription', 'redemption']:
            last_nav = order.instrument_id.market_price
            if last_nav > 0:
                order.units_estimated = order.order_amount / last_nav
            else:
                # On ne bloque pas forcément, mais on avertit
                order.message_post(body=_("Attention : Estimation impossible, aucune VL connue."))

        # 2. Gestion du Stourno (Extourne) pour DAT et Obligations
        if order.operation_type == 'deposit' or (
                order.operation_type == 'trade' and order.instrument_id.instrument_type == 'bond'):
            order._handle_accrued_interest_storno()

        # 3. Contrôle de Conformité (Exemple Ratio 10%)
        order._check_amf_umoa_compliance()
        
        """

    def action_execute(self):
        self.ensure_one()
        remaining_quantity = 0
        executed_quantity = 0
        price = 0
        broker = 0
        tob = 0
        interest = 0
        if self.operation_type == 'trade':
            remaining_quantity = self.quantity - self.executed_qty
            executed_quantity = self.quantity
            price = self.limit_price
            broker = self.total_broker_commission
            tob = self.total_tob_commission
            interest = self.total_interest

        elif self.operation_type == 'opcvm':
            remaining_quantity = self.units_estimated - self.executed_qty
            executed_quantity = self.units_estimated
            price = self.nav
        elif self.operation_type == 'deposit':
            remaining_quantity = self.units_estimated - self.executed_qty
        else:
            raise ValidationError(_("Type inexistant"))


        return {
            'type': 'ir.actions.act_window',
            'name': 'Exécution de l’ordre',
            'res_model': 'efund.bourse.order.execution.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_remaining_quantity': remaining_quantity,
                'default_executed_quantity': remaining_quantity,
                'default_execution_price': price,
                'default_total_broker_commission': broker,
                'default_total_tob_commission': tob,
                'default_total_interest': interest,
                'default_free_tax_amount': executed_quantity * price
            }
        }

    def action_send(self):
        for order in self:
            if order.state != 'validated':
                continue

            # Possibilité d'envoyer l'ordre au broker

            order.state = 'sent'




    def _handle_accrued_interest_storno(self):

        """ Génère l'écriture d'extourne pour éviter le double comptage des intérêts """
        self.ensure_one()
        # Logique simplifiée : on marque l'instrument pour recalcul des IC à la validation
        self.instrument_id.with_context(storno_date=self.date_order)._update_accrued_interests()
        self.message_post(body=_("Extourne des intérêts courus calculée pour la VL."))


    """
    def _check_amf_umoa_compliance(self):
         #Moteur de vérification des ratios prudentiels 
    self.ensure_one()
    nav = self.vehicule_id.total_net_assets or 1.0

    # Calcul de l'exposition théorique
    amount = self.total_amount_trade or self.order_amount or self.deposit_amount
    projected_ratio = (amount / nav) * 100

    # Règle simple : un seul titre ne doit pas dépasser 10%
    if projected_ratio > 10.0:
        if self.env.context.get('force_compliance'):
            self.message_post(body=_("Dépassement de ratio (10%) forcé par l'administrateur."))
        else:
            raise ValidationError(_(
                "Ratio Prudentiel : Cet ordre représente %.2f%% de l'actif net, "
                "dépassant la limite réglementaire de 10%%."
            ) % projected_ratio)

    """


    def action_confirm(self):
        """
        Confirme l'ordre après vérification.
        C'est l'étape charnière où l'ordre devient opposable au Middle-Office.
        """
        for order in self:
            if order.state != 'draft':
                raise UserError(_("Seul un ordre en brouillon peut être confirmé."))

            # 1. Vérification des données obligatoires selon le type
            order._validate_order_data()

            # 2. Appel du moteur de conformité (Règles 5/10/40 AMF-UMOA)
            # Cette méthode lève une ValidationError en cas de dépassement
            order._check_amf_umoa_compliance()

            # 3. Vérification de la disponibilité des titres ou cash
            vehicule_cash_account = self.env['efund.vehicule.cash'].search([('vehicule_id', '=', order.vehicule_id.id), ])
            position = self.env['efund.fund.position'].get_position_by_instrument(order.instrument_id.id, order.vehicule.id)
            if order.operation_type == 'trade' and order.instrument_id.instrument_type == 'bond':
                if order.direction == 'sell':
                    if order.quantity > position:
                        raise ValidationError(f"Vous ne pouvez pas acheter plus que ce que vous avez : {position} titres disponibles")
                else:
                    if vehicule_cash_account:
                        balance = vehicule_cash_account.get_balance_by_vehicule_id
                        if balance < self.total_amount:
                            raise ValidationError(f"Attention, le compte espèce du véhicule de gestion ne couvre pas le montant total de l'ordre: {balance}")
            elif order.operation_type == 'opcvm':

                if vehicule_cash_account:
                    balance = vehicule_cash_account.get_balance_by_vehicule_id
                    if balance < self.total_amount:
                        raise ValidationError(
                            f"Attention, le compte espèce du véhicule de gestion ne couvre pas le montant total de l'ordre: {balance}")

            elif order.operation_type == 'redemption':
                if order.quantity > position:
                    raise ValidationError(
                        f"Vous ne pouvez pas acheter plus que ce que vous avez : {position} titres disponibles")

            elif order.operation_type == 'deposit':
                if vehicule_cash_account:
                    balance = vehicule_cash_account.get_balance_by_vehicule_id
                    if balance < self.total_amount:
                        raise ValidationError(
                            f"Attention, le compte espèce du véhicule de gestion ne couvre pas le montant total de l'ordre: {balance}")
            else:
                raise ValidationError(f"Ce code d'opération n'existe pas")


            # 3. Log de l'action pour la piste d'audit
            order.message_post(body=_("Ordre confirmé et soumis au contrôle prudentiel."))

            order.write({'state': 'confirmed'})
        return True

    def get_coupon_period(self, order_date, maturity_date):
        """
        Calcule les dates de coupon entourant la commande basée sur la maturité.
        On suppose une fréquence annuelle (standard UMOA).
        """
        if not order_date or not maturity_date:
            return False

        # 1. On se place sur la date anniversaire de la maturité pour l'année de commande
        # Exemple : Maturité 15/06/2028, Commande 10/03/2026 -> On teste 15/06/2026
        current_anniversary = maturity_date.replace(year=order_date.year)

        # 2. Déterminer le Prochain et le Dernier coupon
        if current_anniversary >= order_date:
            # La date de commande est AVANT l'anniversaire de cette année
            next_coupon_date = current_anniversary
            last_coupon_date = next_coupon_date - relativedelta(years=1)
        else:
            # La date de commande est APRÈS l'anniversaire de cette année
            last_coupon_date = current_anniversary
            next_coupon_date = last_coupon_date + relativedelta(years=1)

        # 3. Calcul du nombre de jours courus (A)
        days_accrued = (order_date - last_coupon_date).days

        # 4. Calcul du nombre de jours total de la période (B) pour la base Exact/365 ou 360
        days_in_period = (next_coupon_date - last_coupon_date).days

        return {
            'last_coupon': last_coupon_date,
            'next_coupon': next_coupon_date,
            'days_accrued': days_accrued,
            'days_in_period': days_in_period
        }


    def action_cancel(self):
        """
        Annule l'ordre si aucune exécution n'a été rattachée.
        """
        for order in self:
            # Sécurité : on ne peut pas annuler un ordre déjà exécuté ou dénoué
            if order.state in ['executed', 'settled']:
                raise UserError(_("Impossible d'annuler un ordre qui a déjà été exécuté ou dénoué."))

            # Vérifier s'il y a des transactions liées
            if order.execution_line_ids:
                raise UserError(
                    _("Cet ordre possède des exécutions. Supprimez les exécutions avant d'annuler l'ordre."))

            order.write({'state': 'cancelled'})
            order.message_post(body=_("Ordre annulé par l'utilisateur."))
        return True


    def _validate_order_data(self):
        """ Vérifie que les champs critiques sont remplis selon le type d'instrument """
        self.ensure_one()
        if self.operation_type == 'trade' and not self.quantity:
            raise ValidationError(_("La quantité est obligatoire pour une transaction de marché."))

        if self.operation_type in ['subscription', 'redemption'] and not self.order_amount:
            raise ValidationError(_("Le montant est obligatoire pour un ordre OPCVM."))

        if self.operation_type == 'deposit' and (not self.deposit_amount or not self.maturity_date):
            raise ValidationError(_("Le montant et l'échéance sont obligatoires pour un DAT."))


    @api.depends('order_date', 'limit_price', 'quantity')
    def _compute_accrured_interest(self):
        for rec in self:
            court_com = 0
            tob_com = 0

            if rec.operation_type == 'trade':

                result = self.env['efund.vehicule.instrument.fee.rule'].search([
                    ('instrument_id', '=', rec.instrument_id.id),
                ])

                if result:
                    for res in result:
                        if res.fee_category == 'brokerage':
                            court_com = res.rate
                        if res.fee_category == 'vat':
                            tob_com = res.rate

                if court_com:
                    rec.total_broker_commission = (rec.quantity * rec.limit_price * court_com) / 100
                if tob_com:
                    rec.total_tob_commission = (rec.total_broker_commission * tob_com) / 100

                bond_id = False
                bond = self.env['efund.vehicule.instrument.core.bond'].search([('instrument_id', '=', rec.instrument_id.id), ])

                if bond:
                    bond_id = bond.id


                result = self.get_coupon_period(rec.order_date, bond.maturity_date)
                interest_per_unit = 0
                if result:
                    days_elapsed = result.get("days_accrued") #(bond.next_coupon_date - rec.order_date).days
                    _logger.info(f"*******************days_elapsed: {days_elapsed} debut: {rec.order_date} fin: {bond.next_coupon_date}")
                    #rec.formulas_accured_interest = f"Interet Couru =  {rec.accrured_interest} : (Taux d'interet ({bond.coupon_rate}) * Nominale ({bond.face_value}) * Nombre de jours écoulés {days_elapsed} / 365 sinon 366 si bessextile)"
                    leap_year = 366 if calendar.isleap(rec.order_date.year) else 365
                    ratio = days_elapsed / leap_year
                    _logger.info(f"*******************ratio: {ratio}")
                    interest_per_unit = bond.coupon_rate * bond.face_value * ratio / 100

                _logger.info(f"*******************interest_per_unit: {interest_per_unit}")
                rec.total_interest = interest_per_unit * rec.quantity
                rec.total_amount = rec.quantity * rec.limit_price + rec.total_interest + rec.total_tob_commission + rec.total_broker_commission
                # if rec.order_id.order_sens == 'achat':
                #   _logger.info("********************achat")

            # else:
            #  rec.total_amount = rec.executed_qty * rec.execution_price + rec.total_interest - rec.total_tob_commission - rec.total_broker_commission


    def action_finalize_execution(self, execution_vals):
        """
        Méthode centrale appelée par le wizard
        """
        self.ensure_one()


        if self.state not in ('sent', 'partially_executed'):
            raise UserError(_("L’ordre ne peut plus être exécuté."))

        qty = execution_vals.get('quantity')
        price = execution_vals.get('price')

        if qty <= 0 or price <= 0:
            raise ValidationError(_("Quantité et prix doivent être positifs."))

        remaining = self.quantity - self.executed_qty
        _logger.info(f"*******************selef.quantity: {self.quantity} execute_qty: {self.executed_qty} remaining {remaining} et quantity {qty}")
        if qty > remaining:
            raise ValidationError(_("Quantité exécutée supérieure au solde restant."))

        self.message_post(
            body=_("L'ordre N° : %s vient d'être exécuté avec une quantité de %s au prix de %s francs") % (
                self.name, qty, price),
            subject="Exécution de l'ordre",
            message_type="comment",
            subtype_xmlid="mail.mt_comment"
        )

        # 1️⃣ Créer ligne d’exécution
        exec_line = self.env['efund.investment.transaction'].create({
            'order_id': self.id,
            'vehicule_id': self.vehicule_id,
            'instrument_id': self.instrument_id,
            'date_transaction': execution_vals.get('execution_date'),
            'quantity': execution_vals.get('date_transaction'),
            'price': execution_vals.get('execution_price'),
            'reference': execution_vals.get('reference'),
            'fees_amount': execution_vals.get('total_broker_commission'),
            'taxes_amount' : execution_vals.get('total_tob_commission'),
            'total_interest' : execution_vals.get('total_interest'),
            'total_amount' : execution_vals.get('total_amount'),
            'free_tax_amount': execution_vals.get('free_tax_amount'),

        })

        self.message_post(
            body=_("La transaction N° : %s vient d'être créée avec une quantité de %s au prix de %s francs") % (
                exec_line.name, qty, price),
            subject="Exécution de l'ordre",
            message_type="comment",
            subtype_xmlid="mail.mt_comment"
        )

        # 2️⃣ Recalcul quantités et prix moyen
        total_qty = sum(self.execution_line_ids.mapped('quantity'))
        total_amount = sum(
            l.quantity * l.price for l in self.execution_line_ids
        )

        self.executed_qty = total_qty
        self.average_execution_price = (
            total_amount / total_qty if total_qty else 0
        )

        # 3️⃣ Mise à jour statut
        self.state = (
            'executed'
            if total_qty >= self.quantity
            else 'partially_executed'
        )
        self.message_post(
            body=_("Une mise à jour du statut de l'ordre vient d'être effectuée. Nouveau statut : %s.") % (
                self.state),
            subject="Exécution de l'ordre",
            message_type="comment",
            subtype_xmlid="mail.mt_comment"
        )

        # 4️⃣ Mise à jour position du fonds
        #self._update_fund_position(exec_line)

        # 5️⃣ Comptabilité (hook)
        # self._create_accounting_entry(exec_line)

        # 6️⃣ NAV à recalculer
        # self.fund_id._mark_nav_to_recompute()

    # =========================

    def _create_accounting_entry(self, execution_line):
        self.ensure_one()

        journal = self.fund_id.operations_journal_id

        debit_account = self.fund_id.investment_account_id
        credit_account = self.fund_id.cash_account_id

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': execution_line.execution_date,
            'journal_id': journal.id,
            'company_id': self.fund_id.company_id.id,
            'line_ids': [
                (0, 0, {
                    'account_id': debit_account.id,
                    'debit': execution_line.quantity * execution_line.price,
                    'credit': 0,
                    'name': self.instrument_id.name,
                }),
                (0, 0, {
                    'account_id': credit_account.id,
                    'debit': 0,
                    'credit': execution_line.quantity * execution_line.price,
                    'name': self.instrument_id.name,
                }),
            ]
        })

        move.action_post()
        execution_line.account_move_id = move.id