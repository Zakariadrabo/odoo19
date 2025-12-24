from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EfundBourseOrder(models.Model):
    _name = "efund.bourse.order"
    _description = "Ordre de Bourse"
    _order = "order_date desc"

    # ---------------------------------------------------------------------
    # IDENTIFICATION
    # ---------------------------------------------------------------------
    name = fields.Char(
        string="Référence",
        default=lambda self: _('ORD/%s') % fields.Date.today(),
        readonly=True
    )

    order_date = fields.Date(
        string="Date Ordre",
        default=fields.Date.context_today,
        required=True
    )

    fund_id = fields.Many2one(
        'efund.fund',
        string="Fonds (OPCVM)",
        required=True
    )



    # ---------------------------------------------------------------------
    # STATUT
    # ---------------------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Non envoyé'),
        ('validated', 'Validé'),
        ('partial', 'Pris en charge'),
        ('executed', 'Exécuté'),
        ('cancelled', 'Relâché')
    ], default='draft', string="Statut")

    # ---------------------------------------------------------------------
    # TYPE D’ORDRE
    # ---------------------------------------------------------------------
    is_subscription = fields.Boolean(string="Souscription")
    is_buy = fields.Boolean(string="Achat")
    is_sell = fields.Boolean(string="Vente")

    order_type = fields.Selection([
        ('market', 'Au marché'),
        ('limit', 'À cours limité'),
        ('threshold', 'À seuil'),
    ], string="Type d’ordre", required=True)

    # ---------------------------------------------------------------------
    # INSTRUMENT FINANCIER
    # ---------------------------------------------------------------------
    instrument_id = fields.Many2one(
        'efund.fund.instrument',
        string="Instrument Financier",
        required=True
    )
    depositaire_sgi = fields.Many2one(
        'efund.depositaire',
        string="Dépositaire du fond",
        required=True
    )


    symbol = fields.Char(
        related='instrument_id.ticker',
        string="Symbole",
        readonly=True
    )

    market_place = fields.Selection(
        related='instrument_id.market',
        string="Place",
        readonly=True
    )

    depository = fields.Selection(
        related='instrument_id.custodian',
        string="Dépositaire",
        readonly=True
    )

    # ---------------------------------------------------------------------
    # CONDITIONS FINANCIÈRES
    # ---------------------------------------------------------------------
    price_limit = fields.Float(string="Cours limite")
    quantity = fields.Float(string="Quantité", required=True)

    allow_loss = fields.Boolean(
        string="P ? (Vente à perte autorisée)",
        help="Valable uniquement pour les ordres d'achat"
    )

    expiry_date = fields.Date(string="Date limite")

    # ---------------------------------------------------------------------
    # PRÉNOTATION (CALCULÉE)
    # ---------------------------------------------------------------------
    gross_amount = fields.Monetary(
        string="Montant brut",
        compute="_compute_prenotation",
        currency_field="currency_id"
    )

    commission_sgi = fields.Monetary(
        string="Commission SGI",
        compute="_compute_prenotation",
        currency_field="currency_id"
    )

    commission_total = fields.Monetary(
        string="Total commissions",
        compute="_compute_prenotation",
        currency_field="currency_id"
    )

    currency_id = fields.Many2one(
        related='fund_id.currency_id',
        readonly=True
    )

    # ---------------------------------------------------------------------
    # SIGNATAIRES
    # ---------------------------------------------------------------------
    signatory_ids = fields.Many2many(
        'res.partner',
        string="Signataires"
    )

    comment = fields.Text(string="Commentaires")

    # ---------------------------------------------------------------------
    # CALCUL PRÉNOTATION
    # ---------------------------------------------------------------------
    @api.depends('price_limit', 'quantity')
    def _compute_prenotation(self):
        for rec in self:
            rec.gross_amount = rec.price_limit * rec.quantity
            rec.commission_sgi = rec.gross_amount * 0.005  # 0,5% exemple
            rec.commission_total = rec.commission_sgi

    # ---------------------------------------------------------------------
    # ACTIONS
    # ---------------------------------------------------------------------
    def action_validate(self):
        for rec in self:
            rec.state = 'validated'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'
