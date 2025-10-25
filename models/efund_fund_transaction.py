from odoo import models, fields, api, _
from odoo.exceptions import UserError,ValidationError


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

    """
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
    """

    @api.model
    def create(self, vals):
        transaction = super().create(vals)
        if transaction.state == 'confirmed':
            transaction._create_accounting_entry()
        return transaction

    def action_confirm(self):
        for transaction in self:
            if transaction.state != 'draft':
                continue
            transaction.write({'state': 'confirmed'})
            transaction._create_accounting_entry()

    def _create_accounting_entry(self):
        """Create accounting entry for the transaction"""
        self.ensure_one()

        # Get the appropriate journal based on transaction type
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.fund_id.id),
            ('type', '=', 'bank'),
        ], limit=1)

        if not journal:
            raise UserError(_('No bank journal found for fund %s') % self.fund_id.name)

        # Prepare account move lines
        move_lines = []

        if self.transaction_type == 'subscription':
            # Debit bank, credit capital
            debit_account = journal.default_account_id
            credit_account = self.fund_id.account_capital_id  # Pre-configured account

            move_lines.append((0, 0, {
                'account_id': debit_account.id,
                'debit': self.amount,
                'credit': 0,
                'name': f'Subscription from {self.investor_id.name}',
            }))

            move_lines.append((0, 0, {
                'account_id': credit_account.id,
                'debit': 0,
                'credit': self.amount,
                'name': f'Capital increase from {self.investor_id.name}',
            }))

        # Create the account move
        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.transaction_date,
            'journal_id': journal.id,
            'company_id': self.fund_id.id,
            'line_ids': move_lines,
            'ref': self.name,
        })

        move.action_post()
        self.accounting_entry_id = move.id

    @api.constrains('units', 'unit_price', 'amount')
    def _check_amounts(self):
        for transaction in self:
            if transaction.transaction_type in ['subscription', 'redemption']:
                if transaction.units <= 0:
                    raise ValidationError(_('Units must be positive for subscriptions and redemptions.'))
                if transaction.unit_price <= 0:
                    raise ValidationError(_('Unit price must be positive.'))
                expected_amount = transaction.units * transaction.unit_price
                if abs(transaction.amount - expected_amount) > 0.01:
                    raise ValidationError(_('Amount does not match units * unit price.'))