from odoo import models, fields, api, _
from odoo.exceptions import UserError

class FundProfile(models.Model):
    _name = "efund.fund.profile"
    _description = "Profil de paramétrage des fonds"

    name = fields.Char(required=True)
    nav_frequency = fields.Selection([('daily','Daily'),('weekly','Weekly'),('monthly','Monthly')], default='daily')
    valuation_time = fields.Float(help="Heure limite (UTC) pour la valorisation (ex: 17.30)")
    settlement_days = fields.Integer(default=2)
    allow_negative_positions = fields.Boolean(default=False)



