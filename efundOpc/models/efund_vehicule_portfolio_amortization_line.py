from odoo import models, fields, api, _

class PortfolioAmortizationLine(models.Model):
    _name = "efund.portfolio.amortization.line"
    _description = "Ligne d'amortissement spécifique par véhicule"

    portfolio_id = fields.Many2one('efund.vehicule.portfolio', ondelete='cascade')
    date = fields.Date("Date")
    capital_debut = fields.Float("Capital Début")
    principal = fields.Float("Principal")
    interet = fields.Float("Intérêt")
    annuite = fields.Float("Annuité")
    capital_fin = fields.Float("Capital Restant")

    def get_position_form(self):
        """
        Ouvre la vue formulaire de la position spécifique (Portfolio)
        depuis la fiche du véhicule (Fonds/Mandat).
        """
        self.ensure_one()
        return {
            'name': _("Détail de la Position : %s") % self.portfolio_id.instrument_id.name,
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'efund.vehicule.portfolio',
            'res_id': self.id,
            'target': 'current',  # Ou 'new' pour une fenêtre surgissante (pop-up)
            'context': self.env.context,
        }