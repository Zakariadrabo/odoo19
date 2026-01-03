import logging
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)

class CashWithdraw(models.Model):
    _name = 'efund.fund.cash.withdraw'
    _description = 'Opération de retrait d’espèces dans un fond'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _order = "create_date desc"


    cash_account_id = fields.Many2one('efund.account.cash', required=True)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    amount = fields.Monetary(string="montant", currency_field="currency_id", required=True)
    payment_mode = fields.Selection([('bank', 'Bank Transfer'), ('cheque', 'Cheque'), ('cash', 'Cash')],
                                    string='Mode de paiement')
    reference_payment = fields.Char(string="Référence paiement / justificatif", )
    note = fields.Text(string="Note interne")

    def action_validate_subscription(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Le deposit doit être soumis avant la validation."))

            rec.write({ 'state': 'validated',})

    def action_submit_subscription(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Le deposit doit être en brouillon avant sa soumission."))

            rec.write({ 'state': 'submitted',})

    def action_cancel_subscription(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("La souscription ne peut plus être annulée."))

            rec.write({ 'state': 'cancelled',})

    def action_account(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("La souscription ne peut plus être annulée."))

            self.env['efund.account.cash.move'].create({
                'cash_account_id':  rec.cash_account_id.id,
                'move_type': 'withdraw',
                'amount': rec.amount,
            })

            rec.write({'state': 'accounted', })
