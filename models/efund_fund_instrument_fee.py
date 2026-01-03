import logging
from datetime import date
from email.policy import default

from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class EfundInstrumentFee(models.Model):
    _name = 'efund.fund.instrument.fee'
    _description = 'Frais d\'un instrument financier'

    instrument_id = fields.Many2one('efund.fund.instrument')

    fee_type = fields.Selection([
        ('brvm', 'Commission BRVM'),
        ('dcbc', 'Commission DC/BR'),
        ('brokerage', 'Commission de courtage'),
        ('tob', 'TOB'),
    ], string='Type de frais')
    rate = fields.Float(string="Taux de frais (%)")
    is_mandatory = fields.Boolean(default=True, string="Obligatoire")
