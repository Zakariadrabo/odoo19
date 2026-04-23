import calendar
import logging
from datetime import datetime

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class EfundBourseOrderExecutionWizard(models.TransientModel):
    _name = 'efund.bourse.order.execution.wizard'
    _description = 'Execution of Bourse Order'


    order_id = fields.Many2one('efund.investment.order', string="Ordre de bourse", required=True, readonly=True)
    operation_type = fields.Selection(related='order_id.operation_type', default='buy', string="Type d'opération")
    instrument_type = fields.Selection(related='order_id.instrument_id.instrument_type', string="Type d'instrument")
    currency_id = fields.Many2one(related='order_id.instrument_id.currency_id', string="Devise")
    executed_quantity = fields.Float(string="Quantité exécutée", required=True)
    execution_price = fields.Float(string="Cours d'exécution", required=True)

    execution_date = fields.Date(string="Date d'exécution", required=True)
    remaining_quantity = fields.Float(string="Quantité restante", readonly=True)
    reference = fields.Char(string="Référence SGI / Marché")
    direction = fields.Selection([('buy', 'Achat'), ('sell', 'Vente')], string="Sens",default="buy" )


    formulas_accured_interest = fields.Text(string='Formules Interet Couru',compute='_compute_accrured_interest', store=True)
    free_tax_amount = fields.Float(string='Montant HT', compute='_compute_accrured_interest',store=True )

    total_courtage = fields.Monetary(string="Courtage", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_tva = fields.Monetary(string="TVA", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_bvm = fields.Monetary(string="Commission BVM", compute='_compute_accrured_interest', inverse='_inverse_nav',store=True)
    total_dc = fields.Monetary(string="Commission DC", compute='_compute_accrured_interest', inverse='_inverse_nav',store=True)
    total_regulateur = fields.Monetary(string="Régulateur", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_interet_brut = fields.Monetary(string="Intérêts brut", compute='_compute_accrured_interest',inverse='_inverse_nav', store=True)
    total_irvm = fields.Monetary(string="Taxe IRVM", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_other = fields.Monetary(string="Autres commissions", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_commission = fields.Monetary(string="Total commissions", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_transaction = fields.Monetary(string="Total Transaction", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_fees = fields.Monetary(string="Total Frais courtage", compute='_compute_accrured_interest',
                                 inverse='_inverse_nav', store=True)
    total_amount_trade = fields.Monetary(string='Total HT', store=True)

    total_interest = fields.Monetary(string="Intérêts courus net", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)
    total_amount = fields.Monetary(string="Total TTC", compute='_compute_accrured_interest', inverse='_inverse_nav', store=True)

    # les données de DAT
    deposit_amount = fields.Monetary(string="Montant à placer", )
    negotiated_rate = fields.Float(string="Taux négocié (%)")
    negotiated_rate_net = fields.Float(string="Taux négocié net (%)", compute='_compute_negotiated_rate_net', store=True)
    interest_type = fields.Selection([('postpaid', 'Postcompté'), ('prepaid', 'Précompté')], default='postpaid', string="Type d'intérêt")
    maturity_date = fields.Date(string="Échéance prévue")
    start_date = fields.Date(string="Date de début")

    # les données de opcvm
    amount_type = fields.Selection([('amount', 'Montant'), ('unit', 'Nombre de parts')], string='Type', default='amount')
    order_amount = fields.Monetary(string="Montant brut souhaité", store=True)
    nav = fields.Float(string="VL", compute='_compute_nav', inverse='_inverse_nav', store=True, readonly=False,digits=(16, 6))
    nav_date_expected = fields.Date(string="Date de VL cible", help="Date de la VL qui sera appliquée")
    units_estimated = fields.Float(string="Parts estimées", store=True)
    direction_opcvm = fields.Selection([('subscription', 'Souscription'), ('redemption', 'Rachat')], string="Sens")

    # BON
    nominal_bta = fields.Monetary(string="Montant nominal BTA", readonly=True, store=True)
    calculation_type = fields.Selection([('rate', 'Taux'), ('amount', 'Prix')], string="Mode de saisie", default='rate',
                                        required=True)
    yield_rate = fields.Float(string="Taux de rendement (%)", digits=(12, 6))
    discount_amount = fields.Monetary(string="Montant de l'escompte")
    purchase_price = fields.Monetary(string="Prix d'acquisition / Net", help="Prix après escompte")


    # ----------------------------------------------------
    # Contraintes
    # ----------------------------------------------------
    @api.onchange('yield_rate', 'execution_date', 'calculation_type','executed_quantity')
    def _onchange_calculate_by_rate(self):
        """ Calcule le montant si on saisit le taux """
        for rec in self:
            if rec.calculation_type == 'rate' and rec.yield_rate:
                tcn = self.env['efund.vehicule.instrument.core.treasury'].search(
                    [('instrument_id', '=', rec.order_id.instrument_id.id), ], limit=1)
                if tcn:
                    duration = (tcn.maturity_date - rec.execution_date).days
                    if duration > 0:
                        # Formule escompte simple : Intérêt = (Nominal * Taux * Durée) / (Base * 100)
                        base = int(tcn.day_count_convention)
                        rec.discount_amount = (tcn.face_value * rec.yield_rate * duration) / (base * 100)
                        rec.purchase_price = tcn.face_value - rec.discount_amount
                        #rec.total_amount = tcn.face_value * rec.executed_quantity
                        rec.total_amount_trade = tcn.face_value * rec.executed_quantity
                        rec.total_interest =rec.discount_amount *  rec.executed_quantity

    @api.onchange('purchase_price', 'execution_date', 'calculation_type','executed_quantity')
    def _onchange_calculate_by_price(self):
        """ Calcule le taux si on saisit le prix d'achat """
        for rec in self:
            if rec.calculation_type == 'amount' and rec.yield_rate:
                tcn = self.env['efund.vehicule.instrument.core.treasury'].search(
                    [('instrument_id', '=', rec.order_id.instrument_id.id), ], limit=1)
                if tcn:
                    duration = (tcn.maturity_date - rec.execution_date).days
                    if duration > 0 and tcn.face_value > 0:
                        rec.discount_amount = tcn.face_value - rec.purchase_price
                        base = int(tcn.day_count_convention)
                        # Taux = (Escompte * Base * 100) / (Nominal * Durée)
                        rec.yield_rate = (rec.discount_amount * base * 100) / (tcn.face_value * duration)
                        rec.purchase_price = tcn.face_value - rec.discount_amount
                        #rec.total_amount = tcn.face_value * rec.executed_quantity
                        rec.total_amount_trade = tcn.face_value * rec.executed_quantity
                        rec.total_interest = rec.discount_amount * rec.executed_quantity



    @api.onchange('amount_type', 'order_amount', 'units_estimated', 'nav')
    def _onchange_order_calculations(self):
        for rec in self:
            if not rec.nav or rec.nav <= 0:
                return

            if rec.amount_type == 'amount':
                # Si on saisit le montant, on calcule les parts
                rec.units_estimated = rec.order_amount / rec.nav
                rec.total_amount = round(rec.units_estimated * rec.nav)
                rec.total_amount_trade = round(rec.units_estimated * rec.nav)
                rec.executed_quantity = rec.units_estimated
                rec.execution_price = rec.nav
            elif rec.amount_type == 'unit':
                # Si on saisit les parts, on calcule le montant
                rec.order_amount = rec.units_estimated * rec.nav
                rec.total_amount = round(rec.units_estimated * rec.nav)
                rec.total_amount_trade = round(rec.units_estimated * rec.nav)
                rec.execution_price = rec.nav
                rec.executed_quantity = rec.units_estimated

    @api.depends('negotiated_rate')
    def _compute_negotiated_rate_net(self):
        for rec in self:
            rec.negotiated_rate_net = rec.negotiated_rate * (1 - rec.order_id.instrument_id.tax_rate / 100)
            _logger.info(f"************* instrument : {rec.order_id.instrument_id.name} taux taxe {rec.order_id.instrument_id.tax_rate}, taux dat : {rec.negotiated_rate}")

    @api.onchange('executed_quantity')
    def _check_executed_quantity(self):
        if self.remaining_quantity < self.executed_quantity:
            raise ValidationError(
                f"La quantité exécutée ne peut pas être supérieure à la quantité restante : {self.remaining_quantity} titres disponibles")




    @api.depends('execution_date','execution_price','executed_quantity','order_id.order_date', 'order_id.limit_price', 'order_id.quantity', 'order_id.deposit_amount', 'order_id.negotiated_rate', 'order_id.interest_type',
                 'order_id.maturity_date', 'order_id.start_date', 'order_id.order_amount', 'order_id.nav', 'order_id.direction','deposit_amount', 'negotiated_rate', 'interest_type', 'order_id.units_estimated','yield_rate')
    def _compute_accrured_interest(self):
        for rec in self:
            tx_courtage = 0
            tx_tva = 0
            tx_regulateur = 0
            tx_bvm = 0
            tx_dc = 0
            tx_irvm = 0
            tx_other = 0

            if rec.order_id.operation_type == 'trade':

                result = self.env['efund.vehicule.instrument.fee.rule'].search([
                    ('instrument_id', '=', rec.order_id.instrument_id.id),
                ])

                if result:
                    for res in result:
                        if res.fee_category == 'courtage':
                            tx_courtage = res.rate
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
                if rec.order_id.instrument_id.instrument_type == 'tcn':
                    tcn = self.env['efund.vehicule.instrument.core.treasury'].search(
                        [('instrument_id', '=', rec.order_id.instrument_id.id), ], limit=1)
                    rec.total_amount_trade = tcn.face_value * rec.executed_quantity
                    if tcn:
                        if tx_courtage > 0:
                            rec.total_courtage = round((rec.executed_quantity * tcn.face_value * tx_courtage) / 100, )
                        if tx_tva > 0 and tx_courtage > 0:
                            rec.total_tva = round((rec.total_courtage * tx_tva) / 100)

                    rec.total_fees = rec.total_courtage + rec.total_tva
                    rec.total_commission = rec.total_courtage + rec.total_tva
                    rec.total_amount = rec.total_amount_trade + rec.total_fees - rec.total_interest if rec.direction == 'buy' else rec.total_amount_trade + rec.total_fees - rec.total_interest

                if rec.order_id.instrument_id.instrument_type == 'bond':
                    bond = self.env['efund.vehicule.instrument.core.bond'].search(
                        [('instrument_id', '=', rec.order_id.instrument_id.id), ])
                    if bond:
                        last_coupon = self.order_id._get_actual_last_coupon_date(bond.coupon_frequency, bond.value_date,
                                                                        rec.execution_date)

                        res = self.order_id.compute_accrued_interest_precise(bond.face_value, bond.coupon_rate, last_coupon,
                                                                    rec.execution_date, bond.coupon_frequency, 'act/act',
                                                                    tx_irvm if tx_irvm > 0 else 0)
                        nbjours = res.get("days")
                        cc_brut = res.get("interest_gross")
                        cc_net = res.get("interest_net")

                        if tx_courtage > 0:
                            rec.total_courtage = round((rec.executed_quantity * bond.face_value * tx_courtage) / 100, )
                        # la TVA se calcul sur la commission de courtage seulement
                        if tx_tva > 0 and tx_courtage > 0:
                            rec.total_tva = round((rec.total_courtage * tx_tva) / 100)

                        if tx_irvm > 0:
                            rec.total_irvm = round((cc_brut * rec.executed_quantity) - (cc_net * rec.executed_quantity))

                        total_transaction = round((rec.executed_quantity * rec.execution_price) + (cc_net * rec.executed_quantity))
                        if tx_bvm > 0 and tx_courtage > 0:
                            rec.total_bvm = round((total_transaction * tx_bvm) / 100)
                        if tx_dc > 0 and tx_courtage > 0:
                            rec.total_dc = round((total_transaction * tx_dc) / 100)
                        if tx_regulateur > 0 and tx_courtage > 0:
                            rec.total_regulateur = round((rec.total_bvm * tx_regulateur) / 100)
                        if tx_other > 0 and tx_courtage > 0:
                            rec.total_other = (total_transaction * tx_other) / 100

                        # calcul des gros montant
                        rec.total_interet_brut = round(cc_brut * rec.executed_quantity)
                        rec.total_interest = round(cc_net * rec.executed_quantity)
                        rec.total_transaction = rec.executed_quantity * rec.execution_price
                        rec.total_commission = rec.total_tva + rec.total_courtage
                        rec.free_tax_amount = rec.total_bvm + rec.total_regulateur + rec.total_dc + rec.total_commission
                        rec.total_fees = rec.total_bvm + rec.total_regulateur + rec.total_dc + rec.total_commission
                        rec.total_amount = (total_transaction + rec.total_fees if rec.order_id.direction == 'buy' else total_transaction - rec.total_fees)

                        self.maturity_date = bond.maturity_date
                        self.negotiated_rate = bond.rate_net

                if rec.order_id.instrument_id.instrument_type == 'equity':
                    rec.total_transaction = rec.executed_quantity * rec.execution_price
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
                    rec.total_amount = rec.total_transaction + rec.total_fees if rec.order_id.direction == 'buy' else rec.total_transaction - rec.total_fees

            if rec.order_id.operation_type == 'deposit':
                deposit = self.env['efund.vehicule.instrument.core.dat'].search(
                    [('instrument_id', '=', rec.order_id.instrument_id.id)], limit=1)
                if deposit:
                    result = self.env["efund.service"].get_interest_valuation_json(rec.deposit_amount,
                                                                                   rec.negotiated_rate,
                                                                                   deposit.tax_rate, rec.start_date,
                                                                                   rec.maturity_date,
                                                                                   rec.execution_date,
                                                                                   deposit.interest_calculation_type,
                                                                                   rec.interest_type)

                    rec.total_interet_brut = result.get('interet_brut')
                    rec.total_interest = result.get('interet_total_net')
                    rec.total_irvm = rec.total_interet_brut - rec.total_interest
                    rec.total_amount_trade = rec.deposit_amount
                    rec.total_amount = rec.deposit_amount + rec.total_interest if rec.interest_type == 'postpaid' else rec.deposit_amount - rec.total_interest

            if rec.order_id.operation_type == 'opcvm':
                rec.total_amount_trade = rec.executed_quantity * rec.execution_price
                rec.total_amount = rec.total_amount_trade
                rec.total_interest = 0
                rec.total_irvm  = 0
                rec.total_interet_brut = 0

    @api.constrains('executed_quantity')
    def _check_executed_quantity_depend(self):
        for rec in self:
            if rec.executed_quantity > rec.remaining_quantity:
                raise ValidationError(
                    _("la quantité exécutée ne peut pas être supérieure à la quantité restante."))

    def _inverse_nav(self):
        """ Cette méthode est vide mais nécessaire pour autoriser la saisie manuelle sur un champ compute """
        pass
    # ----------------------------------------------------
    # VALIDATION
    # ----------------------------------------------------
    def action_confirm_execution(self):
        self.ensure_one()

        if self.order_id.instrument_id.instrument_type == 'bond':
            if self.order_id.state not in ('sent', 'partially_executed'):
                raise UserError(_("L’ordre ne peut plus être exécuté."))

            if self.executed_quantity <= 0 or self.execution_price <= 0:
                raise ValidationError(_("Quantité et prix doivent être positifs."))

            if self.executed_quantity > self.remaining_quantity:
                raise ValidationError(_("Quantité exécutée supérieure au solde restant."))


        self.order_id.message_post(
                body=_("L'ordre N° : %s vient d'être exécuté avec une quantité de %s au prix de %s francs") % (
                    self.order_id.name, self.executed_quantity, self.execution_price ),
                subject="Exécution de l'ordre",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

        # 1️⃣ Créer ligne d’exécution
        res = self.order_id.get_settlement_details(self.execution_date,0 if self.order_id.instrument_id.instrument_type in ('dat','opcvm') or self.order_id.instrument_id.settlement_mode !='direct' else 3)

        if self.instrument_type == 'tcn':
            tcn = self.env['efund.vehicule.instrument.core.treasury'].search(
                [('instrument_id', '=', self.order_id.instrument_id.id), ], limit=1)
            self.negotiated_rate = False
            self.interest_type = 'prepaid'
            self.execution_price = self.purchase_price
            self.maturity_date = tcn.maturity_date
            self.negotiated_rate_net = self.yield_rate

        sens = 'in'
        if self.instrument_type == 'opcvm':
            sens = 'in' if self.direction_opcvm == 'subscription' else 'out'
        if self.instrument_type in ('tcn','bond'):
            sens = 'in' if self.direction == 'buy' else 'out'


        exec_line = self.env['efund.investment.transaction'].create({
                'order_id': self.order_id.id,
                'date_transaction': self.execution_date,
                'date_settlement': res.get('settlement_date'),
                'quantity': self.executed_quantity,
                'price_unit': self.execution_price,
                'start_date': self.start_date,
                'maturity_date': self.maturity_date,
                'negotiated_rate': self.negotiated_rate,
                'negotiated_rate_net': self.negotiated_rate_net,
                'deposit_amount': self.deposit_amount,

                'total_courtage': self.total_courtage,
                'total_tva': self.total_tva,
                'total_dc': self.total_dc,
                'total_irvm': self.total_irvm,
                'total_other': self.total_other,
                'total_bvm': self.total_bvm,
                'total_interet_brut': self.total_interet_brut,
                'total_regulateur': self.total_regulateur,
                'total_interest': self.total_interest,
                'total_transaction': self.total_amount_trade,
                'total_amount_trade': self.total_amount_trade,
                'total_fees': self.total_fees,
                'total_amount': self.total_amount,
                'total_commission': self.total_commission,
                'interest_type': self.interest_type,

                'move_type': sens,
                'label': f" Exécution de l'ordre N° {self.order_id.name} de {'Achat' if sens == 'in' else 'Vente'} de l'instrument {self.order_id.instrument_id.name} - Monstant : {self.total_amount} francs",
                'state': 'confirmed'

            })

        self.order_id.message_post(
                body=_("La transaction N° : %s vient d'être créée avec une quantité de %s au prix de %s francs") % (
                    exec_line.name, self.executed_quantity, self.execution_price) ,
                subject="Exécution de l'ordre",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

        # 2️⃣ Recalcul quantités et prix moyen
        total_qty = sum(self.order_id.execution_line_ids.mapped('quantity'))
        total_amount = sum(l.quantity * l.price_unit for l in self.order_id.execution_line_ids)
        average_execution_price = (total_amount / total_qty if total_qty else 0)

        exec_line.write({'average_execution_price': average_execution_price})



        # 3️⃣ Mise à jour statut
        self.order_id.state = ('executed'  if self.remaining_quantity == self.executed_quantity else 'partially_executed')
        self.order_id.message_post(
                body=_("Une mise à jour du statut de l'ordre vient d'être effectuée. Nouveau statut : %s.") % (
                    self.order_id.state),
                subject="Exécution de l'ordre",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

        return {'type': 'ir.actions.act_window_close'}

    @api.depends('order_id.instrument_id', 'order_id.operation_type')
    def _compute_nav(self):
        for rec in self:
            if rec.order_id.operation_type == 'opcvm' and rec.order_id.instrument_id:
                opcvm = self.env['efund.vehicule.instrument.core.opcvm'].search(
                    [('instrument_id', '=', rec.order_id.instrument_id.id)], limit=1)
                if opcvm:
                    if hasattr(opcvm, 'nav'):
                        rec.nav = opcvm.nav
                    else:
                        rec.nav = 0.0

    def _inverse_nav(self):
        """ Cette méthode est vide mais nécessaire pour autoriser la saisie manuelle sur un champ compute """
        pass
