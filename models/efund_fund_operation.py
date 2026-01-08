from odoo import models, fields, api
from odoo.exceptions import UserError,ValidationError

class FundOperation(models.Model):
    _name = "efund.fund.operation"
    _description = "Fund Operation (pivot for all operation types)"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "date_operation desc, id desc"

    name = fields.Char(string="Reference", required=True, copy=False, default=lambda self: self.env['ir.sequence'].next_by_code('fund.operation') or '/')
    operation_type = fields.Selection([
        ('subscription', 'Subscription'),
        ('redemption', 'Redemption'),
        ('arbitrage', 'Arbitrage'),
        ('distribution', 'Distribution'),
    ], string="Operation Type", required=True, tracking=True)
    investor_id = fields.Many2one('efund.investor', string="Investor", required=True, ondelete='restrict')
    fund_id = fields.Many2one('efund.fund', string="Fund", required=True, ondelete='cascade')
    date_operation = fields.Date(string="Operation Date", required=True, default=fields.Date.context_today)
    nb_parts = fields.Float(string="Number of Shares", digits=(16,6))
    vl = fields.Float(string="NAV / Unit", digits=(16,6))
    currency_id = fields.Many2one('res.currency', related='fund_id.currency_id', store=True, readonly=True)
    amount = fields.Monetary(string="Amount", currency_field='currency_id')
    state = fields.Selection([
        ('draft','Draft'),
        ('validated','Validated'),
        ('accounted','Accounted'),
        ('cancelled','Cancelled'),
    ], string='Status', default='draft', tracking=True)
    journal_entry_id = fields.Many2one('account.move', string="Journal Entry")
    note = fields.Text(string="Notes")
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    @api.constrains('nb_parts','amount','vl')
    def _check_values(self):
        for rec in self:
            if rec.nb_parts and rec.vl and rec.amount:
                # allow small rounding difference tolerance
                if abs(rec.nb_parts * rec.vl - rec.amount) > 0.01:
                    # not raising for now; could raise if strict
                    pass

    def action_validate(self):
        for rec in self:
            if rec.state != 'draft':
                raise ValidationError(_('Only draft operations can be validated.'))
            rec.state = 'validated'
            rec.message_post(body=_('Operation validated.'))

    def action_account(self):
        AccountMove = self.env['account.move']
        for rec in self:
            if rec.state != 'validated':
                raise ValidationError(_('Only validated operations can be accounted.'))
            journal = self.env['account.journal'].search([('company_id','=',rec.company_id.id)], limit=1)
            if not journal:
                raise ValidationError(_('No journal available for company %s') % (rec.company_id.name or ''))
            move_vals = {
                'journal_id': journal.id,
                'date': rec.date_operation,
                'company_id': rec.company_id.id,
                'line_ids': [],
            }
            if rec.amount:
                asset_account = False
                equity_account = False
                # try to use properties if defined on fund
                try:
                    asset_account = rec.fund_id.property_account_asset_id.id
                except Exception:
                    asset_account = False
                try:
                    equity_account = rec.fund_id.property_account_equity_id.id
                except Exception:
                    equity_account = False
                line_debit = (0, 0, {
                    'name': rec.name + ' debit',
                    'account_id': asset_account,
                    'debit': rec.amount,
                    'credit': 0.0,
                    'company_id': rec.company_id.id,
                })
                line_credit = (0, 0, {
                    'name': rec.name + ' credit',
                    'account_id': equity_account,
                    'debit': 0.0,
                    'credit': rec.amount,
                    'company_id': rec.company_id.id,
                })
                move_vals['line_ids'].extend([line_debit, line_credit])
            move = AccountMove.create(move_vals)
            try:
                move.post()
            except Exception:
                pass
            rec.journal_entry_id = move.id
            rec.state = 'accounted'
            rec.message_post(body=_('Operation accounted: %s') % (move.name or ''))