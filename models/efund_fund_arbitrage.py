from odoo import models, fields, api
from odoo.exceptions import UserError,ValidationError

class FundArbitrage(models.Model):
    _name = "efund.fund.arbitrage"
    _description = "Fund Arbitrage"
    _inherits = {'efund.fund.operation': 'operation_id'}

    operation_id = fields.Many2one('efund.fund.operation', required=True, ondelete='cascade', index=True)
    source_fund_id = fields.Many2one('efund.fund', string='Source Fund')
    target_fund_id = fields.Many2one('efund.fund', string='Target Fund')
    fees = fields.Float(string='Fees')
    vl_source = fields.Float(string='Source NAV', digits=(16,6))
    vl_target = fields.Float('Target NAV', digits=(16,6))

    @api.model
    def create(self, vals):
        if 'operation_id' not in vals:
            op_vals = {
                'operation_type': 'arbitrage',
                'investor_id': vals.get('investor_id'),
                'fund_id': vals.get('source_fund_id'),
                'date_operation': vals.get('date_operation'),
                'nb_parts': vals.get('nb_parts'),
                'vl': vals.get('vl_source') or vals.get('vl'),
                'amount': vals.get('amount'),
                'company_id': vals.get('company_id'),
            }
            op = self.env['fund.operation'].create(op_vals)
            vals['operation_id'] = op.id
        return super(FundArbitrage, self).create(vals)