from odoo import models, fields, api
from odoo.exceptions import UserError,ValidationError

class FundSubscription(models.Model):
    _name = "efund.fund.subscription"
    _description = "Fund Subscription"
    _inherits = {'efund.fund.operation': 'operation_id'}

    operation_id = fields.Many2one('efund.fund.operation', required=True, ondelete='cascade', index=True)
    payment_mode = fields.Selection([('bank','Bank Transfer'),('cheque','Cheque'),('cash','Cash')], string='Payment Mode')
    reference_payment = fields.Char(string='Payment Reference')
    bank_id = fields.Many2one('res.bank', string='Bank')
    is_initial = fields.Boolean(string='Initial Subscription', default=False)

    @api.model
    def create(self, vals):
        if 'operation_id' not in vals:
            op_vals = {
                'operation_type': 'subscription',
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
        return super(FundSubscription, self).create(vals)