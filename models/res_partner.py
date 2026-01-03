from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResCompany(models.Model):
    _inherit = "res.partner"

    is_investor = fields.Boolean(string="Is Investor",help="Indicates if this partner is the investor of the fund.",default=False)
    is_fund = fields.Boolean(string="Is Fund",help="Indicates if this partner is the investor of the fund.",default=False,)
    is_management_company = fields.Boolean(string="Is Management Company",help="Indicates if this partner is the management company of the fund.",default=False,)