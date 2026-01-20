from odoo import models, fields, api, _
from odoo.exceptions import UserError

class EfundInvestmentTransaction(models.Model):
    _name = 'efund.investment.transaction'
    _description = "Transaction / Exécution"

    order_id = fields.Many2one('efund.investment.order', string="Ordre d'origine", ondelete='cascade')
    vehicule_id = fields.Many2one(related='order_id.vehicule_id', store=True)
    instrument_id = fields.Many2one(related='order_id.instrument_id', store=True)

    date_transaction = fields.Datetime(string="Date de transaction", default=fields.Datetime.now)
    date_settlement = fields.Date(string="Date de Règlement/Livraison", help="Date théorique dénouement (ex: T+2)")

    quantity = fields.Float(string="Quantité exécutée", required=True)
    price_unit = fields.Float(string="Prix unitaire d'exécution", required=True, digits=(16, 6))

    # Frais de transaction
    broker_id = fields.Many2one('res.partner', string="Intermédiaire / Courtier")
    fees_amount = fields.Float(string="Frais de courtage")
    taxes_amount = fields.Float(string="Taxes / TTF")

    amount_net = fields.Float(string="Montant Net", compute='_compute_totals', store=True)

    state = fields.Selection([
        ('draft', 'Provisoire'),
        ('confirmed', 'Confirmé'),
        ('settled', 'Dénoué (R/L)'),
        ('cancelled', 'Annulé')
    ], default='draft')

    @api.depends('quantity', 'price_unit', 'fees_amount', 'taxes_amount')
    def _compute_totals(self):
        for trade in self:
            # Pour un achat, les frais s'ajoutent au coût ; pour une vente, ils se déduisent du produit
            gross_amount = trade.quantity * trade.price_unit
            if trade.order_id.direction == 'buy':
                trade.amount_net = gross_amount + trade.fees_amount + trade.taxes_amount
            else:
                trade.amount_net = gross_amount - trade.fees_amount - trade.taxes_amount


    def action_confirm_settlement(self):
        """Déclencheur principal du dénouement"""
        for trade in self:
            if trade.state == 'settled':
                continue

            # 1. Mise à jour de l'inventaire (Position)
            trade._update_position_and_pru()

            # 2. Génération de la pièce comptable
            trade._create_accounting_move()

            trade.state = 'settled'

    def _update_portfolio_position(self):
        # Logique à implémenter :
        # 1. Chercher la position actuelle (Portfolio + Instrument)
        # 2. Mettre à jour Quantité et PRU (Prix de Revient Unitaire)
        pass


    def _update_position_and_pru(self):
        """Calcul du nouveau PRU et mise à jour de la quantité"""
        self.ensure_one()
        pos_obj = self.env['efund.investment.position']

        # Chercher la position existante
        position = pos_obj.search([
            ('vehicule_id', '=', self.vehicule_id.id),
            ('instrument_id', '=', self.instrument_id.id)
        ], limit=1)

        if not position:
            if self.order_id.direction == 'sell':
                raise UserError(_("Impossible de vendre un instrument que vous ne possédez pas."))
            # Création initiale
            pos_obj.create({
                'vehicule_id': self.vehicule_id.id,
                'instrument_id': self.instrument_id.id,
                'quantity': self.quantity,
                'pru': self.price_unit + (self.fees_amount / self.quantity if self.quantity else 0)
            })
        else:
            if self.order_id.direction == 'buy':
                # Nouveau PRU = (Ancienne Valeur + Nouvelle Valeur) / Nouvelle Quantité Totale
                new_total_qty = position.quantity + self.quantity
                new_val = (position.quantity * position.pru) + self.amount_net
                position.pru = new_val / new_total_qty if new_total_qty else 0
                position.quantity = new_total_qty
            else:
                # Vente : On réduit la quantité, le PRU ne change pas
                if position.quantity < self.quantity:
                    raise UserError(_("Position insuffisante pour cette vente."))
                position.quantity -= self.quantity

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