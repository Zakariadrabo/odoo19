# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import datetime

class FundAmlAlert(models.Model):
    _name = "efund.aml.alert"
    _description = "AML Alert / Investigation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(
        string="Reference",
        readonly=True,
        default=lambda self: _('AML/%s') % datetime.now().strftime("%Y%m%d%H%M%S")
    )
    investor_id = fields.Many2one(
        'efund.investor',
        string="Investor",
       # required=True
    )
    fund_id = fields.Many2one(
        'res.company',
        string="Fund",
       # required=True
    )
    alert_date = fields.Date(
        string="Alert Date",
        default=fields.Date.context_today
    )
    trigger = fields.Text(
        string="Trigger Description",
        help="Reason why this alert was generated (e.g., unusual transaction pattern, high-risk jurisdiction, etc.)"
    )
    severity = fields.Selection([
        ('info', 'Info'),
        ('suspicious', 'Suspicious'),
        ('critical', 'Critical')
    ], string="Severity", default='suspicious', required=True, tracking=True)
    status = fields.Selection([
        ('new', 'New'),
        ('reviewed', 'Reviewed'),
        ('escalated', 'Escalated'),
        ('closed', 'Closed')
    ], string="Status", default='new', required=True, tracking=True)
    score = fields.Integer(string="Risk Score", help="Numeric score representing the AML risk level.")
    matched_transactions = fields.Many2many(
        'efund.fund.transaction',
        string="Matched Transactions",
        help="Transactions that triggered this alert"
    )
    assigned_to = fields.Many2one('res.users', string="Assigned To", tracking=True)
    resolution_notes = fields.Text(string="Resolution Notes")
    document_ids = fields.Many2many(
        'ir.attachment',
        string="Supporting Documents",
        help="Attach relevant documents or investigation reports"
    )
    closed_at = fields.Datetime(string="Closed On", readonly=True)
    created_at = fields.Datetime(default=fields.Datetime.now, readonly=True)
    active = fields.Boolean(default=True)

    @api.onchange('severity')
    def _onchange_severity(self):
        """Automatically adjust score based on severity."""
        if self.severity == 'info':
            self.score = 10
        elif self.severity == 'suspicious':
            self.score = 50
        elif self.severity == 'critical':
            self.score = 90

    def action_mark_reviewed(self):
        self.write({'status': 'reviewed'})

    def action_escalate(self):
        self.write({'status': 'escalated'})

    def action_close(self):
        self.write({'status': 'closed', 'closed_at': fields.Datetime.now()})
