from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FundInstrumentEquity(models.Model):
    _name = "efund.vehicule.instrument.core.equity"
    _description = "Instrument Financier - Action"
    _inherits = {'efund.vehicule.instrument.core': 'instrument_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']

    instrument_id = fields.Many2one('efund.vehicule.instrument.core', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='instrument_id.currency_id')

    # CHAMPS SPÉCIFIQUES AUX ACTIONS
    is_listed = fields.Boolean(string='Est Coté', default=False)
    listing_date = fields.Date(string='Date 1ère Cotation')
    sector = fields.Selection([('agriculture', 'Agriculture'), ('industrie', 'Industrie'),('technologie', 'Technologie'),
        ('sante', 'Santé'), ('finance', 'Finance'),('energie', 'Énergie'), ('materiaux', 'Matériaux'),('consommation', 'Consommation'),
        ('services', 'Services'),('immobilier', 'Immobilier'), ('telecom', 'Télécoms'),('utilities', 'Services publics')], string="Secteur d'activité")

    # Politique de Dividende
    last_dividend_amount = fields.Monetary(string="Dernier dividende versé", currency_field='currency_id')
    last_dividend_date = fields.Date(string="Date du dernier détachement")

    # Indicateurs de performance (Calculés)
    dividend_yield = fields.Float(string="Rendement (%)", compute="_compute_yield", store=True)
    dividend_frequency = fields.Selection([('annual', 'Annuel'), ('semi_annual', 'Semestriel'),('quarterly', 'Trimestriel'), ('monthly', 'Mensuel'),('none', 'Aucun')
    ], string="Fréquence des dividendes", default='annual')

    market_price = fields.Float(string="Cours de marché", digits=(16, 4))
    market_price_date = fields.Date(string="Date du cours")
    price_change_1d = fields.Float(string="Variation 1j", compute="_compute_price_change", digits=(16, 2))
    volume = fields.Integer(string="Volume échangé")
    listing_market = fields.Selection([('main', 'Marché principal'),
        ('secondary', 'Second marché'), ('growth', 'Marché croissance')], string="Marché de cotation")
    stock_exchange = fields.Char(string="Bourse")


    @api.depends('last_dividend_amount', 'instrument_id.market_price')
    def _compute_yield(self):
        for equity in self:
            if equity.market_price and equity.market_price > 0:
                equity.dividend_yield = (equity.last_dividend_amount / equity.market_price) * 100
            else:
                equity.dividend_yield = 0.0

    @api.depends('last_dividend_amount', 'market_price')
    def _compute_yield(self):
        for equity in self:
            if equity.market_price and equity.market_price > 0 and equity.last_dividend_amount:
                equity.dividend_yield = (equity.last_dividend_amount / equity.market_price) * 100
            else:
                equity.dividend_yield = 0.0

    def _compute_price_change(self):
        """Calcul de la variation journalière"""
        for equity in self:
            equity.price_change_1d = 0.0

    # Méthodes d'action
    def action_update_market_data(self):
        """Mettre à jour les données de marché"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Mise à jour',
                'message': 'Les données de marché seront mises à jour',
                'type': 'info',
                'sticky': False,
            }
        }

    def action_view_dividends(self):
        """Voir les dividendes"""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Fonctionnalité à venir',
                'message': 'La vue des dividendes sera disponible prochainement',
                'type': 'info',
                'sticky': False,
            }
        }

    def action_view_prices(self):
        """Voir l'historique des prix"""
        return self.action_view_dividends()

    def action_view_positions(self):
        """Voir les positions"""
        return self.action_view_dividends()

    def action_close_dat(self):
        self.write({'state': 'matured'})

    """
    @api.model
    def _update_state_cron(self):
        Cron pour mettre à jour l'état des DAT
        today = fields.Date.today()
        active_dats = self.search([('state', '=', 'active')])
        for dat in active_dats:
            if dat.end_date and dat.end_date < today:
                dat.state = 'matured'"""

    def action_activate(self):
        for record in self:
            #if not record.start_date:
             #   raise ValidationError(_("Merci de saisir la date d'opération."))
            record.state = 'active'
            record.message_post(body=_("Le fond a été activé."))

    def action_suspend(self):
        for record in self:
            if record.state != 'active':
                raise ValidationError(_("Seuls les fonds actifs peuvent être suspendus."))
            record.state = 'suspended'
            record.message_post(body=_("Le fond a été suspendu."))

    def action_liquidate(self):
        for record in self:
            if record.state not in ('active', 'suspended'):
                raise ValidationError(_("Seuls les fonds actifs ou suspendus peuvent être liquidés."))
            record.state = 'liquidated'
            record.message_post(body=_("Le fond a été liquidé."))

    def action_reset_to_draft(self):
        pass