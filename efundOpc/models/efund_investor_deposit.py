import logging
from datetime import timedelta
from email.policy import default

from odoo import models, fields, api, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)

class EfundInvestorDeposit(models.Model):
    _name = 'efund.investor.deposit'
    _description = 'Opération de dépôt d’espèces dans un fond'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _order = "create_date desc"


    cash_account_id = fields.Many2one('efund.investor.cash', required=True)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')

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


    def write(self, vals):
        # Empêcher l'écriture si verrouillé
        locked_records = self.filtered(lambda r: r.state in ('accounted','reconciled'))
        if locked_records:
            raise UserError(
                "Ce dépôt est verrouillé et ne peut pas être modifié. "
                "Déverrouillez-le d'abord."
            )
        return super().write(vals)

    def unlink(self):
        for rec in self:
            if rec.state in ('accounted','reconciled'):
                raise UserError(
                    "Un document comptabilisé ne peut pas être supprimé."
                )
        return super().unlink()


    def action_validate_deposit(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Le deposit doit être soumis avant la validation."))

            rec.write({ 'state': 'validated',})

    def action_submit_deposit(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Le deposit doit être en brouillon avant sa soumission."))

            rec.write({ 'state': 'submitted',})

    def action_cancel_deposit(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("La souscription ne peut plus être annulée."))

            rec.write({ 'state': 'cancelled',})

    def action_account(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("La souscription ne peut plus être annulée."))

            rec.write({'state': 'accounted', })

            #---------------------------------------------
            # Création dans le compte cash du fond et réconciliation
            # Réconciliation avec le compte casch du fond
            #---------------------------------------------
            rec.message_post(
                body=_("Déposit comptabilisé. Lancement de la réconciliation..."),
                subject="comptabilisation du dépositt",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            service = self.env['efund.cash.reconciliation.service']
            result =service.reconcile_investor_deposit_with_logging(deposit_data=rec, user_id=self.env.user.id)

            rec.write({
                'investor_cash_move_id': result['investor_cash_move_id'],
                'fund_cash_move_id': result['fund_cash_move_id'],
                'state': 'reconciled',
            })

            # Post du résultat sur le chatter
            rec.message_post(
                body=_(
                    "Réconciliation terminée avec succès.<br/>"
                    "• Mouvement investisseur: <a href=# data-oe-model='efund.account.cash.move' "
                    "data-oe-id='%s'>%s</a><br/>"
                    "• Mouvement fonds: <a href=# data-oe-model='efund.fund.cash.move' "
                    "data-oe-id='%s'>%s</a>"
                ) % (
                         result['investor_cash_move_id'],
                         result['investor_move_ref'],
                         result['fund_cash_move_id'],
                         result['fund_move_ref']
                     ),
                subject="Réconciliation réussie",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

