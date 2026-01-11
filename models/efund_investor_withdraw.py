import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)

class EfundInvestorWithdraw(models.Model):
    _name = 'efund.investor.withdraw'
    _description = 'Opération de retrait d’espèces dans un fond'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _order = "create_date desc"

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.withdraw'))
    cash_account_id = fields.Many2one('efund.investor.cash', required=True)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)

    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")

    amount = fields.Monetary(string="montant", currency_field="currency_id", required=True)
    payment_mode = fields.Selection([('bank', 'Bank Transfer'), ('cheque', 'Cheque'), ('cash', 'Cash')],
                                    string='Mode de paiement')
    reference_payment = fields.Char(string="Référence paiement / justificatif", )
    note = fields.Text(string="Note interne")

    # RELATION DE RECONCILIATION
    investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Cash Investisseur", readonly=True)
    fund_cash_move_id = fields.Many2one('efund.fund.cash.move', string="Cash Fonds", readonly=True)
    reconciliation_log_ids = fields.One2many('efund.operation.reconciliation.log', 'deposit_id')

    def action_validate_withdraw(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Le deposit doit être soumis avant la validation."))

            rec.write({ 'state': 'validated',})

    def action_submit_withdraw(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Le deposit doit être en brouillon avant sa soumission."))

            rec.write({ 'state': 'submitted',})

    def action_cancel_withdraw(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("La souscription ne peut plus être annulée."))

            rec.write({ 'state': 'cancelled',})

    def action_account(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("Le retrait ne peut plus être annulée."))

            rec.write({'state': 'accounted', })

            # ---------------------------------------------
            # Création dans le compte cash du fond et réconciliation
            # Réconciliation avec le compte casch du fond
            # ---------------------------------------------
            rec.message_post(
                body=_("Retrait comptabilisé. Lancement de la réconciliation..."),
                subject="comptabilisation du retrait",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            investor_cash_move = self.env['efund.investor.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.investor.cash.move'),
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'withdraw',
                'amount': rec.amount,
            })
            rec.message_post(
                body=_("Crédit du compte cash investisseur au montant de %s.") % (rec.amount),
                subject="comptabilisation du Retrait",
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

