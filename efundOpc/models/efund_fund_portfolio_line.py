
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class EfundFundAssetLine(models.Model):
    _name = 'efund.fund.portfolio.line'
    _description = 'Ligne d\'Actif du Portefeuille'

    portfolio_id = fields.Many2one('efund.fund.portfolio', string="Portefeuille", required=True, ondelete='cascade')
    fund_id = fields.Many2one(related='portfolio_id.fund_id', store=True)
    instrument_id = fields.Many2one('efund.fund.instrument', string="Instrument financier", required=True)

    # Identification de l'actif
    asset_type = fields.Selection([('equity', 'Action'),('bond', 'Obligation'),('fund', 'Fonds'),('cash', 'Trésorerie'),('other', 'Autre')],
    string="Type d'Actif", required=True)

    asset_code = fields.Char(string="Code ISIN/Identifiant")
    asset_name = fields.Char(string="Nom de l'Actif")

    # Positions
    quantity = fields.Float(string="Quantité", digits=(16, 4))
    average_cost = fields.Monetary(string="Prix Moyen", currency_field='currency_id')
    current_price = fields.Monetary(string="Prix Courant", currency_field='currency_id')

    # Valeurs
    cost_value = fields.Monetary(string="Valeur au Coût",currency_field='currency_id',compute='_compute_values')
    current_value = fields.Monetary(string="Valeur Courante",currency_field='currency_id',compute='_compute_values')
    unrealized_pnl = fields.Monetary(string="Plus/Moins Value",currency_field='currency_id',compute='_compute_values')
    pnl_percentage = fields.Float(string="% P&L",compute='_compute_values')

    # Allocation
    portfolio_weight = fields.Float(string="Poids dans Portefeuille",compute='_compute_allocation')
    currency_id = fields.Many2one(related='portfolio_id.currency_id')

    @api.depends('quantity', 'average_cost', 'current_price')
    def _compute_values(self):
        for line in self:
            line.cost_value = line.quantity * line.average_cost
            line.current_value = line.quantity * line.current_price
            line.unrealized_pnl = line.current_value - line.cost_value
            if line.cost_value != 0:
                line.pnl_percentage = (line.unrealized_pnl / line.cost_value) * 100

    @api.depends('current_value', 'portfolio_id.total_value')
    def _compute_allocation(self):
        for line in self:
            if line.portfolio_id.total_value:
                line.portfolio_weight = (line.current_value / line.portfolio_id.total_value) * 100
            else:
                line.portfolio_weight = 0.0