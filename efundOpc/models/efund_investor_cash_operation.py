import logging
from email.policy import default

from odoo import models, fields, api, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class EfundInvestorCashOperation(models.Model):
    _name = 'efund.investor.cash.operation'
    _description = 'Opération de Trésorerie Investisseur'
    _inherit = ['efund.operation.base', 'efund.confirmable.mixin','mail.thread', 'mail.activity.mixin']
    _order = "date_operation desc, id desc"

    name = fields.Char(string="Référence",readonly=True, copy=False,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.cash.operation'))

    type = fields.Selection([('deposit', 'Dépôt d’espèces'),('withdraw', 'Retrait d’espèces')
    ], string="Type de mouvement", required=True, index=True)

    # Le domaine dynamique limite les comptes à ceux de l'investisseur choisi
    cash_account_id = fields.Many2one('efund.investor.cash_account', string="Compte Espèces",
                                      compute="_compute_accounts",store=True, readonly=True, precompute=True, required=True)
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)

    currency_id = fields.Many2one(related='cash_account_id.vehicule_id.currency_id', string="Devise", store=True)
    amount = fields.Monetary(string="Montant", currency_field="currency_id", required=True)
    fee_amount = fields.Monetary(string="Frais", currency_field="currency_id", store=True)
    payment_mode = fields.Selection([('bank', 'Virement Bancaire'),('cheque', 'Chèque'),
        ('cash', 'Espèces'),('mobile', 'Mobile Money')], string='Mode de règlement', default='bank', required=True)
    date_operation = fields.Datetime(string="Date opération", default=fields.Datetime.now)
    event_id = fields.Many2one('efund.accounting.event', string="Événement", readonly=True)
    investor_cash_move_id = fields.Many2one('efund.investor.cash_account.move', string="Cash Investisseur", readonly=True)

    @api.depends('investor_id','vehicule_id')
    def _compute_accounts(self):
        for rec in self:
            if rec.investor_id and rec.vehicule_id:
                # On cherche le compte espèces
                rec.cash_account_id = self.env['efund.investor.cash_account'].search([
                    ('investor_id', '=', rec.investor_id.id),
                    ('vehicule_id', '=', rec.vehicule_id.id)
                ], limit=1)


    def action_validate(self):
        for rec in self:
            if rec.type == 'withdraw' and rec.cash_account_id.balance < rec.amount:
                raise UserError(_("Le solde du compte (%s) est insuffisant.") % rec.cash_account_id.balance)


            super(EfundInvestorCashOperation, rec).action_validate()

            # ---------------------------------------------
            # Création dans le compte cash du fond et réconciliation
            # Réconciliation avec le compte casch du fond
            # ---------------------------------------------
            rec.message_post(
                body=_("Déposit comptabilisé. Lancement de la réconciliation..."),
                subject="comptabilisation du déposit",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            investor_cash_move = self.env['efund.investor.cash_account.move'].create({
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'deposit',
                'amount': rec.amount,
            })
            rec.message_post(
                body=_("Crédit du compte cash investisseur au montant de %s.") % (rec.amount),
                subject="comptabilisation du déposit",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            rec.write({
                'investor_cash_move_id': investor_cash_move.id,
                'state': 'reconciled',
            })

            # Post du résultat sur le chatter
            rec.message_post(
                body=_("Réconciliation terminée avec succès."),
                subject="Réconciliation réussie",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            event = self.env['efund.accounting.event'].create(rec.build_event_payload())
            rec.event_id = event.id
            self.env['efund.accounting.engine'].process_event(event)

            #Appel de accounting engine
            #l'idéal : def cron_process_events(self): self.env['efund.accounting.engine'].process_pending_events(limit=500)
            """
                def process_pending_events(self, limit=100):
                    events = self.env['efund.accounting.event'].search([('processed','=',False),('state','=','pending')], limit=limit)
                    for event in events:
                        try:
                            self.process_event(event)
                        except Exception as e:
                            event.state = 'failed'

            """


    def build_event_payload(self):

        self.ensure_one()

        return {
            'event_type': ('CASH_IN' if self.type == 'deposit' else 'CASH_OUT'),
            'vehicule_id': self.vehicule_id.id,
            'reference': self.name,
            'event_date': self.date_operation,
            'state': 'draft',

            'payload': {
                'gross': self.amount,
                'net': self.amount - self.fee_amount,
                'fees': self.fee_amount,
            }
        }

    def write(self, vals):
        for record in self:
            if record.state == 'reconciled':
                raise UserError("Vous ne pouvez pas modifier une opération cash déjà comptabilisée.")
        return super(EfundInvestorCashOperation, self).write(vals)
