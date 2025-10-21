from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundTransaction(models.Model):
    _name = "efund.fund.transaction"
    _description = "Transaction sur fonds"

    fund_id = fields.Many2one('res.company', domain="[('company_type','=','fonds')]", required=True, index=True)
    type = fields.Selection([('subscription','Subscription'),('redemption','Redemption'),('transfer','Transfer'),('arbitrage','Arbitrage'),('dividend','Dividend'),('fee','Fee')], required=True)
    partner_id = fields.Many2one('res.partner', string="Investor")
    date = fields.Date(required=True, index=True)
    amount = fields.Monetary(currency_field='currency_id')
    units = fields.Float()
    status = fields.Selection([('draft','Draft'),('validated','Validated'),('done','Done'),('cancelled','Cancelled')], default='draft')
    instrument_id = fields.Many2one('efund.fund.instrument')
    currency_id = fields.Many2one('res.currency')
    related_move_id = fields.Many2one('account.move', string="Accounting Move")

    def action_validate(self):
        for rec in self:
            if rec.status != 'draft':
                raise UserError(_("Only draft transactions can be validated."))
            rec.status = 'validated'
            journal = self.env['account.journal'].search([('company_id','=',rec.fund_id.id)], limit=1)
            move_vals = {
                'journal_id': journal.id if journal else False,
                'date': rec.date,
                'company_id': rec.fund_id.id,
                'line_ids': [],
            }
            move = self.env['account.move'].create(move_vals)
            rec.related_move_id = move.id

    def action_post(self):
        for rec in self:
            rec.status = 'done'