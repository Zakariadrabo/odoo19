import logging
from datetime import date
from email.policy import default

from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class EfundInstrumentFee(models.Model):
    _name = 'efund.vehicule.instrument.fee'
    _description = 'Frais liés à une transaction sur instrument'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.vehicule.instrument.fee'))
    vehicule_id = fields.Many2one('efund.vehicule', required=True)
    instrument_id = fields.Many2one('efund.vehicule.instrument.core', string="Instrument", required=True)
    trade_id = fields.Many2one('efund.investment.transaction', string="Transaction instrument")
    broker_id = fields.Many2one('efund.depositaire', string="Dépositaire du fond", store=True)

    fee_category = fields.Selection(
        [('courtage', 'Commission de courtage'), ('vat', 'TVA'),
         ('bvmac', 'Commission Bourse Valeurs Mobilières'), ('dc', 'Commission Dépositaire Central'), ('ircm', 'IRCM / IRVM'), ('regulateur', 'Commission régulateur'),
         ('other', 'Autres frais'), ],string="Catégorie de Frais", required=True)
    base_amount = fields.Monetary(string="Base de calcul")
    rate = fields.Float(string="Taux (%)")
    fee_amount = fields.Monetary(string="Montant du frais")
    currency_id = fields.Many2one(related='vehicule_id.currency_id', store=True)
    vehicule_cash_move_id = fields.Many2one('efund.vehicule.cash.move', string="Impact cash fonds", readonly=True)
    state = fields.Selection([('draft', 'Brouillon'), ('reconciled', 'Réconcilié')], string="État", default='draft')

    # journal_entry_id = fields.Many2one('account.move',string="Écriture comptable",readonly=True)
