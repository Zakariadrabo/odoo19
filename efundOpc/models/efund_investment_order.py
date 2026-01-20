from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EfundInvestmentOrder(models.Model):
    _name = 'efund.investment.order'
    _description = "Ordre d'Investissement"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Référence", required=True, copy=False, readonly=True, default=lambda self: _('Nouveau'))

    # Liens vers le portefeuille et l'instrument
    vehicule_id = fields.Many2one('efund.vehicule', string="Portefeuille", required=True, ondelete='restrict')  # Référence à votre modèle de base
    instrument_id = fields.Many2one('efund.fund.instrument.core', string="Instrument", required=True)
    currency_id = fields.Many2one(related='instrument_id.currency_id', store=True)

    direction = fields.Selection([('buy', 'Achat'), ('sell', 'Vente')],string="Sens", required=True, default='buy')
    state = fields.Selection([('draft', 'Brouillon'),('confirmed', 'Confirmé'),('executed', 'Exécuté'),('cancelled', 'Annulé')], string="État", default='draft', tracking=True)

    # Détails de l'ordre
    quantity = fields.Float(string="Quantité ordonnée", required=True, digits=(16, 4))
    price_type = fields.Selection([('market', 'Au marché'),('limit', 'Prix limité')], string="Type de prix", default='market')
    limit_price = fields.Float(string="Prix limite", digits=(16, 6))

    # Suivi des exécutions
    transaction_ids = fields.One2many('efund.investment.transaction', 'order_id', string="Exécutions")
    executed_qty = fields.Float(string="Quantité exécutée", compute='_compute_execution_data', store=True)
    remaining_qty = fields.Float(string="Quantité restante", compute='_compute_execution_data', store=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('Nouveau')) == _('Nouveau'):
            vals['name'] = self.env['ir.sequence'].next_by_code('efund.investment.order') or _('Nouveau')
        return super().create(vals)

    @api.depends('transaction_ids.quantity')
    def _compute_execution_data(self):
        for order in self:
            executed = sum(order.transaction_ids.mapped('quantity'))
            order.executed_qty = executed
            order.remaining_qty = order.quantity - executed

    def action_confirm(self):
        self.ensure_one()
        pass
        #self.write({'state': 'confirmed'})

    def action_cancel(self):
        pass