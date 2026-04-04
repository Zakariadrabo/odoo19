from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class EfundPortfolioCashflow(models.Model):
    _name = 'efund.vehicule.cashflow'
    _description = 'Échéancier des flux de portefeuille'

    vehicule_id = fields.Many2one('efund.vehicule', string="Véhicule", readonly=True)
    position_id = fields.Many2one('efund.vehicule.portfolio', string="Position", ondelete='cascade')
    instrument_id = fields.Many2one('efund.vehicule.instrument.core', string="Instrument")

    date_scheduled = fields.Date(string="Date prévue")
    amount_expected = fields.Monetary(string="Montant attendu")
    currency_id = fields.Many2one(related='vehicule_id.currency_id')
    flow_type = fields.Selection([('coupon', 'Coupon'), ('redemption', 'Remboursement Capital'), ('dividend', 'Dividende')], string="Type de flux")
    state = fields.Selection([('draft', 'Attendu'),('received', 'Encaissé'),('late', 'En retard')], default='draft')

