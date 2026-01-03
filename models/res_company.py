from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class ResPartner(models.Model):
    _inherit = "res.company"

    is_management_company = fields.Boolean(string="Is Management Company",help="Indicates if this company is the management company of the fund.",default=False)
    is_funder = fields.Boolean(string="Is Investor",help="Indicates if this company is the investor of the fund.",default=False,)
    management_company_id = fields.One2many('efund.management.company','company_id',string="Management Company Record")

