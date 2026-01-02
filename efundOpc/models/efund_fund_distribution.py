from odoo import models, fields, api
from odoo.exceptions import UserError,ValidationError

class FundDistribution(models.Model):
    _name = "efund.fund.distribution"
    _description = "Fund Distribution"
    _inherits = {'efund.fund.operation': 'operation_id'}

    operation_id = fields.Many2one('efund.fund.operation', required=True, ondelete='cascade', index=True)
    amount_per_part = fields.Float(string='Amount per Part')
    distribution_date = fields.Date(string='Distribution Date')
    total_amount = fields.Float(string='Total Amount')
    payment_mode = fields.Selection([('bank','Bank Transfer'),('reinvest','Reinvestment')], string='Payment Mode')

    @api.model
    def create(self, vals):
        if 'operation_id' not in vals:
            op_vals = {
                'operation_type': 'distribution',
                'investor_id': vals.get('investor_id'),
                'fund_id': vals.get('fund_id'),
                'date_operation': vals.get('distribution_date') or vals.get('date_operation'),
                'nb_parts': vals.get('nb_parts'),
                'vl': vals.get('vl'),
                'amount': vals.get('total_amount') or vals.get('amount'),
                'company_id': vals.get('company_id'),
            }
            op = self.env['fund.operation'].create(op_vals)
            vals['operation_id'] = op.id
        return super(FundDistribution, self).create(vals)
