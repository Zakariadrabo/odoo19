# efund_fund_instrument_price.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from datetime import datetime, date


class FundInstrumentPrice(models.Model):
    _name = "efund.fund.instrument.price"
    _description = "Cours d'un instrument financier"
    _order = "date desc, instrument_id"
    _rec_name = "display_name"

    instrument_id = fields.Many2one('efund.fund.instrument', string="Instrument", required=True, index=True)
    date = fields.Date(string="Date du cours", required=True, default=fields.Date.today, index=True)
    price = fields.Float(string="Cours", digits=(16, 4), required=True)
    currency_id = fields.Many2one('res.currency', string="Devise du cours", required=True)
    is_validated = fields.Boolean(string="Validé", default=False)
    validated_date = fields.Date(string="Date de validation")
    validated_by = fields.Many2one('res.users', string="Validé par")

    # Champs calculés
    display_name = fields.Char(string="Nom", compute='_compute_display_name', store=True)

    @api.depends('instrument_id', 'date', 'price')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.instrument_id.name} - {rec.date} - {rec.price:.4f}"

    def action_validate(self):
        """Valider un cours et mettre à jour les positions"""
        for price in self:
            if not price.is_validated:
                price.is_validated = True
                price.validated_date = fields.Date.today()
                price.validated_by = self.env.user

                # Mettre à jour les positions des fonds
                self._update_fund_positions(price)

    def _update_fund_positions(self, price):
        """Mettre à jour le market_value des positions basé sur le nouveau cours"""
        # Récupérer toutes les positions pour cet instrument
        positions = self.env['efund.fund.position'].search([
            ('instrument_id', '=', price.instrument_id.id),
        ])

        # Mettre à jour le dernier cours dans l'instrument
        price.instrument_id.write({
            'last_validated_price': price.price,
            'last_price_date': price.date,
        })

        # Recalculer la valeur de marché pour toutes les positions
        for position in positions:
            position._compute_market_value()

    def action_validate_batch(self):
        """Valider plusieurs cours en une fois"""
        unvalidated = self.filtered(lambda p: not p.is_validated)
        for price in unvalidated:
            price.action_validate()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Validation terminée'),
                'message': _('%s cours ont été validés.') % len(unvalidated),
                'type': 'success',
                'sticky': False,
            }
        }