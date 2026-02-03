from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EfundInvestmentTransaction(models.Model):
    _name = 'efund.investment.transaction'
    _description = "Transaction / Exécution"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investment.transaction'))
    order_id = fields.Many2one('efund.investment.order', string="Ordre d'origine", ondelete='cascade')
    vehicule_id = fields.Many2one(related='order_id.vehicule_id', store=True)
    instrument_id = fields.Many2one(related='order_id.instrument_id', store=True)

    date_transaction = fields.Datetime(string="Date de transaction", default=fields.Datetime.now)
    date_settlement = fields.Date(string="Date de Règlement/Livraison", help="Date théorique dénouement (ex: T+2)")

    quantity = fields.Float(string="Quantité exécutée", required=True)
    price_unit = fields.Float(string="Prix unitaire d'exécution", required=True, digits=(16, 6))
    move_type = fields.Selection([('in', 'Entrée'), ('out', 'Sortie')], string="Type de transaction", required=True, )
    label = fields.Char(string="Libellé de la transaction", required=True,)

    # Frais de transaction
    broker_id = fields.Many2one('res.partner', string="Intermédiaire / Courtier")
    fees_amount = fields.Float(string="Frais de courtage")
    taxes_amount = fields.Float(string="Taxes / TTF")
    interest_amount = fields.Float(string="Intérêts courus")
    free_tax_amount = fields.Float(string="Montant HT",)
    amount_net = fields.Float(string="Montant Net", )
    average_execution_price = fields.Float(string="Prix moyen d'exécution",)
    state = fields.Selection([('draft', 'Provisoire'),('confirmed', 'Confirmé'), ('settled', 'Dénoué (R/L)'),('cancelled', 'Annulé')
    ], default='draft')


    def action_confirm_settlement(self):
        """Déclencheur principal du dénouement"""
        # Ajouter ici la logique de comptabilisation
        for rec in self:
            if rec.quantity <= 0:
                raise UserError(_("La quantité doit être supérieure à 0 pour confirmer la ligne."))
            if rec.price_unit <= 0:
                raise UserError(_("Le prix doit être supérieur à 0 pour confirmer la ligne."))

            # comptabiliation
            rec.message_post(
                body=_("Comptabilisation de la transaction. Lancement de la réconciliation..."),
                subject="comptabilisation de la souscription",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # 1- Crédit du compte du fond pour le montant investi
            vehicule_cash = self.env['efund.vehicule.cash'].search([
                ('vehicule_id', '=', rec.vehicule_id.id)
            ], limit=1)
            if not vehicule_cash:
                    vehicule_cash = self.env['efund.vehicule.cash'].create({
                    'name': f"Trésorerie - {rec.vehicule_id.name}",
                    'vehicule_id': rec.vehicule_id.id,
                    'company_id': rec.vehicule_id.company_id.id,
                })

            # deterniné le sens de l'opération
            direction = 'buy'
            if rec.order_id.operation_type == 'trade':
                if rec.order_id.direction == 'sell':
                    direction = 'sell'
            if rec.order_id.operation_type == 'opcvm':
                if rec.order_id.direction_opcvm == 'redemption':
                    direction = 'sell'


            # 1- debit ou credit de l'achat ou de la vente
            vehicule_move_trans = self.env['efund.vehicule.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                'vehicule_cash_id': vehicule_cash.id,
                'amount': rec.free_tax_amount,
                'move_type': 'investment_out' if direction == 'buy' else 'divestment_in',
                'liquidity_type': 'liquid',
                'label': rec.label,
                'state': 'reconciled',
                'trade_id': rec.id,
                'instrument_id': rec.order_id.instrument_id.id,
            })
            message = 'Débit du compte du véhicule au montant de %s francs  représentant le montant de la transaction N° %s' if direction == 'buy' else 'Crédit du compte du fond au montant de %s francs  représentant le montant de la transaction N°: %s'
            rec.message_post(
                body=_(message) % (
                    rec.free_tax_amount, rec.name),
                subject="comptabilisation de la transaction",
                message_type="comment",
                subtype_xmlid="mail.mt_comment"
            )

            # 2- Débit des frais de courtage

            vehicule_move_broker = self.env['efund.vehicule.cash.move']
            if rec.fees_amount > 0:
                vehicule_move_broker.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                    'vehicule_cash_id': vehicule_cash.id,
                    'amount': rec.fees_amount,
                    'move_type': 'broker_fee_out',
                    'liquidity_type': 'liquid',
                    'state': 'reconciled',
                    'label': 'Frais de courtage',
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,
                })
                rec.message_post(
                    body=_("Débit du compte du fond au montant de %s francs représentant les frais de courtage") % (
                        rec.fees_amount),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # 3- Debit des taxes
            vehicule_move_tax = self.env['efund.vehicule.cash.move']
            if rec.taxes_amount > 0:
                vehicule_move_tax.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                    'vehicule_cash_id': vehicule_cash.id,
                    'amount': rec.taxes_amount,
                    'move_type': 'tax_fee_out',
                    'liquidity_type': 'liquid',
                    'label': 'Taxes sur courtage',
                    'state': 'reconciled',
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,
                })
                rec.message_post(
                    body=_(
                        "Débit du compte du fond au montant de %s francs représentant les taxes sur la commission") % (
                             rec.taxes_amount),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # 4- Credit du compte des frais de commission
            instrument_fee_broker = self.env['efund.vehicule.instrument.fee']
            if rec.fees_amount > 0:
                instrument_fee_broker.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.vehicule.instrument.fee'),
                    'vehicule_id': rec.vehicule_id.id,
                    'fee_category': 'broker_fee',
                    'base_amount': rec.free_tax_amount,
                    'fee_amount': rec.fees_amount,
                    'vehicule_cash_move_id': vehicule_move_broker.id,
                    'state': 'reconciled',
                    'broker_id': rec.broker_id.id,
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,

                })
                rec.message_post(
                    body=_("Crédit du compte des frais au montant de %s francs représentant les frais de courtage") % (
                        rec.fees_amount),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # 5- Credit du compte des frais des taxes
            instrument_fee_tax = self.env['efund.vehicule.instrument.fee']
            if rec.taxes_amount > 0:
                instrument_fee_tax.create({
                    'name': self.env['ir.sequence'].next_by_code('efund.vehicule.instrument.fee'),
                    'vehicule_id': rec.vehicule_id.id,
                    'fee_category': 'vat',
                    'base_amount': rec.fees_amount,
                    'fee_amount': rec.taxes_amount,
                    'vehicule_cash_move_id': vehicule_move_tax.id,
                    'state': 'reconciled',
                    'broker_id': rec.broker_id.id,
                    'trade_id': rec.id,
                    'instrument_id': rec.order_id.instrument_id.id,
                })
                rec.message_post(
                    body=_(
                        "Crédit du compte des frais au montant de %s francs représentant les taxes sur la commission") % (
                             rec.taxes_amount),
                    subject="comptabilisation de la transaction",
                    message_type="comment",
                    subtype_xmlid="mail.mt_comment"
                )

            # Mise à jour des référence dans le compte cash du fond
            if rec.taxes_amount > 0:
                vehicule_move_broker.write({'fee_id': instrument_fee_tax.id})
            if rec.fees_amount > 0:
                vehicule_move_tax.write({'fee_id': instrument_fee_broker.id})

            # Livraison des titres (T+2) et mise à jour des positions
            position = self.env['efund.vehicule.position'].get_or_create_position(
                instrument_id = rec.order_id.instrument_id.id,
                first_price_date = rec.date_transaction,
                first_price = rec.price_unit,
                vehicule_id = rec.vehicule_id.id,
            )
            trade_date = self
            position.apply_trade(trade_date)
            position.action_generate_cashflows(rec.instrument_id)
            rec.message_post(
                body=_(
                    "Mise à jour de la position de l'instrument %s du fonds %s avec %s titres à %s francs") % (
                         rec.order_id.instrument_id.name, rec.vehicule_id.name, rec.quantity, rec.price_unit),
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
            self.write({'state': 'settled'})


    def _create_accounting_move(self):
        """Génération de l'écriture account.move"""
        self.ensure_one()
        move_obj = self.env['account.move']

        # Déterminer les comptes (à configurer dans le core ou la classe d'actif)
        acc_titre = self.instrument_id.asset_class_id.account_asset_id
        acc_banque = self.vehicule_id.bank_journal_id.default_account_id

        line_ids = []

        # Exemple pour un achat
        if self.order_id.direction == 'buy':
            # Débit Titres (Valeur brute)
            line_ids.append((0, 0, {
                'name': f"Achat {self.instrument_id.name}",
                'account_id': acc_titre.id,
                'debit': self.quantity * self.price_unit,
                'analytic_distribution': {
                    self.vehicule_id.analytic_account_id.id: 100} if self.vehicule_id.analytic_account_id else {},
            }))
            # Crédit Banque (Montant net)
            line_ids.append((0, 0, {
                'name': f"Règlement {self.instrument_id.name}",
                'account_id': acc_banque.id,
                'credit': self.amount_net,
            }))

        move = move_obj.create({
            'journal_id': self.vehicule_id.bank_journal_id.id,
            'date': self.date_settlement or fields.Date.today(),
            'ref': self.order_id.name,
            'line_ids': line_ids,
        })
        move.action_post()