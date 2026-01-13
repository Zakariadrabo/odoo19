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
        ('brokerage', 'Commission de courtage'),
        ('tob', 'Taxe sur les Oérations de Bourse'),
    ], string='Type de frais')

    rate = fields.Float(string="Taux de frais (%)")
    is_mandatory = fields.Boolean(default=True, string="Obligatoire")
