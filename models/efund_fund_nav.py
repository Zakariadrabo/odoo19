from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundNAV(models.Model):
    _name = "efund.fund.nav"
    _description = "Computed NAV for a fund"

    fund_id = fields.Many2one('res.company', domain="[('company_type','=','fonds')]", required=True)
    date = fields.Date(required=True, index=True)
    fund_currency_id = fields.Many2one('res.currency',string="Devise du fonds",required=True)
    nav_total = fields.Monetary(string="Actif net total",currency_field='fund_currency_id')
    nav_per_share = fields.Float()
    class_id = fields.Many2one('efund.fund.class')
    status = fields.Selection([('draft','Draft'),('computed','Computed'),('posted','Posted')], default='draft')
    computed_by = fields.Many2one('res.users')
    computed_at = fields.Datetime()
    accounting_move_id = fields.Many2one('account.move')

    def compute_nav(self):
        # Simplified placeholder: aggregate market_value from positions
        positions = self.env['fund.position'].search([('fund_id','=',self.fund_id.id),('valuation_date','=',self.date)])
        total = sum(positions.mapped('market_value') or [0.0])
        self.nav_total = total
        if self.class_id and self.class_id.shares_outstanding:
            self.nav_per_share = total / self.class_id.shares_outstanding
        else:
            self.nav_per_share = 0.0
        self.status = 'computed'
        self.computed_by = self.env.user
        self.computed_at = fields.Datetime.now()

    @api.model
    def compute_nav_batch(self):
        funds = self.env['res.company'].search([('company_type','=','fonds')])
        for fund in funds:
            nav = self.create({'fund_id': fund.id, 'date': fields.Date.today()})
            try:
                nav.compute_nav()
            except Exception as e:
                pass
