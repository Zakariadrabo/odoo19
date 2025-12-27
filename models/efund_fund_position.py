# efund_fund_position.py
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class FundPosition(models.Model):
    _name = "efund.fund.position"
    _description = "Position d'un fonds sur un instrument"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = "display_name"
    _order = "valuation_date desc, instrument_id"

    # ========== CHAMPS DE BASE ==========
    fund_id = fields.Many2one(
        'efund.fund',
        string="Fonds",
        required=True,
        index=True,
        ondelete='cascade'
    )

    instrument_id = fields.Many2one(
        'efund.fund.instrument',
        string="Instrument",
        required=True,
        index=True,
        domain="[('is_active', '=', True)]"
    )

    # ========== INFORMATIONS DE POSITION ==========
    quantity = fields.Float(
        string="Quantité",
        digits=(16, 4),
        default=0.0,
        required=True
    )

    avg_cost = fields.Monetary(
        string="Coût moyen unitaire",
        currency_field='currency_id'
    )

    market_value = fields.Monetary(
        string="Valeur de marché",
        currency_field='currency_id',
        compute='_compute_market_value',
        store=True,
    )

    valuation_date = fields.Date(
        string="Date de valorisation",
        default=fields.Date.today,
        required=True,
        index=True
    )

    # ========== INFORMATIONS DE COURS ==========
    last_price = fields.Float(
        string="Dernier cours",
        digits=(16, 4),
        compute='_compute_last_price',
        store=True,
    )

    last_price_date = fields.Date(
        string="Date dernier cours",
        compute='_compute_last_price',
        store=True,

    )

    # ========== CALCULS DE PERFORMANCE ==========
    unrealized_pl = fields.Monetary(
        string="Plus/Moins-value latente",
        currency_field='currency_id',
        compute='_compute_performance',
        store=True,
    )

    unrealized_pl_percent = fields.Float(
        string="PL %",
        digits=(16, 2),
        compute='_compute_performance',
        store=True,
    )
    decoration_state = fields.Selection(
        [('normal', 'Normal'),
         ('success', 'Success'),
         ('danger', 'Danger')],
        string="Decoration State",
        compute='_compute_decoration_state',
        store=True  # Important pour la performance
    )



    # ========== AUTRES INFORMATIONS ==========
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise de valorisation",
        related='fund_id.currency_id',
        store=True,
    )

    instrument_currency_id = fields.Many2one(
        'res.currency',
        string="Devise de l'instrument",
        related='instrument_id.currency_id',
        store=True,
    )

    state = fields.Selection([
        ('active', 'Active'),
        ('closed', 'Clôturée'),
        ('suspended', 'Suspendue')
    ], string="Statut", default='active', required=True)

    notes = fields.Text(string="Notes")

    display_name = fields.Char(
        string="Nom",
        compute='_compute_display_name',
        store=True
    )

    adjustment_ids = fields.One2many(
        'efund.position.adjustment',
        'position_id',
        string="Ajustements"
    )

    # les méthodes de dépendances

    @api.depends('unrealized_pl')
    def _compute_decoration_state(self):
        for record in self:
            if record.unrealized_pl > 0:
                record.decoration_state = 'success'
            elif record.unrealized_pl < 0:
                record.decoration_state = 'danger'
            else:
                record.decoration_state = 'normal'


    @api.depends('instrument_id')
    def _compute_last_price(self):
        """Récupère le dernier cours validé pour l'instrument"""
        for pos in self:
            if pos.instrument_id:
                # Chercher le dernier cours validé
                last_price = self.env['efund.fund.instrument.price'].search([
                    ('instrument_id', '=', pos.instrument_id.id),
                    ('is_validated', '=', True)
                ], order='date desc', limit=1)

                if last_price:
                    pos.last_price = last_price.price
                    pos.last_price_date = last_price.date
                else:
                    pos.last_price = 0.0
                    pos.last_price_date = False
            else:
                pos.last_price = 0.0
                pos.last_price_date = False

    @api.depends('quantity', 'avg_cost', 'last_price')
    def _compute_market_value(self):
        """Calcule la valeur de marché basée sur le dernier cours"""
        for pos in self:
            if pos.quantity and pos.last_price:
                pos.market_value = pos.quantity * pos.last_price
            else:
                pos.market_value = 0.0

    @api.depends('market_value', 'quantity', 'avg_cost')
    def _compute_performance(self):
        """Calcule les plus/moins-values latentes"""
        for pos in self:
            cost_basis = pos.quantity * (pos.avg_cost or 0.0)
            market_value = pos.market_value

            if cost_basis:
                pos.unrealized_pl = market_value - cost_basis
                pos.unrealized_pl_percent = ((market_value - cost_basis) / cost_basis) * 100
            else:
                pos.unrealized_pl = 0.0
                pos.unrealized_pl_percent = 0.0

    @api.depends('fund_id', 'instrument_id', 'valuation_date')
    def _compute_display_name(self):
        """Génère un nom d'affichage convivial"""
        for rec in self:
            if rec.fund_id and rec.instrument_id:
                rec.display_name = f"{rec.fund_id.name} - {rec.instrument_id.name} ({rec.valuation_date})"
            else:
                rec.display_name = "Nouvelle position"

    @api.constrains('quantity', 'avg_cost')
    def _check_positive_values(self):
        """Vérifie que les valeurs sont positives"""
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError(_("La quantité ne peut pas être négative."))
            if rec.avg_cost < 0:
                raise ValidationError(_("Le coût moyen ne peut pas être négatif."))

    # ========== MÉTHODES D'ACTION ==========
    def action_update_position(self):
        """Mettre à jour une position existante"""
        self.ensure_one()
        return {
            'name': _('Mettre à jour la position'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.position.update.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_position_id': self.id,
                'default_fund_id': self.fund_id.id,
                'default_instrument_id': self.instrument_id.id,
                'default_current_quantity': self.quantity,
                'default_current_avg_cost': self.avg_cost,
            }
        }

    def action_close_position(self):
        """Clôturer une position"""
        self.ensure_one()
        return {
            'name': _('Clôturer la position'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.position.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_position_id': self.id,
            }
        }

    def action_view_instrument(self):
        """Ouvrir la fiche de l'instrument"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Instrument'),
            'res_model': 'efund.fund.instrument',
            'view_mode': 'form',
            'res_id': self.instrument_id.id,
        }

    def _apply_instrument_event(self, event):
        """
        Applique un événement d'instrument à la position
        """
        self.ensure_one()

        _logger.info(f"Applying event {event.name} to position {self.id}")

        # Créer un enregistrement d'ajustement
        adjustment_vals = {
            'position_id': self.id,
            'event_id': event.id,
            'adjustment_date': fields.Date.today(),
            'adjustment_type': event.event_type,
            'description': f"Ajustement suite à l'événement: {event.name}",
        }

        # Appliquer les ajustements selon le type d'événement
        if event.event_type == 'dividend':
            # Pour un dividende, on crée un revenu
            adjustment_vals.update({
                'cash_impact': event.net_amount * self.quantity,
                'tax_amount': (event.cash_amount * (event.tax_rate / 100)) * self.quantity,
            })

        elif event.event_type in ['stock_split', 'reverse_split']:
            # Pour un split, on ajuste la quantité
            new_quantity = self.quantity * event.adjustment_ratio
            adjustment_vals.update({
                'quantity_change': new_quantity - self.quantity,
                'new_quantity': new_quantity,
                'price_adjustment': 1.0 / event.adjustment_ratio if event.adjustment_ratio > 0 else 1.0,
            })

            # Mettre à jour la position
            self.write({'quantity': new_quantity})

        elif event.event_type == 'capital_increase':
            # Pour une augmentation de capital
            adjustment_vals.update({
                'quantity_change': self.quantity * event.quantity_ratio,
                'description': f"Augmentation de capital - Ratio: {event.quantity_ratio}",
            })

        elif event.event_type == 'coupon_payment':
            # Pour un paiement de coupon
            adjustment_vals.update({
                'cash_impact': event.net_amount,
                'tax_amount': event.cash_amount - event.net_amount,
            })

        # Créer l'enregistrement d'ajustement
        adjustment = self.env['efund.position.adjustment'].create(adjustment_vals)

        # Poste un message sur la position
        self.message_post(
            body=_("Événement appliqué: %s") % event.name,
            subject=_("Ajustement de position")
        )

        return adjustment