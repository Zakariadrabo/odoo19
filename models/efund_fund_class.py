from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FundClass(models.Model):
    _name = "efund.fund.class"
    _description = "Classe de parts d'un fonds"

    name = fields.Char(required=True)
    fund_id = fields.Many2one('res.company', domain="[('company_type','=','fonds')]", required=True)
    currency_id = fields.Many2one('res.currency')
    shares_outstanding = fields.Float(default=0.0)
