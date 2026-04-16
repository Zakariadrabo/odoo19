import logging
from datetime import timedelta, date
from email.policy import default

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)


class EfundInvestmentOrder(models.Model):
    _name = 'efund.investment.order'
    _description = "Ordre d'Investissement"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investment.order'))

    # Liens vers le portefeuille et l'instrument
    vehicule_id = fields.Many2one('efund.vehicule', string="Fonds / Mandat", required=True,
                                  ondelete='restrict')  # Référence à votre modèle de base
    instrument_id = fields.Many2one('efund.vehicule.instrument.core', string="Instrument", required=True)
    instrument_type = fields.Selection(related='instrument_id.instrument_type', store=True, string="Type d'instrument")

    currency_id = fields.Many2one(related='instrument_id.currency_id', store=True)
    operation_type = fields.Selection(
        [('trade', 'Transaction de marché'), ('opcvm', 'OPCVM'), ('deposit', 'Placement bancaire'),
        ], string="Type d'opération", required=True, tracking=True)

    order_date = fields.Date(string="Date de commande", default=fields.Date.context_today)
    direction = fields.Selection([('buy', 'Achat'), ('sell', 'Vente')], string="Sens",default="buy" )
    state = fields.Selection([('draft', 'Brouillon'), ('validated', 'Validé'), ('sent', 'Envoyé'),
                              ('partially_executed', 'Partiellement exécuté'), ('executed', 'Exécuté'),
                              ('cancelled', 'Annuler')], default='draft', string="Statut")
    broker_tax = fields.Float(string="Commission courtier")
    rate = fields.Float(string="Taux de courtage", digits=(12, 6), store=True)

    total_courtage = fields.Monetary(string="Courtage", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_tva = fields.Monetary(string="TVA", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_bvm = fields.Monetary(string="Commission BVM", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_dc = fields.Monetary(string="Commission DC", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_regulateur = fields.Monetary(string="Régulateur", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_interet_brut = fields.Monetary(string="Intérêts brut", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_irvm = fields.Monetary(string="Taxe IRVM", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_other = fields.Monetary(string="Autres commissions", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_commission = fields.Monetary(string="Total commissions", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_transaction = fields.Monetary(string="Total Transaction", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_fees = fields.Monetary(string="Total Frais", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_interest = fields.Monetary(string="Intérêts courus net", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_amount = fields.Monetary(string="Total TTC", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)

    # les données de trade
    price_type = fields.Selection([('market', 'Au marché'), ('limit', 'Prix limité')], default='market')
    limit_price = fields.Float(string="Prix limite", digits=(16, 6))
    validity_date = fields.Date(string="Date de validité", help="Date d'expiration de l'ordre")
    quantity = fields.Float(string="Quantité", digits=(16, 6))
    total_amount_trade = fields.Monetary(compute='_compute_total_amount', string='Total HT',precompute=True, store=True)

    # les données de opcvm
    amount_type = fields.Selection([('amount', 'Montant'), ('unit', 'Nombre de parts')], string='Type',default='amount')
    order_amount = fields.Monetary(string="Montant brut souhaité", store=True)
    nav = fields.Float(string="VL", compute='_compute_nav', inverse='_inverse_nav', store=True, readonly=False,digits=(16, 6))
    nav_date_expected = fields.Date(string="Date de VL cible", help="Date de la VL qui sera appliquée")
    units_estimated = fields.Float(string="Parts estimées", store=True)
    direction_opcvm = fields.Selection([('subscription', 'Souscription'), ('redemption', 'Rachat')], string="Sens")

    # les données de DAT
    deposit_amount = fields.Monetary(string="Montant à placer",  store=True)
    negotiated_rate = fields.Float(string="Taux négocié (%)", store=True)
    interest_type = fields.Selection([('postpaid', 'Postcompté'), ('prepaid', 'Précompté')], default='postpaid', string="Type d'intérêt", store=True)
    maturity_date = fields.Date(string="Échéance prévue", store=True)
    start_date = fields.Date(string="Date de début", store=True)

    # BON
    nominal_bta = fields.Monetary(string="Montant nominal BTA", readonly=True, store=True)
    calculation_type = fields.Selection([('rate', 'Taux'), ('amount', 'Prix')], string="Mode de saisie", default='rate', required=True)
    yield_rate = fields.Float(string="Taux de rendement (%)", digits=(12, 6))
    discount_amount = fields.Monetary(string="Montant de l'escompte")
    purchase_price = fields.Monetary(string="Prix d'acquisition / Net", help="Prix après escompte")


    # Suivi des exécutions
    executed_qty = fields.Float(string="Quantité exécutée", compute='_compute_execution', store=True)
    remaining_qty = fields.Float(string="Quantité restante", compute='_compute_execution', store=True)

    # Relations avec transaction
    execution_line_ids = fields.One2many('efund.investment.transaction', 'order_id', )
    broker_id = fields.Many2one('efund.depositaire', string="Société de bourse")

    @api.onchange('yield_rate',  'order_date', 'calculation_type')
    def _onchange_calculate_by_rate(self):
        """ Calcule le montant si on saisit le taux """
        for rec in self:
            if rec.calculation_type == 'rate' and rec.yield_rate:
                tcn = self.env['efund.vehicule.instrument.core.treasury'].search([('instrument_id', '=', rec.instrument_id.id),], limit=1)
                if tcn:
                    duration = (tcn.maturity_date - rec.order_date).days
                    if duration > 0:
                        # Formule escompte simple : Intérêt = (Nominal * Taux * Durée) / (Base * 100)
                        base = int(tcn.day_count_convention)
                        rec.discount_amount = (tcn.face_value * rec.yield_rate * duration) / (base * 100)
                        rec.purchase_price = tcn.face_value - rec.discount_amount
                        #rec.total_amount = tcn.face_value * rec.quantity
                        rec.total_amount_trade = tcn.face_value * rec.quantity
                        rec.total_interest = rec.discount_amount* rec.quantity
                        rec.maturity_date = tcn.maturity_date


    @api.onchange('purchase_price', 'order_date', 'calculation_type')
    def _onchange_calculate_by_price(self):
        """ Calcule le taux si on saisit le prix d'achat """
        for rec in self:
            if rec.calculation_type == 'amount' and rec.yield_rate:
                tcn = self.env['efund.vehicule.instrument.core.treasury'].search([('instrument_id', '=', rec.instrument_id.id),], limit=1)
                if tcn:
                    duration = (tcn.maturity_date - rec.order_date).days
                    if duration > 0 and tcn.face_value > 0:
                        rec.discount_amount = tcn.face_value - rec.purchase_price
                        base = int(tcn.day_count_convention)
                        # Taux = (Escompte * Base * 100) / (Nominal * Durée)
                        rec.yield_rate = (rec.discount_amount * base * 100) / (tcn.face_value * duration)
                        rec.purchase_price = tcn.face_value - rec.discount_amount
                        #rec.total_amount = tcn.face_value * rec.quantity
                        rec.total_amount_trade = tcn.face_value * rec.quantity
                        rec.total_interest = rec.discount_amount * rec.quantity
                        rec.maturity_date = tcn.maturity_date
                        #rec.total_amount = tcn.face_value * rec.quantity


    @api.depends('instrument_id', 'operation_type')
    def _compute_nav(self):
        for rec in self:
            if rec.operation_type == 'opcvm' and rec.instrument_id:
                opcvm = self.env['efund.vehicule.instrument.core.opcvm'].search(
                    [('instrument_id', '=', rec.instrument_id.id)], limit=1)
                if opcvm:
                    if hasattr(opcvm, 'nav'):
                        rec.nav = opcvm.nav
                    else:
                        rec.nav = 0.0
            if rec.operation_type == 'deposit' and rec.instrument_id:
                deposit = self.env['efund.vehicule.instrument.core.dat'].search(
                    [('instrument_id', '=', rec.instrument_id.id)], limit=1)
                if deposit:
                    rec.deposit_amount = deposit.amount_deposit
                    rec.negotiated_rate = deposit.interest_rate
                    rec.interest_type = deposit.interest_type
                    rec.maturity_date = deposit.end_date
                    rec.start_date = deposit.start_date

    # Calcul DAT
    def compute_dat_settlement_daily_basis(self, nominal, annual_rate, date_start, date_end,
                                           interest_type='postpaid', tax_rate=0.0):
        """
        Calcule la mise en place du DAT sur une base de taux journalier.
        - Idéal pour les DAT < 1 an.
        - Facilite le calcul lors des renouvellements.
        """

        # 1. Calcul de la durée exacte (Ex: 90 jours, 180 jours, ou 365 jours)
        d_start = fields.Date.from_string(date_start) if isinstance(date_start, str) else date_start
        d_end = fields.Date.from_string(date_end) if isinstance(date_end, str) else date_end

        if d_start and d_end:
            # Vérifiez que ce ne sont pas des entiers
            if isinstance(d_start, date) and isinstance(d_end, date):
                duration_days = (d_end - d_start).days
            else:
                # Si c'est déjà un entier, ne faites pas .days
                duration_days = d_end - d_start
        #duration_days = (date_end - date_start).days

        # 2. Calcul du taux journalier
        # Exemple : 6% / 360 = 0,01666% par jour


        # 3. Calcul de l'intérêt brut total pour la période
        # Formule : Nominal * Taux Journalier * Nombre de jours
        if isinstance(nominal, (list, tuple)):
            nominal = nominal[0] if nominal else 0.0

            # On s'assure que tout est bien au format numérique
        nominal = float(nominal or 0.0)
        annual_rate = float(annual_rate or 0.0)
        tax_rate = float(tax_rate or 0.0)

        daily_rate = (annual_rate / 100.0) / 365

        total_interest_gross = nominal * daily_rate * duration_days

        # 4. Gestion de la retenue fiscale (IRCM)
        tax_amount = total_interest_gross * (tax_rate / 100.0)
        total_interest_net = total_interest_gross - tax_amount

        # 5. Détermination du flux de trésorerie (Cash Out)
        if interest_type == 'prepaid':
            # Précompté : Le client paie le net (Nominal - Intérêts à recevoir)
            cash_out = nominal - total_interest_net
        else:
            # Postcompté : Le client place le Nominal total
            cash_out = nominal

        return {
            'duration_days': duration_days,
            'daily_rate': daily_rate,
            'interest_gross': round(total_interest_gross, 2),
            'interest_net': round(total_interest_net, 2),
            'cash_out': round(cash_out, 2),
        }

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
                if order.instrument_id.instrument_type != 'tcn':
                    order.total_amount_trade = order.quantity * order.limit_price
            elif order.operation_type in ['subscription', 'redemption']:
                order.total_amount_trade = order.nav * order.units_estimated
                order.total_amount = order.nav * order.units_estimated
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
            elif order.operation_type == 'opcvm':
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
        if rule.allowed_zones and self.instrument_id.issuer_id.country_id not in rule.allowed_zones.mapped(
                'country_ids'):
            raise ValidationError(
                _("Incohérence : L'actif %s n'appartient pas à la zone d'investissement autorisée.") % self.self.instrument_id.name)
        # 2. Contrôle du Type d'Actif
        if rule.allowed_asset_types and self.instrument_id.asset_class_id not in rule.allowed_asset_types:
            raise ValidationError(
                _("Incohérence : Le type d'actif %s est interdit pour ce mandat. ") % self.instrument_id.asset_class_id.name)

        self.write({'state': 'confirmed'})


    def action_execute(self):
        for rec in self:
            #self.ensure_one()
            remaining_quantity = 0
            executed_quantity = 0
            price = 0
            broker = 0
            tob = 0
            interest = 0
            if rec.operation_type == 'trade':
                remaining_quantity = rec.quantity - rec.executed_qty
                executed_quantity = rec.quantity
                price = rec.limit_price
                broker = rec.total_courtage
                tob = rec.total_tva
                interest = rec.total_interest

            elif rec.operation_type == 'opcvm':
                remaining_quantity = rec.units_estimated - rec.executed_qty
                executed_quantity = rec.units_estimated
                price = rec.nav
            elif rec.operation_type == 'deposit':
                remaining_quantity = rec.units_estimated - rec.executed_qty
            else:
                raise ValidationError(_("Type inexistant"))

            return {
                'type': 'ir.actions.act_window',
                'name': 'Exécution de l’ordre',
                'res_model': 'efund.bourse.order.execution.wizard',
                'view_mode': 'form',
                'target': 'new',
                'context': {
                    'default_order_id': rec.id,
                    'default_remaining_quantity': remaining_quantity,
                    'default_executed_quantity': remaining_quantity,
                    'default_execution_date': rec.order_date,
                    'default_execution_price': price,
                    'default_total_courtage': rec.total_courtage,
                    'default_total_tva': rec.total_tva,
                    'default_total_dc': rec.total_dc,
                    'default_total_irvm': rec.total_irvm,
                    'default_total_other': rec.total_other,
                    'default_total_bvm': rec.total_bvm,
                    'default_total_interet_brut': rec.total_interet_brut,
                    'default_total_regulateur': rec.total_regulateur,
                    'default_total_interest': rec.total_interest,
                    'default_total_transaction': rec.total_amount_trade,
                    'default_total_amount_trade': rec.total_amount_trade,
                    'default_total_fees': rec.total_fees,
                    'default_total_amount': rec.total_amount,
                    'default_direction': rec.direction,
                    # DAT
                    'default_deposit_amount': rec.deposit_amount,
                    'default_negotiated_rate': rec.negotiated_rate,
                    'default_interest_type': rec.interest_type,
                    'default_start_date': rec.start_date,
                    'default_maturity_date': rec.maturity_date,
                    'default_operation_type': rec.operation_type,
                    # OPCVM
                    'default_order_amount': rec.order_amount,
                    'default_nav': rec.nav,
                    'default_amount_type': rec.amount_type,
                    'default_units_estimated': rec.units_estimated,
                    'default_nav_date_expected': rec.nav_date_expected,
                    'default_direction_opcvm': rec.direction_opcvm,
                    #Bon
                    # BON
                    'default_nominal_bta': rec.nominal_bta,
                    'default_calculation_type': rec.calculation_type,
                    'default_yield_rate': rec.yield_rate,
                    'default_discount_amount': rec.discount_amount,
                    'default_purchase_price': rec.purchase_price,
                    'default_instrument_type': rec.instrument_type
                }
            }

    def action_send(self):
        for order in self:
            if order.state != 'validated':
                continue

            # Possibilité d'envoyer l'ordre au broker

            order.state = 'sent'


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
            vehicule_cash_account = self.env['efund.vehicule.cash'].search(
                [('vehicule_id', '=', order.vehicule_id.id), ])
            position = self.env['efund.fund.position'].get_position_by_instrument(order.instrument_id.id,
                                                                                  order.vehicule.id)
            if order.operation_type == 'trade' and order.instrument_id.instrument_type == 'bond':
                if order.direction == 'sell':
                    if order.quantity > position:
                        raise ValidationError(
                            f"Vous ne pouvez pas acheter plus que ce que vous avez : {position} titres disponibles")
                else:
                    if vehicule_cash_account:
                        balance = vehicule_cash_account.get_balance_by_vehicule_id
                        if balance < self.total_amount:
                            raise ValidationError(
                                f"Attention, le compte espèce du véhicule de gestion ne couvre pas le montant total de l'ordre: {balance}")
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

    @api.depends('order_date', 'limit_price', 'quantity', 'deposit_amount', 'negotiated_rate', 'interest_type',
                 'maturity_date', 'start_date', 'order_amount', 'nav', 'direction', 'units_estimated','nav','discount_amount','yield_rate','rate')
    def _compute_accrured_interest(self):
        for rec in self:
            serviceEngine = self.env['efund.service']
            #rec.rate = 0
            tx_tva = 0
            tx_regulateur = 0
            tx_bvm = 0
            tx_dc = 0
            tx_irvm = 0
            tx_other = 0

            if rec.operation_type == 'trade':

                    result = self.env['efund.vehicule.instrument.fee.rule'].search([
                        ('instrument_id', '=', rec.instrument_id.id),
                    ])

                    if result:
                        for res in result:
                            if res.fee_category == 'courtage':
                                tx_courtage = rec.rate
                            if res.fee_category == 'vat':
                                tx_tva = res.rate
                            if res.fee_category == 'bvmac':
                                tx_bvm = res.rate
                            if res.fee_category == 'dc':
                                tx_dc = res.rate
                            if res.fee_category == 'ircm':
                                tx_irvm = res.rate
                            if res.fee_category == 'regulateur':
                                tx_regulateur = res.rate
                            if res.fee_category == 'other':
                                tx_other = res.rate

                    # Récupération du type de l'instrument
                    if rec.instrument_id.instrument_type == 'tcn':
                        tcn = self.env['efund.vehicule.instrument.core.treasury'].search([('instrument_id', '=', rec.instrument_id.id),], limit=1)
                        rec.total_amount_trade = rec.quantity * tcn.face_value
                        if tcn:
                            if rec.rate > 0:
                                rec.total_courtage = round((rec.quantity * tcn.face_value * rec.rate) / 100, )
                            if tx_tva > 0 and rec.rate > 0:
                                rec.total_tva = round((rec.total_courtage * tx_tva) / 100)


                        rec.total_interest = rec.discount_amount * rec.quantity
                        rec.total_fees = rec.total_courtage + rec.total_tva
                        rec.total_commission = rec.total_courtage + rec.total_tva
                        rec.total_amount_trade = rec.quantity * tcn.face_value
                        rec.total_amount =  rec.total_amount_trade + rec.total_fees - rec.total_interest if rec.direction == 'buy' else rec.total_amount_trade + rec.total_fees - rec.total_interest


                    if rec.instrument_id.instrument_type == 'bond':
                        bond = self.env['efund.vehicule.instrument.core.bond'].search(
                            [('instrument_id', '=', rec.instrument_id.id), ])
                        if bond:
                            res = serviceEngine.compute_accrued_interest_precise(bond.face_value, bond.coupon_rate, rec.order_date, bond.maturity_date,bond.coupon_frequency, tax_rate=tx_irvm if tx_irvm > 0 else 0, add_day=0)
                            cc_brut = res.get('interest_gross')
                            cc_net = res.get('interest_net')

                            if rec.rate > 0:
                                rec.total_courtage = round((rec.quantity * bond.face_value * rec.rate) / 100,)
                            # la TVA se calcul sur la commission de courtage seulement
                            if tx_tva > 0 and rec.rate > 0:
                                rec.total_tva = round((rec.total_courtage * tx_tva) / 100)

                            if tx_irvm > 0:
                                rec.total_irvm = round((cc_brut * rec.quantity) - (cc_net * rec.quantity))

                            total_transaction = round((rec.quantity * rec.limit_price) + (cc_net * rec.quantity))
                            if tx_bvm > 0 and rec.rate > 0:
                                rec.total_bvm = round((total_transaction * tx_bvm) / 100)
                            if tx_dc > 0 and rec.rate > 0:
                                rec.total_dc = round((total_transaction * tx_dc) / 100)
                            if tx_regulateur > 0 and rec.rate > 0:
                                rec.total_regulateur = round((rec.total_bvm * tx_regulateur) / 100)
                            if tx_other > 0 and rec.rate > 0:
                                rec.total_other = (total_transaction * tx_other) / 100

                            # calcul des gros montant
                            rec.total_interet_brut = round(cc_brut * rec.quantity)
                            rec.total_interest = round(cc_net * rec.quantity)
                            rec.total_transaction = round(total_transaction)
                            rec.total_commission = rec.total_tva + rec.total_courtage
                            rec.total_fees = rec.total_bvm + rec.total_regulateur + rec.total_dc + rec.total_commission
                            rec.total_amount = rec.total_transaction +  rec.total_fees if rec.direction == 'buy' else rec.total_transaction -  rec.total_fees

                    if rec.instrument_id.instrument_type == 'equity':
                        rec.total_transaction = rec.quantity * rec.limit_price
                        if tx_courtage > 0:
                            rec.total_courtage = (rec.total_transaction * tx_courtage) / 100
                        if tx_tva > 0 and tx_courtage > 0:
                            rec.total_tva = (rec.total_courtage * tx_tva) / 100
                        if tx_bvm > 0 and tx_courtage > 0:
                            rec.total_bvm = (rec.total_transaction * tx_bvm) / 100
                        if tx_dc > 0 and tx_courtage > 0:
                            rec.total_dc = (rec.total_transaction * tx_dc) / 100
                        if tx_regulateur > 0 and tx_courtage > 0:
                            rec.total_regulateur = (rec.total_bvm * tx_regulateur) / 100
                        if tx_other > 0 and tx_courtage > 0:
                            rec.total_other = (rec.total_transaction * tx_other) / 100

                        rec.total_commission = rec.total_courtage + rec.total_tva
                        rec.total_fees = rec.total_bvm + rec.total_regulateur + rec.total_dc + rec.total_commission
                        rec.total_amount = (rec.total_transaction +  rec.total_fees if rec.direction == 'buy' else rec.total_transaction - rec.total_fees)

            if rec.operation_type == 'deposit':
                deposit = self.env['efund.vehicule.instrument.core.dat'].search(
                    [('instrument_id', '=', rec.instrument_id.id)], limit=1)
                if deposit:
                    if rec.deposit_amount and rec.negotiated_rate and rec.start_date and rec.maturity_date and rec.interest_type:
                        res = self.compute_dat_settlement_daily_basis(nominal=rec.deposit_amount,
                                                                      annual_rate=rec.negotiated_rate,
                                                                      date_start=rec.start_date, date_end=rec.maturity_date,
                                                                      interest_type=rec.interest_type,
                                                                      tax_rate=deposit.tax_rate)
                        duration_days = res.get('duration_days')
                        daily_rate = res.get('daily_rate')
                        interest_gross = res.get('interest_gross')
                        interest_net = res.get('interest_net')
                        cash_out = res.get('cash_out')

                        # Champ BD
                        rec.total_interet_brut = interest_gross
                        rec.total_irvm = interest_gross - interest_net
                        rec.total_interest = interest_net
                        rec.total_amount = cash_out


            if rec.operation_type == 'opcvm':
                rec.total_amount_trade = rec.units_estimated * rec.nav
                rec.total_amount = rec.units_estimated * rec.nav


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
            'fees_amount': execution_vals.get('total_total_courtage'),
            'taxes_amount': execution_vals.get('total_tva'),
            'total_interest': execution_vals.get('total_interest'),
            'total_fees': execution_vals.get('total_fees'),
            'total_amount': execution_vals.get('total_amount'),
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
        total_amount = sum(l.quantity * l.price for l in self.execution_line_ids)

        self.executed_qty = total_qty
        self.average_execution_price = ( total_amount / total_qty if total_qty else 0)

        # 3️⃣ Mise à jour statut
        self.state = ('executed' if total_qty >= self.quantity  else 'partially_executed' )
        self.message_post(
            body=_("Une mise à jour du statut de l'ordre vient d'être effectuée. Nouveau statut : %s.") % (
                self.state),
            subject="Exécution de l'ordre",
            message_type="comment",
            subtype_xmlid="mail.mt_comment"
        )

        # 4️⃣ Mise à jour position du fonds
        # self._update_fund_position(exec_line)

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



    def get_settlement_details(self, purchase_date, days_to_add):
        """
        Calcule la date de dénouement et le nombre de jours calendaires.
        Purchase_date: Date d'achat (J)
        days_to_add: 3 jours ouvrés
        """
        current_date = purchase_date
        if days_to_add == 0:
            while True:
                # 1. Test Weekend (5=Samedi, 6=Dimanche)
                if current_date.weekday() >= 5:
                    current_date += timedelta(days=1)
                    continue

                # 2. Test Jours Fériés
                is_holiday = self.env['efund.public.holiday'].search_count([
                    ('holiday_date', '=', current_date),
                ])
                if is_holiday:
                    current_date += timedelta(days=1)
                    continue

                # Si on arrive ici, c'est un jour ouvré valide
                break

            # Cas standard : dénouement différé (ex: T+3)
        else:
            working_days_counted = 0
            while working_days_counted < days_to_add:
                current_date += timedelta(days=1)

                # Test Weekend
                if current_date.weekday() >= 5:
                    continue

                # Test Jours Fériés
                is_holiday = self.env['efund.public.holiday'].search_count([
                    ('holiday_date', '=', current_date),
                ])
                if is_holiday:
                    continue

                working_days_counted += 1

        settlement_date = current_date
        calendar_days = (settlement_date - purchase_date).days

        return {
            'settlement_date': settlement_date,
            'calendar_days': calendar_days
        }

    # méthode de calcul de l'intérêt
    def compute_accrued_interest_advanced(self, nominal, annual_rate, last_coupon_date, settlement_date,
                                          frequency='annual', day_count='act/365', tax_rate=0.0):
        """
        Paramètres :
        - nominal : Principal du titre
        - annual_rate : Taux annuel (ex: 7.0 pour 7%)
        - last_coupon_date : Date de la dernière jouissance
        - settlement_date : Date de dénouement (J+3 calculé)
        - frequency : 'annual', 'semi_annual', 'quarterly', 'monthly'
        - day_count : '30/360', 'act/365', 'act/360'
        - tax_rate : Taux d'imposition (ex: 5.5 pour IRCM)
        """

        # 1. Gestion de la Fréquence (Nombre de périodes par an)
        freq_map = {'annual': 1, 'semi_annual': 2, 'quarterly': 4, 'monthly': 12}
        periods = freq_map.get(frequency, 1)

        # 2. Calcul du nombre de jours selon la convention
        if day_count == '30/360':
            # Méthode ISDA 30/360
            d1, m1, y1 = last_coupon_date.day, last_coupon_date.month, last_coupon_date.year
            d2, m2, y2 = settlement_date.day, settlement_date.month, settlement_date.year

            d1 = min(d1, 30)
            if d1 > 29: d2 = min(d2, 30)

            days = (y2 - y1) * 360 + (m2 - m1) * 30 + (d2 - d1)
            year_base = 360
        else:
            # Méthode Actual (Jours réels)
            days = (settlement_date - last_coupon_date).days
            year_base = 365 if day_count == 'act/365' else 360

        # 3. Calcul de l'intérêt BRUT
        # Formule : (Nominal * Taux) * (Jours / Base)
        # Note : La fréquence est implicitement gérée par le ratio jours/base
        # ajout du nombre de jour avant le dénouement
        nbjour_denouement = self.get_settlement_details(settlement_date,0 if self.instrument_id.instrument_type in ('dat','opcvm') or self.instrument_id.settlement_mode !='direct' else 3)
        nb_days_to_add = nbjour_denouement['calendar_days']
        interest_gross = (nominal * (annual_rate / 100.0)) * ((days + nb_days_to_add) / year_base)

        # 4. Application de la fiscalité (IRVM/IRCM)
        interest_net = interest_gross * (1 - (tax_rate / 100.0))

        return {
            'days': days,
            'days_avec_denouement': days + nb_days_to_add,
            'interest_gross': round(interest_gross, 8),
            'interest_net': round(interest_net, 8),
            'settlement_date': settlement_date
        }

    def compute_accrued_interest_precise(self, nominal, annual_rate, last_coupon_date, settlement_date,
                                         frequency='annual', day_count='act/act', tax_rate=0.0):
        self.ensure_one()
        """
        Calcule l'intérêt couru avec une base dynamique (Dernier Coupon - Prochain Coupon)
        """
        # 1. Détermination du prochain coupon pour calculer la base de la période
        freq_map = {
            'annual': relativedelta(years=1),
            'semi_annual': relativedelta(months=6),
            'quarterly': relativedelta(months=3),
            'monthly': relativedelta(months=1),
        }
        nb_periods_map = {'annual': 1, 'semi_annual': 2, 'quarterly': 4, 'monthly': 12}

        delta = freq_map.get(frequency, relativedelta(years=1))
        next_coupon_date = last_coupon_date + delta
        periods_per_year = nb_periods_map.get(frequency, 1)

        # 2. Calcul des jours courus avec dénouement (J+3 ouvré)
        # Note: On part de la date de l'ordre, settlement_details nous donne la date de valeur
        days = 0 if (self.instrument_id.instrument_type in ('dat', 'opcvm') or self.instrument_id.settlement_mode == 'direct') else 3
        details = self.get_settlement_details(settlement_date, days)
        final_settlement_date = details['settlement_date']

        # Nombre de jours entre le dernier coupon et la date de valeur réelle
        days_accrued = (settlement_date - last_coupon_date).days

        # 3. Calcul de la base de la période (Le dénominateur précis)
        days_in_period = 0
        if day_count == 'act/act':
            # Nombre de jours réels dans la période de coupon actuelle
            days_in_period = (next_coupon_date - last_coupon_date).days
            # La base annuelle devient : Jours de la période * Nombre de périodes par an
            year_base = days_in_period  # * periods_per_year
        elif day_count == '30/360':
            year_base = 360
            # (Logique 30/360 simplifiée pour l'exemple)
        else:
            year_base = 365 if day_count == 'act/365' else 360

        # 4. Calcul de l'intérêt BRUT
        # Formule : Nominal * Taux Annuel * (Jours Courus / Base Dynamique)
        nbjour_denouement = self.get_settlement_details(settlement_date,0 if self.instrument_id.instrument_type in ('dat','opcvm') or self.instrument_id.settlement_mode !='direct' else 3)
        nb_days_to_add = nbjour_denouement['calendar_days']

        taux_reel = (1 - (tax_rate / 100.0)) * annual_rate
        nb_jour = days_accrued + nb_days_to_add

        interet_period = taux_reel / periods_per_year

        interest_gross = nb_jour / year_base * (annual_rate / periods_per_year) * nominal / 100

        # 5. Application de la fiscalité (IRVM/IRCM)
        interest_net = nb_jour / year_base * interet_period * nominal / 100

        return {
            'interet_period': interet_period,
            'last_coupon_date': last_coupon_date,
            'next_coupon_date': next_coupon_date,
            'settlement_date_final': final_settlement_date,
            'days_accrued': days_accrued,
            'days_in_period': days_in_period if day_count == 'act/act' else year_base,
            'interest_gross': round(interest_gross, 8),
            'interest_net': round(interest_net, 8),
        }

    def affichemoilesdetail(self, order):
        bond = self.env['efund.vehicule.instrument.core.bond'].search(
            [('instrument_id', '=', order.instrument_id.id), ])
        serviceEngine = self.env['efund.service'].search([])

        res = serviceEngine.get_coupon_period(
            order_date=order.order_date,
            maturity_date=bond.maturity_date,
            frequency=1)

        raise ValidationError(f"Date dernier coupon: {res.get('last_coupon')} - Prochain coupon:{res.get('next_coupon')} - Nombre jours courus: {res.get('days_accrued')} - Nombre jour dans la période : {res.get('days_in_period')}")


    def _get_actual_last_coupon_date(self, frequency, value_date, execution_date):
        """
        Calcule la date du dernier coupon payé AVANT la date d'exécution.
        Exemple : Jouissance 02/02/2024, Achat 03/03/2026, Fréq Annuelle.
        Résultat : 02/02/2026
        """
        initial_date = value_date
        frequency = frequency  # 'annual', 'semi_annual', etc.

        # Mapper pour relativedelta
        freq_map = {
            'annual': relativedelta(years=1),
            'semi_annual': relativedelta(months=6),
            'quarterly': relativedelta(months=3),
            'monthly': relativedelta(months=1),
        }
        delta = freq_map.get(frequency, relativedelta(years=1))

        current_coupon_date = initial_date

        # On avance tant que la prochaine date de coupon est inférieure ou égale à l'achat
        while current_coupon_date + delta <= execution_date :
            current_coupon_date += delta

        return current_coupon_date
