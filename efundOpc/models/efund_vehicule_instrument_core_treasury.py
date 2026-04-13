import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)


class FundInstrumentTreasury(models.Model):
    _name = "efund.vehicule.instrument.core.treasury"
    _description = "Bons du Trésor et Titres de Créances"
    _inherits = {'efund.vehicule.instrument.core': 'instrument_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']

    instrument_id = fields.Many2one('efund.vehicule.instrument.core', required=True, ondelete='cascade')

    # Caractéristiques de l'émission
    face_value = fields.Monetary(string="Valeur Nominale", default=1000000.0, required=True)
    issue_date = fields.Date(string="Date d'émission", required=True)
    maturity_date = fields.Date(string="Date d'échéance", required=True)

    # Logique de calcul (Taux vs Montant)
    calculation_type = fields.Selection([
        ('rate', 'Saisir le Taux'),
        ('amount', 'Saisir le Montant/Prix')
    ], string="Mode de saisie", default='rate', required=True)

    yield_rate = fields.Float(string="Taux de rendement (%)", digits=(12, 6))
    discount_amount = fields.Monetary(string="Montant de l'escompte")
    purchase_price = fields.Monetary(string="Prix d'acquisition / Net", help="Prix après escompte")

    # Paramètres de calcul
    day_count_convention = fields.Selection([('360', '360'),('365', '365'),], string="Convention de base", default='360')

    @api.onchange('yield_rate', 'face_value', 'issue_date', 'maturity_date', 'calculation_type')
    def _onchange_calculate_by_rate(self):
        """ Calcule le montant si on saisit le taux """
        if self.calculation_type == 'rate' and self.yield_rate:
            duration = self._get_duration()
            if duration > 0:
                # Formule escompte simple : Intérêt = (Nominal * Taux * Durée) / (Base * 100)
                base = int(self.day_count_convention)
                self.discount_amount = (self.face_value * self.yield_rate * duration) / (base * 100)
                self.purchase_price = self.face_value - self.discount_amount

    @api.onchange('purchase_price', 'face_value', 'issue_date', 'maturity_date', 'calculation_type')
    def _onchange_calculate_by_price(self):
        """ Calcule le taux si on saisit le prix d'achat """
        if self.calculation_type == 'amount' and self.purchase_price:
            duration = self._get_duration()
            if duration > 0 and self.face_value > 0:
                self.discount_amount = self.face_value - self.purchase_price
                base = int(self.day_count_convention)
                # Taux = (Escompte * Base * 100) / (Nominal * Durée)
                self.yield_rate = (self.discount_amount * base * 100) / (self.face_value * duration)

    def _get_duration(self):
        if self.issue_date and self.maturity_date:
            return (self.maturity_date - self.issue_date).days
        return 0