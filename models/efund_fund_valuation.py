# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime

class FundValuation(models.Model):
    _name = "efund.fund.valuation"
    _description = "Fund Valuation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"

    name = fields.Char(string="Reference", readonly=True, default="/")
    fund_id = fields.Many2one("efund.fund", string="Fund", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="fund_id.company_id", store=True, readonly=True)
    valuation_date = fields.Date(string="Valuation Date", required=True, default=fields.Date.context_today)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('validated', 'Validated'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', tracking=True)

    valuation_type = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string="Valuation Frequency", default="daily")

    # Global NAV metrics
    total_assets = fields.Monetary(string="Total Assets", currency_field='currency_id')
    total_liabilities = fields.Monetary(string="Total Liabilities", currency_field='currency_id')
    net_assets = fields.Monetary(string="Net Assets", currency_field='currency_id', compute="_compute_net_assets", store=True)
    nav_per_share = fields.Monetary(string="NAV per Share", currency_field='currency_id', compute="_compute_nav_per_share", store=True)

    total_shares = fields.Float(string="Total Outstanding Shares", required=True, default=1.0)
    currency_id = fields.Many2one(related='fund_id.currency_id', store=True, readonly=True)

    valuation_line_ids = fields.One2many("efund.fund.valuation.line", "valuation_id", string="Valuation Lines")
    fee_line_ids = fields.One2many("efund.fund.valuation.fee", "valuation_id", string="Fees")
    log_ids = fields.One2many("efund.fund.valuation.log", "valuation_id", string="Valuation Logs")

    computed_by = fields.Many2one("res.users", string="Computed By")
    validated_by = fields.Many2one("res.users", string="Validated By")
    validation_date = fields.Datetime(string="Validation Date")

    notes = fields.Text(string="Comments / Observations")


    @api.depends('total_assets', 'total_liabilities')
    def _compute_net_assets(self):
        for rec in self:
            rec.net_assets = (rec.total_assets or 0) - (rec.total_liabilities or 0)

    @api.depends('net_assets', 'total_shares')
    def _compute_nav_per_share(self):
        for rec in self:
            rec.nav_per_share = rec.net_assets / rec.total_shares if rec.total_shares else 0.0

    def action_compute(self):
        """ Compute valuation from portfolio positions """
        for rec in self:
            rec.write({'state': 'in_progress', 'computed_by': self.env.user.id})
            total_assets, total_liabilities = 0.0, 0.0
            for line in rec.valuation_line_ids:
                total_assets += line.market_value
            for fee in rec.fee_line_ids:
                total_liabilities += fee.amount
            rec.total_assets = total_assets
            rec.total_liabilities = total_liabilities
            rec._compute_net_assets()
            rec._compute_nav_per_share()

    def action_validate(self):
        """ Validate valuation and lock NAV """
        for rec in self:
            if rec.state == 'validated':
                continue
            rec.write({
                'state': 'validated',
                'validated_by': self.env.user.id,
                'validation_date': fields.Datetime.now()
            })

    def action_cancel(self):
        self.write({'state': 'cancelled'})
