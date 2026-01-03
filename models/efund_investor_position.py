from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FundInvestorPosition(models.Model):
    _name = 'efund.investor.position'
    _description = 'Investor Position in Fund'
    _order = 'investor_id, fund_id'

    investor_id = fields.Many2one('efund.investor',string='Investor',required=True)
    fund_id = fields.Many2one('efund.fund',string='Fund',required=True )
    share_class_id = fields.Many2one('efund.fund.class',string='Share Class',required=True)
    units = fields.Float(string='Units Held',digits=(16, 2),default=0.0)
    average_price = fields.Float(string='Average Price',digits=(16, 6))
    total_cost = fields.Float(string='Total Cost')
    current_value = fields.Float(string='Current Value', compute='_compute_current_value')
    unrealized_pnl = fields.Float(string='Unrealized P&L',compute='_compute_pnl')
    unrealized_pnl_percent = fields.Float(string='Unrealized P&L %',compute='_compute_pnl')
    as_of_date = fields.Date(string='As of Date',default=fields.Date.context_today)

    @api.depends('units', 'fund_id', 'share_class_id')
    def _compute_current_value(self):
        """Calcule la valeur courante basée sur la dernière NAV"""
        for position in self:
            # Trouve la dernière NAV pour cette classe de parts
            last_nav = self.env['fund.nav'].search([
                ('share_class_id', '=', position.share_class_id.id),
                ('status', '=', 'validated')
            ], order='nav_date desc', limit=1)

            if last_nav:
                position.current_value = position.units * last_nav.nav_per_share
            else:
                position.current_value = position.total_cost

    @api.depends('current_value', 'total_cost')
    def _compute_pnl(self):
        for position in self:
            position.unrealized_pnl = position.current_value - position.total_cost
            if position.total_cost > 0:
                position.unrealized_pnl_percent = (position.unrealized_pnl / position.total_cost) * 100
            else:
                position.unrealized_pnl_percent = 0.0