from odoo import models, fields, api, _


class EfundFundPortfolio(models.Model):
    _name = 'efund.fund.portfolio'
    _description = 'Actif détenu par le fonds'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Portefeuille", required=True)
    fund_id = fields.Many2one('efund.fund',string="Fonds",required=True,index=True,ondelete='cascade')
    company_id = fields.Many2one('res.company', related='fund_id.company_id', store=True)

    currency_id = fields.Many2one(related='fund_id.currency_id',store=True)
    quantity = fields.Float(compute='_compute_position',string="Quantité détenue",store=False)
    average_cost = fields.Monetary(compute='_compute_position',string="Coût moyen",currency_field='currency_id',store=False)
    market_value = fields.Monetary(compute='_compute_market_value',string="Valeur de marché",currency_field='currency_id')

    # Métriques du portefeuille
    total_value = fields.Monetary(string="Valeur Totale",currency_field='currency_id',compute='_compute_portfolio_metrics')
    number_of_assets = fields.Integer(string="Nombre d'Actifs",compute='_compute_portfolio_metrics')

    # Performance
    performance_date = fields.Date(string="Date de Valorisation")
    total_cost = fields.Monetary(string="Coût Total", currency_field='currency_id')
    unrealized_pnl = fields.Monetary(string="Plus/Moins Value", currency_field='currency_id')

    # Composition
    asset_line_ids = fields.One2many('efund.fund.portfolio.line','portfolio_id',string="Lignes d'Actifs")

    _fund_unique = models.Constraint(
        'unique(fund_id)',
        'Un seul portefeuille par fonds.'
    )

    @api.depends('asset_line_ids', 'asset_line_ids.current_value')
    def _compute_portfolio_metrics(self):
        for portfolio in self:
            portfolio.total_value = sum(portfolio.asset_line_ids.mapped('current_value'))
            portfolio.number_of_assets = len(portfolio.asset_line_ids)

    def _compute_position(self):
        for asset in self:
            moves = self.env['efund.fund.asset.move'].search([
                ('asset_id', '=', asset.id)
            ])

            qty = 0.0
            total_cost = 0.0

            for m in moves:
                if m.move_type == 'buy':
                    qty += m.quantity
                    total_cost += m.quantity * m.price
                elif m.move_type == 'sell':
                    qty -= m.quantity
                    total_cost -= m.quantity * asset.average_cost if asset.average_cost else 0.0

            asset.quantity = qty
            asset.average_cost = qty and (total_cost / qty) or 0.0

    def _compute_market_value(self):
        for asset in self:
            asset.market_value = asset.quantity * asset.instrument_id.last_price
