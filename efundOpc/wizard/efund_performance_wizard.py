import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)


class EfundPerformanceWizard(models.TransientModel):
    _name = 'efund.performance.wizard'
    _description = 'Calcul de Performance'

    # --- Entrées ---
    vehicule_id = fields.Many2one('efund.vehicule', string="Véhicule", required=True)
    mandat_id = fields.Many2one('efund.vehicule.mandate', string="Mandate", required=True)
    date_t = fields.Date(string="Date début (T)", required=True, default=fields.Date.today)
    date_t1 = fields.Date(string="Date fin (T1)", required=True, default=fields.Date.today)
    target_rate = fields.Float(string="Taux Objectif (%)", digits=(16, 4), help="Taux annuel attendu")

    # --- Résultats (Calculés) ---
    valuation_t = fields.Monetary(string="Valorisation T", )
    valuation_t1 = fields.Monetary(string="Valorisation T1", )
    performance = fields.Monetary(string="Montant Généré", )

    accrued_coupon_client = fields.Monetary(string="Coupon Couru Client", )
    superperformance = fields.Monetary(string="Profit réalisé", )

    currency_id = fields.Many2one(related='vehicule_id.currency_id')

    def action_save_performance(self):
        self.ensure_one()
        _logger.info(f"*********** afficher le mandat {self.mandat_id}")
        save_line = self.env['efund.vehicule.mandate.performance.history'].create({
            'mandat_id': self.mandat_id.id,
            'start_date': self.date_t,
            'end_date': self.date_t1,
            'target_rate': self.target_rate,
            'start_date_valuation': self.valuation_t,
            'end_date_valuation': self.valuation_t1,
            'performance': self.performance,
            'accrued_coupon_client': self.accrued_coupon_client,
            'superperformance': self.superperformance,
        })

    def action_confirm_execution(self):
        self.ensure_one()
        for rec in self:
            # 1. Récupération des valorisations (Actif Net) aux deux dates
            # On utilise la méthode NAV que nous avons construite précédemment
            val_t = self.env["efund.service"].get_net_asset_value(rec.vehicule_id, rec.date_t)
            _logger.info(f"********** j'ai fini t {rec.date_t}")
            val_t1 = self.env["efund.service"].get_net_asset_value(rec.vehicule_id, rec.date_t1)
            _logger.info(f"********** j'ai fini t1 {rec.date_t1}")

            _logger.info(f"Valorisation T: {val_t} - Valorisation T1: {val_t1}")

            rec.valuation_t = val_t.get("total_nav")
            rec.valuation_t1 = val_t1.get("total_nav")

            rec.target_rate = (rec.valuation_t1/rec.valuation_t) - 1

            # 2. Calcul de la performance (Variation absolue)
            rec.performance = val_t1.get("total_nav") - val_t.get("total_nav")

            # 3. Calcul du Coupon Couru Client (Prorata Temporis)
            # Formule: (T1 - T) / 365 * Taux Objectif * Montant initial (T)
            if rec.date_t and rec.date_t1:
                days = (rec.date_t1 - rec.date_t).days
                # On utilise la valorisation à T comme "Montant misé"
                rec.accrued_coupon_client = (days / 365.0) * (rec.mandat_id.target_return_rate / 100.0) * rec.mandat_id.initial_amount
            else:
                rec.accrued_coupon_client = 0.0

            # 4. Superperformance
            rec.superperformance = rec.performance - rec.accrued_coupon_client

            return {
                'type': 'ir.actions.act_window',
                'res_model': 'efund.performance.wizard',
                'view_mode': 'form',
                'res_id': self.id,  # On reste sur le même enregistrement
                'target': 'new',  # Indispensable pour rester en mode "pop-up"
            }