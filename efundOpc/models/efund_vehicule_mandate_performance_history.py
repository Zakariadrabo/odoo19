from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EfundMandatePerformance(models.Model):
    _name = 'efund.vehicule.mandate.performance.history'
    _description = 'Historique de performance annuelle'
    _order = 'start_date desc'

    mandat_id = fields.Many2one('efund.vehicule.mandate', string="Mandat", required=True, ondelete='cascade')
    target_return_rate = fields.Float(related='mandat_id.target_return_rate', string="Taux Objectif", )
    start_date= fields.Date(string="Date début", required=True, default=fields.Date.today)
    end_date = fields.Date(string="Date fin", required=True, default=fields.Date.today)
    target_rate = fields.Float(string="Performance", digits=(16, 4), help="Taux annuel attendu")

    # --- Résultats (Calculés) ---
    start_date_valuation = fields.Monetary(string="Valorisation Début", )
    end_date_valuation = fields.Monetary(string="Valorisation Fin", )
    performance = fields.Monetary(string="Montant généré", )

    accrued_coupon_client = fields.Monetary(string="Coupon Couru Client", )
    superperformance = fields.Monetary(string="Profit réalisé", )
    currency_id = fields.Many2one(related='mandat_id.vehicule_id.currency_id')


