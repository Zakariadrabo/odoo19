from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
class EfundAccountPartMove(models.Model):
    _name = 'efund.account.part.move'
    _description = 'Mouvements compte titres'

    part_account_id = fields.Many2one('efund.account.part', required=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id',store=True)
    investor_id = fields.Many2one(related='part_account_id.investor_id',store=True)
    move_type = fields.Selection([
        ('subscription','Souscription'),
        ('redemption','Rachat'),
    ], required=True)
    parts = fields.Float(required=True)
    date = fields.Datetime(default=fields.Datetime.now)
