from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FundBourseOrderExecutionLine(models.Model):
    _name = 'efund.bourse.order.execution.line'
    _description = 'Execution Line of Bourse Order'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'execution_date desc'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.bourse.order.execution.line'))
    order_id = fields.Many2one('efund.bourse.order', required=True, ondelete='cascade')
    order_sens = fields.Selection([('buy', 'Achat'), ('sell', 'Vente')], string="Sens de l'achat/vente", required=True)
    fund_id = fields.Many2one(related='order_id.fund_id', string="Fonds (OPCVM)", store=True)
    mandat_id = fields.Many2one(related="order_id.mandat_id", string="Mandat", store=True)
    execution_date = fields.Date(required=True, string='Date d\'Execution', default=fields.Date.today)
    quantity = fields.Float(required=True, string='Quantité', digits=(16, 4))
    price = fields.Float(required=True, string='Prix', digits=(16, 6))
    broker_id = fields.Many2one("efund.depositaire", string="Dépositaire du fond", store=True)
    reference = fields.Char(string="Référence SGI")
    currency_id = fields.Many2one(related='order_id.currency_id', store=True)

    total_broker_commission = fields.Monetary(string="Commission de courtage", store=True)
    total_tob_commission = fields.Monetary(string="Taxe TVA", store=True)
    total_interest = fields.Monetary(string="Intérêts courus", store=True)
    total_amount = fields.Monetary(string="Total montant", store=True, compute='_compute_total_amount', )
    total_amount_ht = fields.Monetary(string="Montant HT", compute="_compute_total_amount_ht", store=True)
    fund_cash_move_id = fields.Many2one('efund.fund.cash.move', string="Cash Fond", readonly=True)

    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('confirmed', 'Confirmé'),
        ('done', 'Exécuté'),
        ('accounted', 'Comptabilisé'),
        ('cancelled', 'Annulé'),
        ('reconciled', 'Réconcilié')
    ], default='draft', string='État', tracking=True)

    description = fields.Text(string="Description")

    # Contraintes
    _sql_constraints = models.Constraint([(
        'CHECK(quantity > 0)',
        'La quantité doit être positive!'),
        ('CHECK(price >= 0)',
         'Le prix ne peut pas être négatif!')
    ]
    )

    @api.depends('quantity', 'price')
    def _compute_total_amount_ht(self):
        for line in self:
            line.total_amount_ht = line.quantity * line.price

    @api.depends('total_amount_ht', 'total_broker_commission', 'total_tob_commission', 'total_interest')
    def _compute_total_amount(self):
        for line in self:
            line.total_amount = (
                    line.total_amount_ht +
                    line.total_broker_commission +
                    line.total_tob_commission +
                    line.total_interest
            )

    # Méthodes de workflow
    def action_draft(self):
        self.write({'state': 'draft'})

    def action_confirm(self):
        self.write({'state': 'confirmed'})

    def action_done(self):
        self.write({'state': 'done'})

    def action_account(self):
        # Ajouter ici la logique de comptabilisation
        self.write({'state': 'accounted'})
        for rec in self:
            if rec.quantity <= 0:
                raise UserError(_("La quantité doit être supérieure à 0 pour confirmer la ligne."))
            if rec.price <= 0:
                raise UserError(_("Le prix doit être supérieur à 0 pour confirmer la ligne."))

            # comptabiliation
            rec.message_post(
                body=_("Comptabilisation de la transaction. Lancement de la réconciliation..."),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # 1- Crédit du compte du fond pour le montant investi
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', rec.fund_id.id)
            ], limit=1)
            if not fund_cash:
                fund_cash = self.env['efund.fund.cash'].create({
                    'name': f"Trésorerie - {rec.fund_id.name}",
                    'fund_id': rec.fund_id.id,
                    'company_id': rec.fund_id.company_id.id,
                })

            # 1- debit ou credit de l'achat ou de la vente
            fund_move_trans = self.env['efund.fund.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'amount': rec.total_amount_ht,
                'move_type': 'investment_out' if rec.order_sens == 'buy' else 'divestment_in',
                'liquidity_type': 'liquid',
                'state': 'reconciled',
                'trade_id': rec.id,
                'instrument_id': rec.order_id.instrument_id.id,
                'fund_id': rec.fund_id.id,
            })
            message = 'Débit du compte du fond au montant de %s francs  représentant le montant de la transaction N° %s' if rec.order_sens == 'buy' else 'Crédit du compte du fond au montant de %s francs  représentant le montant de la transaction N°: %s'
            rec.message_post(
                body=_(message) % (
                    rec.total_amount_ht,rec.name),
                subject="comptabilisation de la transaction",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # 2- Débit des frais de courtage

            fund_move_broker = self.env['efund.fund.cash.move']
            if rec.total_broker_commission > 0:
                fund_move_broker.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                    'fund_cash_id': fund_cash.id,
                    'amount': rec.total_broker_commission,
                    'move_type': 'broker_fee_out',
                    'liquidity_type': 'liquid',
                    'state': 'reconciled',
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,
                    'fund_id': rec.fund_id.id,
                })
                rec.message_post(
                    body=_("Débit du compte du fond au montant de %s francs représentant les frais de courtage") % (
                        rec.total_broker_commission),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # 3- Debit des taxes
            fund_move_tax = self.env['efund.fund.cash.move']
            if rec.total_tob_commission > 0:
                fund_move_tax.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                    'fund_cash_id': fund_cash.id,
                    'amount': rec.total_tob_commission,
                    'move_type': 'tax_fee_out',
                    'liquidity_type': 'liquid',
                    'state': 'reconciled',
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,
                    'fund_id': rec.fund_id.id,
                })
                rec.message_post(
                    body=_(
                        "Débit du compte du fond au montant de %s francs représentant les taxes sur la commission") % (
                             rec.total_tob_commission),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # 4- Credit du compte des frais de commission
            instrument_fee_broker = self.env['efund.fund.instrument.fee']
            if rec.total_broker_commission > 0:
                instrument_fee_broker.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.fund.instrument.fee'),
                    'fund_id': rec.fund_id.id,
                    'transaction_type': rec.order_sens,
                    'fee_category': 'broker_fee',
                    'base_amount': rec.total_amount_ht,
                    'fee_amount': rec.total_broker_commission,
                    'fund_cash_move_id': fund_move_broker.id,
                    'state': 'reconciled',
                    'broker_id': rec.broker_id.id,
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,

                })
                rec.message_post(
                    body=_("Crédit du compte des frais au montant de %s francs représentant les frais de courtage") % (
                        rec.total_broker_commission),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # 5- Credit du compte des frais des taxes
            instrument_fee_tax = self.env['efund.fund.instrument.fee']
            if rec.total_tob_commission > 0:
                instrument_fee_tax.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.fund.instrument.fee'),
                    'fund_id': rec.fund_id.id,
                    'transaction_type': rec.order_sens,
                    'fee_category': 'vat',
                    'base_amount': rec.total_broker_commission,
                    'fee_amount': rec.total_tob_commission,
                    'fund_cash_move_id': fund_move_tax.id,
                    'state': 'reconciled',
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,

                })
                rec.message_post(
                    body=_(
                        "Crédit du compte des frais au montant de %s francs représentant les taxes sur la commission") % (
                             rec.total_tob_commission),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # Mise à jour des référence dans le compte cash du fond
            if rec.total_tob_commission > 0:
                fund_move_broker.write({'fee_id': instrument_fee_tax.id})
            if rec.total_broker_commission > 0:
                fund_move_tax.write({'fee_id': instrument_fee_broker.id})

            # Livraison des titres (T+2) et mise à jour des positions
            position = self.env['efund.fund.position']._get_or_create_position(
                instrument_id=rec.order_id.instrument_id.id,
                valuation_date=rec.execution_date,
                issuance_price=rec.price,
                fund_id=rec.fund_id.id,
                mandat_id=None,
            )
            trade_date = self
            position.apply_trade(trade_date)
            rec.message_post(
                body=_(
                    "Mise à jour de la position de l'instrument %s du fonds %s avec %s titres à %s francs") % (
                         rec.order_id.instrument_id.name, rec.fund_id.name, rec.quantity, rec.price),
                subject="mise à jour de la position",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # Post du résultat sur le chatter
            rec.message_post(
                body=_("Réconciliation terminée avec succès."),
                subject="Réconciliation réussie",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )
            self.write({'state': 'reconciled'})


    def action_cancel(self):
        self.write({'state': 'cancelled'})


    # Contraintes supplémentaires
    @api.constrains('execution_date')
    def _check_execution_date(self):
        for line in self:
            if line.execution_date > fields.Date.today():
                raise UserError(_("La date d'exécution ne peut pas être dans le futur."))
