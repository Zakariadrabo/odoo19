from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FundAmlAlert(models.Model):
    _name = "efund.aml.alert"
    _description = "AML Alert / Investigation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    name = fields.Char(string="Reference", default=lambda self: _('Alert/%s') % fields.Date.today())
    investor_id = fields.Many2one('efund.investor', string="Investor", required=True)
    fund_id = fields.Many2one('res.company', string="Fund", required=True)
    trigger = fields.Char()
    severity = fields.Selection([('info','Info'), ('suspicious','Suspicious'), ('critical','Critical')], default='suspicious', required=True)
    status = fields.Selection([('new','New'), ('reviewed','Reviewed'), ('escalated','Escalated'), ('closed','Closed')], default='new', required=True)
    score = fields.Integer()
    matched_transactions = fields.Many2many('efund.fund.transaction', string="Matched Transactions")
    assigned_to = fields.Many2one('res.users', string="Assigned To")
    notes = fields.Text()
    created_at = fields.Datetime(default=fields.Datetime.now)

    def action_assign(self, user_id):
        self.assigned_to = user_id
        self.status = 'reviewed'

    def action_escalate(self):
        self.status = 'escalated'
        # create activity for compliance team
        self.activity_schedule('mail.mail_activity_data_todo', user_id=self.assigned_to.id if self.assigned_to else False, summary=_("Investigate AML Alert"))

    def action_close(self):
        self.status = 'closed'