from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FundValuationLog(models.Model):
    _name = "efund.fund.valuation.log"
    _description = "Fund Valuation Log"

    valuation_id = fields.Many2one("efund.fund.valuation", required=True, ondelete="cascade")
    timestamp = fields.Datetime(default=fields.Datetime.now)
    user_id = fields.Many2one("res.users", default=lambda self: self.env.user)
    action = fields.Char()
    message = fields.Text()
