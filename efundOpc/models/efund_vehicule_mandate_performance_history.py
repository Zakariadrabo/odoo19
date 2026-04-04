from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EfundMandatePerformance(models.Model):
    _name = 'efund.vehicule.mandate.performance.history'
    _description = 'Historique de performance annuelle'
    _order = 'year desc'

    mandat_id = fields.Many2one('efund.vehicule.mandate', string="Mandat", required=True, ondelete='cascade')
    year = fields.Integer(string="Année", required=True)
    anniversary_date = fields.Date(string="Date Anniversaire")

    # Taux réalisé (TWR ou MWR selon votre méthode)
    realized_rate = fields.Float(string="Taux Réalisé (%)", digits=(16, 2))

    # Comparaison
    previous_year_rate = fields.Float(string="Taux Année N-1 (%)", readonly=True)
    variation = fields.Float(string="Variation (bps)", compute="_compute_variation", store=True)

    @api.depends('realized_rate', 'previous_year_rate')
    def _compute_variation(self):
        for rec in self:
            # Calcul en points de base (bps)
            rec.variation = (rec.realized_rate - rec.previous_year_rate) * 100

