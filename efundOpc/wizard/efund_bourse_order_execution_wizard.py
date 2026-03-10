import calendar
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class EfundBourseOrderExecutionWizard(models.TransientModel):
    _name = 'efund.bourse.order.execution.wizard'
    _description = 'Execution of Bourse Order'


    order_id = fields.Many2one('efund.investment.order', string="Ordre de bourse", required=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.instrument_id.currency_id', string="Devise")
    executed_quantity = fields.Float(string="Quantité exécutée", required=True)
    execution_price = fields.Float(string="Cours d'exécution", required=True)

    execution_date = fields.Date(string="Date d'exécution", default=fields.Date.context_today, required=True)
    remaining_quantity = fields.Float(string="Quantité restante", readonly=True)
    reference = fields.Char(string="Référence SGI / Marché")
    direction = fields.Char(string="Direction")

    total_broker_commission = fields.Monetary(string="Total commission du broker",compute='_compute_accrured_interest', store=True )
    total_tob_commission = fields.Monetary(string="Total Taxe", compute='_compute_accrured_interest',store=True)
    total_interest = fields.Monetary(string="Total intérêts courus", compute='_compute_accrured_interest',store=True )
    total_amount = fields.Monetary(string="Total montant",compute='_compute_accrured_interest',store=True )
    accrured_interest = fields.Float(string='Interet Couru',compute='_compute_accrured_interest', store=True)
    formulas_accured_interest = fields.Text(string='Formules Interet Couru',compute='_compute_accrured_interest', store=True)
    free_tax_amount = fields.Float(string='Montant HT', compute='_compute_accrured_interest',store=True )


    # ----------------------------------------------------
    # Contraintes
    # ----------------------------------------------------
    @api.onchange('executed_quantity')
    def _check_executed_quantity(self):
        if self.remaining_quantity < self.executed_quantity:
            raise ValidationError(
                f"La quantité exécutée ne peut pas être supérieure à la quantité restante : {self.remaining_quantity} titres disponibles")


    @api.onchange('execution_date','execution_price','executed_quantity')
    def _compute_accrured_interest(self):
        for rec in self:
            if rec.order_id.operation_type == 'trade':
                court_com = 0
                tob_com = 0
                result = self.env['efund.vehicule.instrument.fee.rule'].search([
                    ('instrument_id', '=', rec.order_id.instrument_id.id),
                ])
                if result:
                    for res in result:
                        if res.fee_category == 'brokerage':
                            court_com = res.rate
                        if res.fee_category == 'vat':
                            tob_com = res.rate

                if court_com:
                    rec.total_broker_commission = (rec.executed_quantity * rec.execution_price * court_com) / 100
                if tob_com:
                    rec.total_tob_commission = (rec.total_broker_commission * tob_com) / 100

                bond_id = False
                bond = self.env['efund.vehicule.instrument.core.bond'].search([('instrument_id', '=', rec.order_id.instrument_id.id), ])

                days_elapsed = (bond.next_coupon_date - rec.execution_date).days
                _logger.info(f"nombre de jour: {days_elapsed}, debut {bond.next_coupon_date}, fin {rec.execution_date}, coupon {bond.coupon_frequency}")
                rec.formulas_accured_interest = f"Interet Couru =  {rec.accrured_interest} : (Taux d'interet ({bond.coupon_rate}) * Nominale ({bond.face_value}) * Nombre de jours écoulés {days_elapsed} / 365 sinon 366 si bessextile)"
                leap_year = 366 if calendar.isleap(rec.execution_date.year) else 365
                ratio = days_elapsed / leap_year
                _logger.info(f"ratio: {ratio}")
                rec.accrured_interest = bond.coupon_rate * bond.face_value * ratio /100
                _logger.info(f"interet couru: {rec.accrured_interest}")
                rec.total_interest = rec.accrured_interest * rec.executed_quantity
                rec.free_tax_amount = rec.executed_quantity * rec.execution_price
                rec.total_amount = rec.executed_quantity * rec.execution_price + rec.total_interest + rec.total_tob_commission + rec.total_broker_commission
                #"""
                #if rec.order_id.order_sens == 'achat':
                 #   _logger.info("********************achat")

               # else:
                  #  rec.total_amount = rec.executed_quantity * rec.execution_price + rec.total_interest - rec.total_tob_commission - rec.total_broker_commission
                if rec.order_id.direction == 'buy':
                    rec.direction = 'achat'
                else:
                    rec.direction = 'vente'
            elif rec.order_id.operation_type == 'opcvm':
                rec.total_amount = rec.executed_quantity * rec.execution_price
                rec.formulas_accured_interest = ""
                rec.free_tax_amount = rec.executed_quantity * rec.execution_price
                rec.total_amount = rec.executed_quantity * rec.execution_price
                if rec.order_id.direction_opcvm == 'subscription':
                    rec.direction = 'souscription'
                else:
                    rec.direction = 'rachat'
            elif rec.order_id.operation_type == 'deposit':
                rec.total_amount = rec.executed_quantity * rec.execution_price
                rec.formulas_accured_interest = ""
                rec.free_tax_amount = rec.executed_quantity * rec.execution_price
            else:
                raise ValidationError(_("Type d'opération non pris en charge : %s") % rec.order_id.operation_type)

    @api.constrains('executed_quantity')
    def _check_executed_quantity_depend(self):
        for rec in self:
            if rec.executed_quantity > rec.remaining_quantity:
                raise ValidationError(
                    _("la quantité exécutée ne peut pas être supérieure à la quantité restante."))

    # ----------------------------------------------------
    # VALIDATION
    # ----------------------------------------------------
    def action_confirm_execution(self):
        self.ensure_one()

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
        exec_line = self.env['efund.investment.transaction'].create({
            'order_id': self.order_id.id,
            'date_transaction': self.execution_date,
            'quantity': self.executed_quantity,
            'price_unit': self.execution_price,
            #'reference': self.reference,
            'fees_amount': self.total_broker_commission,
            'taxes_amount' : self.total_tob_commission,
            'interest_amount' : self.total_interest,
            'amount_net' : self.executed_quantity * self.execution_price + self.total_interest + self.total_tob_commission + self.total_broker_commission,
            'free_tax_amount':  self.executed_quantity * self.execution_price,
            'move_type': 'out' if self.direction in ('souscription', 'achat') else 'in',
            'label': f" Exécution de l'ordre N° {self.order_id.name} de {self.direction} de l'instrument {self.order_id.instrument_id.name} - Monstant : {self.free_tax_amount} francs",
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

        """
        self.order_id.action_finalize_execution({
            'execution_date': self.execution_date,
            'quantity': self.executed_quantity,
            'price': self.execution_price,
            'reference': self.reference,
            'total_broker_commission': self.total_broker_commission,
            'total_tob_commission': self.total_tob_commission,
            'total_interest': self.total_interest,
            'total_amount': self.total_amount,
            #'free_tax_amount': self.free_tax_amount

        })
        """
        return {'type': 'ir.actions.act_window_close'}
