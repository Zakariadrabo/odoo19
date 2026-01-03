# efund_position_adjustment.py

import logging
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

_logger = logging.getLogger(__name__)


class PositionAdjustment(models.Model):
    _name = "efund.position.adjustment"
    _description = "Ajustement de Position"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "adjustment_date desc"

    # Identification
    name = fields.Char(string="Référence",default=lambda self: _('Nouvel ajustement'),compute='_compute_name', store=True)
    position_id = fields.Many2one('efund.fund.position',string="Position",required=True, ondelete='cascade')

    # Ajoutez ce champ
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('posted', 'Comptabilisé'),
        ('cancelled', 'Annulé'),
    ], string="Statut",
        default='draft',
        tracking=True)

    event_id = fields.Many2one('efund.fund.instrument.event',string="Événement",required=True,ondelete='cascade')
    instrument_id = fields.Many2one('efund.fund.instrument',related='position_id.instrument_id',store=True,string="Instrument")
    fund_id = fields.Many2one('efund.fund',related='position_id.fund_id',store=True,string="Fonds")

    # Dates
    adjustment_date = fields.Date(string="Date d'ajustement",required=True,default=fields.Date.today)

    # Type d'ajustement
    adjustment_type = fields.Selection([
        ('dividend', 'Dividende'),
        ('split', 'Split/Reverse Split'),
        ('capital_change', 'Changement de Capital'),
        ('coupon', 'Coupon'),
        ('merger', 'Fusion'),
        ('spin_off', 'Scission'),
        ('other', 'Autre'),
    ], string="Type d'ajustement",
        required=True)

    # Impacts quantitatifs
    quantity_change = fields.Float(string="Changement de quantité",digits=(16, 4))
    new_quantity = fields.Float(string="Nouvelle quantité",digits=(16, 4))

    # Impacts financiers
    cash_impact = fields.Monetary(string="Impact cash",currency_field='currency_id')
    tax_amount = fields.Monetary(string="Montant taxe",currency_field='currency_id')
    price_adjustment = fields.Float(string="Ratio de prix",digits=(16, 6))

    # Informations
    description = fields.Text(string="Description")

    # Métadonnées
    currency_id = fields.Many2one('res.currency',related='position_id.currency_id',store=True)

    # Calcul du nom
    @api.depends('position_id', 'adjustment_date', 'adjustment_type')
    def _compute_name(self):
        for adj in self:
            if adj.position_id and adj.adjustment_date:
                adj.name = f"AJ-{adj.position_id.id}-{adj.adjustment_date}-{adj.adjustment_type}"
            else:
                adj.name = _('Nouvel ajustement')

    # Contraintes
    @api.constrains('quantity_change', 'new_quantity')
    def _check_quantities(self):
        for adj in self:
            if adj.new_quantity < 0:
                raise ValidationError(_("La quantité ne peut pas être négative."))

    # Méthodes pour changer le statut
    def action_post(self):
        """Marquer comme comptabilisé"""
        for adj in self:
            adj.state = 'posted'
            adj.message_post(
                body=_("Ajustement comptabilisé."),
                subject=_("Comptabilisation")
            )

    def action_cancel(self):
        """Annuler l'ajustement"""
        for adj in self:
            adj.state = 'cancelled'
            adj.message_post(
                body=_("Ajustement annulé."),
                subject=_("Annulation")
            )

    def action_draft(self):
        """Revenir au brouillon"""
        for adj in self:
            adj.state = 'draft'
