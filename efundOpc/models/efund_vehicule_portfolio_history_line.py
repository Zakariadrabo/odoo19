from odoo import models, fields, api


class EfundPortfolioHistoryLine(models.Model):
    _name = 'efund.vehicule.portfolio.history.line'
    _description = "Ligne de détail de l'historique du portefeuille"
    _order = 'history_id desc, market_value desc'

    # ========== LIAISONS ==========
    history_id = fields.Many2one('efund.vehicule.portfolio.history', string="Parent History",required=True,ondelete='cascade',index=True)
    instrument_id = fields.Many2one('efund.vehicule.instrument.core', string="Instrument", required=True)
    currency_id = fields.Many2one(related='history_id.currency_id',store=True,string="Devise")

    # ========== DONNÉES FIGÉES (SNAPSHOT) ==========
    # On utilise des champs standards (non-compute) pour figer la donnée
    quantity = fields.Float(string="Quantité", digits=(16, 4))
    price_unit = fields.Float(string="Cours/Prix", digits=(16, 4), help="Prix de l'instrument à la date de l'historique")

    # Intérêts courus au moment du snapshot (très important pour les Obligations/DAT)
    accrued_interest = fields.Monetary(string="Intérêts Courus",currency_field='currency_id')

    # Valeur de marché totale (Quantité * Prix + Intérêts)
    market_value = fields.Monetary(string="Valeur de Marché",currency_field='currency_id',help="Valeur totale de la position à la date de valorisation")
    weight = fields.Float(string="% Portefeuille", digits=(16, 2), help="Poids de la ligne par rapport à la valeur totale du portefeuille")