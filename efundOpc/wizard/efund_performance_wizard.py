from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EfundPerformanceWizard(models.TransientModel):
    _name = 'efund.performance.wizard'
    _description = 'Calcul de Performance'

    # --- Entrées ---
    vehicule_id = fields.Many2one('efund.vehicule', string="Véhicule", required=True)
    date_t = fields.Date(string="Date début (T)", required=True, default=fields.Date.today)
    date_t1 = fields.Date(string="Date fin (T1)", required=True, default=fields.Date.today)
    target_rate = fields.Float(string="Taux Objectif (%)", digits=(16, 4), help="Taux annuel attendu")

    # --- Résultats (Calculés) ---
    valuation_t = fields.Monetary(string="Valorisation T", compute="_compute_performance")
    valuation_t1 = fields.Monetary(string="Valorisation T1", compute="_compute_performance")
    performance = fields.Monetary(string="Performance brute", compute="_compute_performance")

    accrued_coupon_client = fields.Monetary(string="Coupon Couru Client", compute="_compute_performance")
    superperformance = fields.Monetary(string="Superperformance", compute="_compute_performance")

    currency_id = fields.Many2one(related='vehicule_id.currency_id')

    @api.depends('date_t', 'date_t1', 'vehicule_id', 'target_rate')
    def _compute_performance(self):
        for wizard in self:
            # 1. Récupération des valorisations (Actif Net) aux deux dates
            # On utilise la méthode NAV que nous avons construite précédemment
            val_t = wizard.vehicule_id.get_net_asset_value(wizard.vehicule_id, wizard.date_t)['total_nav']
            val_t1 = wizard.vehicule_id.get_net_asset_value(wizard.vehicule_id, wizard.date_t1)['total_nav']

            wizard.valuation_t = val_t
            wizard.valuation_t1 = val_t1

            # 2. Calcul de la performance (Variation absolue)
            wizard.performance = val_t1 - val_t

            # 3. Calcul du Coupon Couru Client (Prorata Temporis)
            # Formule: (T1 - T) / 365 * Taux Objectif * Montant initial (T)
            if wizard.date_t and wizard.date_t1:
                days = (wizard.date_t1 - wizard.date_t).days
                # On utilise la valorisation à T comme "Montant misé"
                wizard.accrued_coupon_client = (days / 365.0) * (wizard.target_rate / 100.0) * val_t
            else:
                wizard.accrued_coupon_client = 0.0

            # 4. Superperformance
            wizard.superperformance = wizard.performance - wizard.accrued_coupon_client
    def action_confirm_execution(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window_close',
        }