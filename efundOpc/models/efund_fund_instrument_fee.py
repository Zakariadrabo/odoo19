import logging
from datetime import date
from email.policy import default

from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

class EfundInstrumentFee(models.Model):
    _name = 'efund.fund.instrument.fee'
    _description = 'Frais liés à une transaction sur instrument'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.fund.instrument.fee'))
    #fund_id = fields.Many2one('efund.fund', required=True)
    instrument_id = fields.Many2one('efund.fund.instrument', required=True)
    transaction_type = fields.Selection([('buy', 'Achat'),('sell', 'Vente'),], string="Type transaction", required=True)
    trade_id = fields.Many2one('efund.bourse.order.execution.line',string="Transaction instrument")
    broker_id = fields.Many2one('efund.depositaire', string="Dépositaire du fond",  store=True)

    fee_category = fields.Selection([('broker_fee', 'Commission de courtage'),('market_tax', 'Taxe de marché'), ('vat', 'TVA'),
        ('other', 'Autres frais'),], required=True)
    base_amount = fields.Monetary(string="Base de calcul")
    rate = fields.Float(string="Taux (%)")
    fee_amount = fields.Monetary(string="Montant du frais")
    currency_id = fields.Many2one(related='fund_id.currency_id', store=True)
    #fund_cash_move_id = fields.Many2one('efund.fund.cash.move',string="Impact cash fonds",readonly=True)
    state = fields.Selection([('draft', 'Brouillon'),('reconciled', 'Réconcilié')], string="État", default='draft')

    #journal_entry_id = fields.Many2one('account.move',string="Écriture comptable",readonly=True)
