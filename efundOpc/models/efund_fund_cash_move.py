from odoo import models, fields, api, _


class EfundFundCashMove(models.Model):
    _name = 'efund.fund.cash.move'
    _description = 'Mouvement espèces du fonds'
    _order = 'date desc, id desc'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.fund.cash.move'))
    cash_account_id = fields.Many2one('efund.fund.cash', string="Compte espèces", required=True, ondelete='cascade')
    fund_id = fields.Many2one(related='cash_account_id.fund_id',store=True,index=True)
    company_id = fields.Many2one(related='fund_id.company_id', store=True)
    currency_id = fields.Many2one(related='cash_account_id.currency_id', store=True)
    move_type = fields.Selection([('subscription_in', 'Entrée Souscription'),('redemption_out', 'Sortie Rachat'),
        ('deposit_in', 'Dépôt Investisseur'),('withdraw_out', 'Retrait Investisseur'),('investment_out', 'Investissement Actif'),
        ('divestment_in', 'Désinvestissement'),('fee_out', 'Frais de Gestion'),('dividend_in', 'Dividendes Reçus'),
        ('coupon_in', 'Coupons Reçus'),('interest_in', 'Intérêts'),('transfer_in', 'Virement Entrant'),
        ('transfer_out', 'Virement Sortant'),('other', 'Autre Opération'),], string="Type de Mouvement", required=True)
    amount = fields.Monetary(required=True,currency_field='currency_id')
    date = fields.Date(string="Date de valeur", required=True, default=fields.Date.today)
    value_date = fields.Date(string="Date comptable")
    reference = fields.Char(string="Référence opération")
    state = fields.Selection([('draft', 'Brouillon'),('pending', 'En Attente'),('posted', 'Validé'),('cancelled', 'Annulé'),
    ], string="Statut", default='draft')
    note = fields.Text()

    # Références aux transactions investisseurs
    investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Mouvement Investisseur")
    subscription_id = fields.Many2one('efund.investor.subscription', string="Ordre de Souscription")
    redemption_id = fields.Many2one('efund.investor.redemption', string="Ordre de Rachat")

    # Informations complémentaires
    partner_id = fields.Many2one('res.partner', string="Contrepartie")
    journal_id = fields.Many2one('account.journal', string="Journal Comptable")
    account_move_id = fields.Many2one('account.move', string="Écriture Comptable")

    # Champs calculés
    is_incoming = fields.Boolean(string="Entrant", compute='_compute_direction', store=True)
    balance_after = fields.Monetary(string="Solde Après", compute='_compute_balances')
