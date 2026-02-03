from odoo import models, fields, api, _


class EfundFundCashMove(models.Model):
    _name = 'efund.vehicule.cash.move'
    _description = 'Mouvement espèces du fonds'
    _order = 'date desc, id desc'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'))
    vehicule_cash_id = fields.Many2one('efund.vehicule.cash', string="Compte du fond espèces", required=True, ondelete='cascade')
    vehicule_id = fields.Many2one(related='vehicule_cash_id.vehicule_id',store=True,index=True)
    company_id = fields.Many2one(related='vehicule_id.company_id', store=True)
    currency_id = fields.Many2one(related='vehicule_cash_id.currency_id', store=True)
    move_type = fields.Selection([('subscription_in', 'Entrée Souscription'),('redemption_out', 'Sortie Rachat'),
        ('deposit_in', 'Dépôt Investisseur'),('withdraw_out', 'Retrait Investisseur'),('investment_out', 'Investissement Actif'),
        ('divestment_in', 'Désinvestissement'),('fee_out', 'Frais de Gestion'),('broker_fee_out', 'Frais de Courtage'),('tax_fee_out', 'Taxes'),('dividend_in', 'Dividendes Reçus'),
        ('coupon_in', 'Coupons Reçus'),('interest_in', 'Intérêts'),('transfer_in', 'Virement Entrant'),
        ('transfer_out', 'Virement Sortant'),('other_out', 'Autre Opération'),], string="Type de Mouvement", required=True)
    amount = fields.Monetary(required=True,currency_field='currency_id')
    label = fields.Char(string="Libellé")
    date = fields.Datetime(string="Date de valeur", required=True, default=fields.Datetime.now)
    value_date = fields.Datetime(string="Date comptable")
    reference = fields.Char(string="Référence opération")
    state = fields.Selection([('draft', 'Brouillon'),('pending', 'En Attente'),('posted', 'Validé'),('cancelled', 'Annulé'),('reconciled', 'Réconcilié'),
    ], string="Statut", default='draft')
    note = fields.Text()
    # Nouveau champ pour le solde circulant
    balance_running = fields.Monetary(string="Solde circulant",compute='_compute_balance_running',store=True,)

    # État de liquidité
    liquidity_type = fields.Selection([
        ('liquid', 'Liquide'),
        ('pending', 'En Attente'),
        ('blocked', 'Bloqué'),
    ], string="Liquidité", default='liquid')

    # Références aux transactions investisseurs
    investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Mouvement Investisseur")
    subscription_id = fields.Many2one('efund.investor.subscription', string="Ordre de Souscription")
    redemption_id = fields.Many2one('efund.investor.redemption', string="Ordre de Rachat")

    # Références aux transactions Portefeuille
    trade_id = fields.Many2one('efund.investment.transaction', string="Ordre de Souscription")
    fee_id = fields.Many2one('efund.vehicule.instrument.fee', string="Ordre de Rachat")
    instrument_id = fields.Many2one('efund.vehicule.instrument.core',string="Instrument Financier",)

    # Informations complémentaires
    investor_id = fields.Many2one('efund.investor', string="Contrepartie", ondelete='cascade')
    #partner_id = fields.Many2one('res.partner', string="Contrepartie")
    journal_id = fields.Many2one('account.journal', string="Journal Comptable")
    account_move_id = fields.Many2one('account.move', string="Écriture Comptable")

    # Champs calculés
    is_incoming = fields.Boolean(string="Entrant", compute='_compute_direction', store=True)
    balance_after = fields.Monetary(string="Solde Après", compute='_compute_balances')

    @api.depends('amount', 'vehicule_cash_id', 'date', 'create_date')
    def _compute_balance_running(self):
        for move in self:
            # On cherche tous les mouvements du même compte cash antérieurs ou égaux à celui-ci
            # On trie par date et par ID pour garantir un ordre constant
            previous_moves = self.search([
                ('vehicule_cash_id', '=', move.vehicule_cash_id.id),
                '|', ('date', '<', move.date),
                '&', ('date', '=', move.date), ('id', '<=', move.id)
            ])
            # Somme de tous les montants (positifs et négatifs)
            move.balance_running = sum(m.amount if '_in' in m.move_type else -m.amount
                for m in previous_moves
            )
