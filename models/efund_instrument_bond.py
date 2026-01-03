
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FundBondCoupon(models.Model):
    _name = 'efund.bond.coupon'
    _description = 'Bond Coupon Payment Schedule'
    _order = 'payment_date asc'

    instrument_id = fields.Many2one('efund.fund.instrument', required=True)
    coupon_number = fields.Integer(string='Coupon #')
    payment_date = fields.Date(string='Payment Date')
    coupon_amount = fields.Monetary(string='Coupon Amount',currency_field='currency_id',compute='_compute_coupon_amount',store=True)
    currency_id = fields.Many2one(related='instrument_id.currency_id',string='Currency')
    status = fields.Selection([
        ('upcoming', 'Upcoming'),
        ('paid', 'Paid'),
        ('accrued', 'Accrued'),
        ('defaulted', 'Defaulted'),
    ], string='Status', default='upcoming')

    @api.depends('instrument_id.coupon_rate', 'instrument_id.face_value', 'instrument_id.coupon_frequency')
    def _compute_coupon_amount(self):
        """Calcule le montant de chaque coupon"""
        for coupon in self:
            if coupon.instrument_id.coupon_frequency == 'annual':
                periods = 1
            elif coupon.instrument_id.coupon_frequency == 'semi_annual':
                periods = 2
            elif coupon.instrument_id.coupon_frequency == 'quarterly':
                periods = 4
            elif coupon.instrument_id.coupon_frequency == 'monthly':
                periods = 12
            else:
                periods = 1

            annual_coupon = coupon.instrument_id.face_value * (coupon.instrument_id.coupon_rate / 100)
            coupon.coupon_amount = annual_coupon / periods