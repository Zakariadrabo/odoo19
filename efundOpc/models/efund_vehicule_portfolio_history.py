from odoo import models, fields, api, _

class EfundMandateValuationHistory(models.Model):
    _name = 'efund.vehicule.portfolio.history'
    _description = 'Historique de valorisation du portefeuille'
    _order = 'date desc'

    vehicule_id = fields.Many2one('efund.vehicule', string="Mandat", required=True, ondelete='cascade')
    date = fields.Date(string="Date de valorisation", default=fields.Date.today, required=True)

    # Détails de la valorisation
    total_market_value = fields.Monetary(string="Valeur Titres")
    cash_balance = fields.Monetary(string="Solde Cash")
    total_valuation = fields.Monetary(string="Valorisation Totale", compute="_compute_total", store=True)
    currency_id = fields.Many2one(related='vehicule_id.currency_id')

    line_ids = fields.One2many('efund.vehicule.portfolio.history.line','history_id',string="Détail des Positions")

    @api.depends('total_market_value', 'cash_balance')
    def _compute_total(self):
        for rec in self:
            rec.total_valuation = rec.total_market_value + rec.cash_balance