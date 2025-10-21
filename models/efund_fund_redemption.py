from odoo import models, fields, api
from odoo.exceptions import UserError,ValidationError

class FundRedemption(models.Model):
    _name = "efund.fund.redemption"
    _description = "Fund Redemption"
    _inherits = {'efund.fund.operation': 'operation_id'}

    operation_id = fields.Many2one('efund.fund.operation', required=True, ondelete='cascade', index=True)
    redemption_reason = fields.Selection([('partial','Partial'),('total','Total'),('arbitrage','Arbitrage Out')], string='Reason')
    payout_mode = fields.Selection([('bank','Bank Transfer'),('cheque','Cheque')], string='Payout Mode')
    payout_date = fields.Date(string='Payout Date')
    withholding_tax = fields.Float(string='Withholding Tax (%)')

    @api.model
    def create(self, vals):
        if 'operation_id' not in vals:
            op_vals = {
                'operation_type': 'redemption',
                'investor_id': vals.get('investor_id'),
                'fund_id': vals.get('fund_id'),
                'date_operation': vals.get('date_operation'),
                'nb_parts': vals.get('nb_parts'),
                'vl': vals.get('vl'),
                'amount': vals.get('amount'),
                'company_id': vals.get('company_id'),
            }
            op = self.env['fund.operation'].create(op_vals)
            vals['operation_id'] = op.id
        return super(FundRedemption, self).create(vals)