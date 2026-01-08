from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FundKycCheck(models.Model):
    _name = "efund.kyc.check"
    _description = "KYC Check / Screening Log"
    _order = "checked_at desc"

    investor_id = fields.Many2one('efund.investor', string="Investor", required=True, ondelete='cascade')
    check_type = fields.Selection([('sanctions','Sanctions'),('pep','PEP'),('id_validity','ID Validity'),('address','Address Check')], required=True)
    result = fields.Selection([('ok','OK'),('alert','Alert'),('fail','Fail')], required=True)
    details = fields.Text()
    checked_at = fields.Datetime(default=fields.Datetime.now)
    source = fields.Char()
    operator_id = fields.Many2one('res.users')