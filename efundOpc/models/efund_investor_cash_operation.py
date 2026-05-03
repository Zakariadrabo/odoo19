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
                                      compute="_compute_accounts",store=True, readonly=True, precompute=True,)
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
                'date': rec.date_operation,
                'value_date': rec.date_operation,
            })
            rec.message_post(
                body=_("Crédit du compte cash investisseur au montant de %s.") % (rec.amount),
                subject="comptabilisation du déposit",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

           # Création de Event
            """
            serviceEngine = self.env['efund.service']
            payload = {'gross': rec.amount, }
            event = self.env['efund.accounting.event'].create(
                serviceEngine.build_event_payload('INV_CASH_IN' if self.type == 'deposit' else 'INV_CASH_OUT', rec.vehicule_id.id, 'Apport Liquidité - ' + rec.name,
                                                  rec.date_operation, payload))
            rec.event_id = event.id
            self.env['efund.accounting.engine'].process_event(event)

            # Chagement de status après comptabilisation
            rec.write({
                'investor_cash_move_id': investor_cash_move.id,
                'state': 'reconciled',
            })
            """

            # Post du résultat sur le chatter
            rec.message_post(
                body=_("Réconciliation terminée avec succès."),
                subject="Réconciliation réussie",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

    def write(self, vals):
        for record in self:
            if record.state == 'reconciled':
                raise UserError("Vous ne pouvez pas modifier une opération cash déjà comptabilisée.")
        return super(EfundInvestorCashOperation, self).write(vals)
