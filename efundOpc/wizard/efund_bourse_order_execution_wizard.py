import calendar
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

class EfundBourseOrderExecutionWizard(models.TransientModel):
    _name = 'efund.bourse.order.execution.wizard'
    _description = 'Execution of Bourse Order'

    order_id = fields.Many2one('efund.bourse.order', string="Ordre de bourse", required=True, readonly=True)
    currency_id = fields.Many2one(related='order_id.instrument_id.currency_id', string="Devise")
    executed_quantity = fields.Float(string="Quantité exécutée", required=True)
    execution_price = fields.Float(string="Cours d'exécution", required=True)

    execution_date = fields.Date(string="Date d'exécution", default=fields.Date.context_today, required=True)
    remaining_quantity = fields.Float(string="Quantité restante", readonly=True)
    reference = fields.Char(string="Référence SGI / Marché")

    total_broker_commission = fields.Monetary(string="Total commission du broker", store=True)
    total_tob_commission = fields.Monetary(string="Total Taxe", store=True)
    total_interest = fields.Monetary(string="Total intérêts courus",  store=True)
    total_amount = fields.Monetary(string="Total montant", store=True)
    accrured_interest = fields.Float(string='Interet Couru',compute='_compute_accrured_interest',)
    formulas_accured_interest = fields.Text(string='Formules Interet Couru', store=True)
    free_tax_amount = fields.Float(string='Montant HT',  store=True)


    # ----------------------------------------------------
    # Contraintes
    # ----------------------------------------------------
    @api.onchange('execution_date','execution_price','executed_quantity')
    def _compute_accrured_interest(self):
        for rec in self:
            court_com = 0
            tob_com = 0
            result = self.env['efund.fund.instrument.fee'].search([
                ('instrument_id', '=', rec.order_id.instrument_id.id),
            ])
            if result:
                for res in result:
                    if res.fee_type == 'brokerage':
                        court_com = res.rate
                    if res.fee_type == 'tob':
                        tob_com = res.rate

            if court_com:
                rec.total_broker_commission = (rec.executed_quantity * rec.execution_price * court_com) / 100
            if tob_com:
                rec.total_tob_commission = (rec.total_broker_commission * tob_com) / 100

            if rec.order_id.instrument_id.accrued_interest:
                rec.test_value = rec.order_id.instrument_id.accrued_interest

            days_elapsed = (rec.order_id.instrument_id.next_coupon_date - rec.execution_date).days
            rec.formulas_accured_interest = f"Interet Couru =  {rec.accrured_interest} : (Taux d'interet ({rec.order_id.instrument_id.coupon_rate}) * Nominale ({rec.order_id.instrument_id.face_value}) * Nombre de jours écoulés {days_elapsed} / 365 sinon 366 si bessextile)"
            leap_year = 366 if calendar.isleap(rec.execution_date.year) else 365
            ratio = days_elapsed / leap_year
            rec.accrured_interest = rec.order_id.instrument_id.coupon_rate * rec.order_id.instrument_id.face_value * ratio /100
            rec.total_interest = rec.accrured_interest * rec.executed_quantity
            rec.free_tax_amount = rec.executed_quantity * rec.execution_price
            rec.total_amount = rec.executed_quantity * rec.execution_price + rec.total_interest + rec.total_tob_commission + rec.total_broker_commission


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
        self.order_id.action_finalize_execution({
            'execution_date': self.execution_date,
            'quantity': self.executed_quantity,
            'price': self.execution_price,
            'reference': self.reference,
            'total_broker_commission': self.total_broker_commission,
            'total_tob_commission': self.total_tob_commission,
            'total_interest': self.total_interest,
            'total_amount': self.total_amount,
            'free_tax_amount': self.free_tax_amount

        })
        return {'type': 'ir.actions.act_window_close'}
