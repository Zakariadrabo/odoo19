import logging
from datetime import date
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class FundInstrumentEvent(models.Model):
    _name = "efund.fund.instrument.event"
    _description = "Événement sur Instrument Financier"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "event_date desc, instrument_id"

    # ----------------------------------------------------
    # IDENTIFICATION
    # ----------------------------------------------------
    name = fields.Char(
        string="Référence",
        required=True,
        default=lambda self: _('Nouvel événement'),
        tracking=True
    )

    instrument_id = fields.Many2one(
        'efund.fund.instrument',
        string="Instrument",
        required=True,
        ondelete='cascade',
        domain="[('state', '=', 'approved')]",
        tracking=True
    )

    instrument_name = fields.Char(
        related='instrument_id.name',
        string="Nom de l'instrument",
        store=True
    )

    isin = fields.Char(
        related='instrument_id.isin',
        string="Code ISIN",
        store=True
    )

    # ----------------------------------------------------
    # TYPE D'ÉVÉNEMENT
    # ----------------------------------------------------
    event_type = fields.Selection([
        ('corporate_action', 'Action sur Valeur'),
        ('capital_increase', 'Augmentation de Capital'),
        ('capital_reduction', 'Réduction de Capital'),
        ('stock_split', 'Fractionnement d\'Action (Split)'),
        ('reverse_split', 'Regroupement d\'Action (Reverse Split)'),
        ('dividend', 'Dividende'),
        ('interest_payment', 'Paiement d\'Intérêt'),
        ('coupon_payment', 'Paiement de Coupon'),
        ('maturity', 'Échéance'),
        ('call_option', 'Option d\'Achat'),
        ('put_option', 'Option de Vente'),
        ('merger', 'Fusion/Acquisition'),
        ('spin_off', 'Scission (Spin-off)'),
        ('delisting', 'Retrait de Cotation'),
        ('rating_change', 'Changement de Notation'),
        ('default', 'Défaut de Paiement'),
        ('restructuring', 'Restructuration'),
        ('other', 'Autre événement')
    ], string="Type d'événement",
        required=True,
        tracking=True)

    # ----------------------------------------------------
    # DATES
    # ----------------------------------------------------
    announcement_date = fields.Date(
        string="Date d'annonce",
        tracking=True,
        help="Date à laquelle l'événement a été annoncé"
    )

    event_date = fields.Date(
        string="Date de l'événement",
        required=True,
        tracking=True,
        default=fields.Date.today,
        help="Date effective de l'événement"
    )

    record_date = fields.Date(
        string="Date de détachement",
        tracking=True,
        help="Date de détachement/record date"
    )

    payment_date = fields.Date(
        string="Date de paiement",
        tracking=True,
        help="Date de paiement effectif"
    )

    # ----------------------------------------------------
    # CARACTÉRISTIQUES DE L'ÉVÉNEMENT
    # ----------------------------------------------------
    description = fields.Text(
        string="Description",
        tracking=True,
        help="Description détaillée de l'événement"
    )

    impact_type = fields.Selection([
        ('positive', 'Positif'),
        ('negative', 'Négatif'),
        ('neutral', 'Neutre'),
        ('adjustment', 'Ajustement technique')
    ], string="Impact",
        tracking=True)

    adjustment_ratio = fields.Float(
        string="Ratio d'ajustement",
        digits=(16, 8),
        default=1.0,
        tracking=True,
        help="Ratio pour ajuster les positions (ex: 0.5 pour 1 pour 2 split)"
    )

    cash_amount = fields.Monetary(
        string="Montant monétaire",
        currency_field='currency_id',
        tracking=True,
        help="Montant de cash distribué (dividende, intérêt, etc.)"
    )

    new_instrument_id = fields.Many2one(
        'efund.fund.instrument',
        string="Nouvel instrument",
        tracking=True,
        help="Nouvel instrument créé (fusion, scission, etc.)"
    )

    quantity_ratio = fields.Float(
        string="Ratio de quantité",
        digits=(16, 8),
        default=1.0,
        tracking=True,
        help="Ratio de conversion pour les nouvelles actions"
    )

    # ----------------------------------------------------
    # STATUT ET VALIDATION
    # ----------------------------------------------------
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('pending', 'En attente'),
        ('confirmed', 'Confirmé'),
        ('processed', 'Traité'),
        ('cancelled', 'Annulé')
    ], string="Statut",
        default='draft',
        tracking=True)

    is_processed = fields.Boolean(
        string="Traité",
        compute='_compute_is_processed',
        store=True
    )

    processed_date = fields.Date(
        string="Date de traitement",
        tracking=True
    )

    # ----------------------------------------------------
    # INFORMATIONS FINANCIÈRES
    # ----------------------------------------------------
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        related='instrument_id.currency_id',
        store=True
    )

    tax_rate = fields.Float(
        string="Taux de taxe (%)",
        digits=(16, 4),
        tracking=True
    )

    net_amount = fields.Monetary(
        string="Montant net",
        currency_field='currency_id',
        compute='_compute_net_amount',
        store=True
    )

    # ----------------------------------------------------
    # LIENS AVEC LES POSITIONS
    # ----------------------------------------------------
    position_ids = fields.Many2many(
        'efund.fund.position',
        string="Positions impactées",
        compute='_compute_affected_positions',
        store=False
    )

    affected_position_count = fields.Integer(
        string="Nombre Positions impactées",
        compute='_compute_affected_positions',
        store=False
    )

    # ----------------------------------------------------
    # FICHIERS ET DOCUMENTS
    # ----------------------------------------------------
    attachment_ids = fields.Many2many(
        'ir.attachment',
        string="Documents joints",
        help="Documents relatifs à l'événement"
    )



    # ----------------------------------------------------
    # MÉTHODES COMPUTÉES
    # ----------------------------------------------------
    @api.depends('state')
    def _compute_is_processed(self):
        for event in self:
            event.is_processed = event.state == 'processed'

    @api.depends('cash_amount', 'tax_rate')
    def _compute_net_amount(self):
        for event in self:
            if event.cash_amount:
                tax_amount = event.cash_amount * (event.tax_rate / 100)
                event.net_amount = event.cash_amount - tax_amount
            else:
                event.net_amount = 0.0

    def _compute_affected_positions(self):
        for event in self:
            positions = self.env['efund.fund.position'].search([
                ('instrument_id', '=', event.instrument_id.id),
                ('valuation_date', '<=', event.record_date or event.event_date)
            ])
            event.position_ids = positions
            event.affected_position_count = len(positions)

    # ----------------------------------------------------
    # CONTRAINTES
    # ----------------------------------------------------
    @api.constrains('adjustment_ratio')
    def _check_adjustment_ratio(self):
        for event in self:
            if event.adjustment_ratio <= 0:
                raise ValidationError(_("Le ratio d'ajustement doit être positif."))

    @api.constrains('quantity_ratio')
    def _check_quantity_ratio(self):
        for event in self:
            if event.quantity_ratio < 0:
                raise ValidationError(_("Le ratio de quantité ne peut pas être négatif."))

    @api.constrains('announcement_date', 'event_date', 'record_date', 'payment_date')
    def _check_dates_consistency(self):
        for event in self:
            dates = []
            if event.announcement_date:
                dates.append(('announcement_date', event.announcement_date))
            dates.append(('event_date', event.event_date))
            if event.record_date:
                dates.append(('record_date', event.record_date))
            if event.payment_date:
                dates.append(('payment_date', event.payment_date))

            # Trier par date
            sorted_dates = sorted(dates, key=lambda x: x[1])

            # Vérifier la cohérence logique
            for i in range(len(sorted_dates) - 1):
                if sorted_dates[i][1] > sorted_dates[i + 1][1]:
                    raise ValidationError(_(
                        "Incohérence dans les dates: %s ne peut pas être après %s"
                    ) % (sorted_dates[i][0], sorted_dates[i + 1][0]))

    # ----------------------------------------------------
    # ACTIONS
    # ----------------------------------------------------
    def action_confirm(self):
        """Confirmer l'événement"""
        for event in self:
            if event.state != 'draft':
                continue
            event.state = 'confirmed'
            event.message_post(
                body=_("Événement confirmé."),
                subject=_("Confirmation d'événement")
            )

    def action_process(self):
        """Traiter l'événement"""
        for event in self:
            if event.state != 'confirmed':
                continue

            # Marquer comme traité
            event.state = 'processed'
            event.processed_date = fields.Date.today()

            # Appliquer l'impact sur les positions
            event._apply_to_positions()

            event.message_post(
                body=_("Événement traité et appliqué aux positions."),
                subject=_("Traitement d'événement")
            )

    def action_cancel(self):
        """Annuler l'événement"""
        for event in self:
            event.state = 'cancelled'
            event.message_post(
                body=_("Événement annulé."),
                subject=_("Annulation d'événement")
            )

    def action_reset_to_draft(self):
        """Revenir au brouillon"""
        for event in self:
            event.state = 'draft'

    def action_view_affected_positions(self):
        """Voir les positions impactées"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Positions impactées - {self.name}',
            'res_model': 'efund.fund.position',
            'view_mode': 'list,form',
            'domain': [('instrument_id', '=', self.instrument_id.id)],
            'context': {
                'search_default_date_before': self.record_date or self.event_date,
                'default_instrument_id': self.instrument_id.id,
            },
        }

    def _apply_to_positions(self):
        """Appliquer l'événement aux positions concernées"""
        self.ensure_one()

        positions = self.env['efund.fund.position'].search([
            ('instrument_id', '=', self.instrument_id.id),
            ('valuation_date', '<=', self.record_date or self.event_date),
            ('state', '=', 'active')
        ])

        _logger.info(f"Applying event {self.name} to {len(positions)} positions")

        for position in positions:
            position._apply_instrument_event(self)

    # ----------------------------------------------------
    # MÉTHODES DE CRÉATION AUTOMATIQUE
    # ----------------------------------------------------
    @api.model
    def create_coupon_event(self, coupon):
        """Créer un événement pour un paiement de coupon"""
        event_vals = {
            'instrument_id': coupon.instrument_id.id,
            'name': f"Coupon {coupon.coupon_number} - {coupon.instrument_id.name}",
            'event_type': 'coupon_payment',
            'announcement_date': coupon.announcement_date,
            'event_date': coupon.payment_date,
            'record_date': coupon.record_date,
            'payment_date': coupon.payment_date,
            'description': f"Paiement du coupon {coupon.coupon_number}",
            'cash_amount': coupon.amount,
            'state': 'confirmed' if coupon.status == 'accrued' else 'draft',
        }
        return self.create(event_vals)

    @api.model
    def create_dividend_event(self, instrument, amount, payment_date, record_date=None):
        """Créer un événement de dividende"""
        event_vals = {
            'instrument_id': instrument.id,
            'name': f"Dividende - {instrument.name}",
            'event_type': 'dividend',
            'event_date': payment_date,
            'record_date': record_date or payment_date,
            'payment_date': payment_date,
            'description': f"Distribution de dividende",
            'cash_amount': amount,
            'state': 'confirmed',
        }
        return self.create(event_vals)