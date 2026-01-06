# fichier : efund_fund_portfolio_move.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class EfundFundAssetMove(models.Model):
    _name = 'efund.fund.portfolio.move'
    _description = 'Mouvements d\'Acquisition/Vente d\'Actifs'
    _order = 'trade_date desc, id desc'

    # Identifiant
    name = fields.Char(
        string="Référence Ordre",
        required=True,
        default=lambda self: self.env['ir.sequence'].next_by_code('efund.fund.portfolio.move')
    )

    # Lien vers le fonds
    fund_id = fields.Many2one('efund.fund',string="Fonds",required=True,index=True)
    portfolio_id = fields.Many2one('efund.fund.portfolio',string="Portefeuille",required=True,index=True)
    # Type de transaction
    move_type = fields.Selection([
        ('purchase', 'Achat'),('sale', 'Vente'),('transfer_in', 'Transfert Entrant'),('transfer_out', 'Transfert Sortant'),
        ('corporate_action', 'Action Corporate'),('dividend_reinvestment', 'Réinvestissement Dividende'),
        ('coupon', 'Coupon'),('valuation', 'Réévaluation'),], string="Type de Mouvement", required=True)
    direction = fields.Selection([('buy', 'Achat'),('sell', 'Vente'),], string="Direction", compute='_compute_direction', store=True)

    # Actif concerné
    instrument_id = fields.Many2one('efund.fund.instrument', string="Instrument financier", required=True)

    # Détails de la transaction
    trade_date = fields.Date(string="Date de Transaction",required=True,default=fields.Date.today)
    settlement_date = fields.Date(string="Date de Règlement/Livraison",required=True)
    quantity = fields.Float(string="Quantité",required=True,digits=(16, 4))
    price = fields.Monetary(string="Prix Unitaire",currency_field='currency_id',required=True)
    total_amount = fields.Monetary(string="Montant Total",currency_field='currency_id',compute='_compute_amounts',store=True)

    # Frais et commissions
    brokerage_fees = fields.Monetary(string="Frais de Courtage",currency_field='currency_id',default=0.0)
    transaction_fees = fields.Monetary(string="Frais de Transaction",currency_field='currency_id',default=0.0)
    taxes = fields.Monetary(string="Taxes",currency_field='currency_id',default=0.0)
    net_amount = fields.Monetary(string="Montant Net",currency_field='currency_id',compute='_compute_amounts',store=True)

    # Contrepartie
    counterparty_id = fields.Many2one('res.partner',string="Contrepartie")
    broker_id = fields.Many2one('res.partner',string="Courtier",domain=[('is_broker', '=', True)])

    # Références
    order_ref = fields.Char(string="Référence Ordre Courtier")
    contract_ref = fields.Char(string="Référence Contrat")

    # Statut
    state = fields.Selection([('draft', 'Brouillon'),('confirmed', 'Confirmé'),('executed', 'Exécuté'),('settled', 'Réglé'),
        ('cancelled', 'Annulé'),], string="Statut", default='draft')

    # Liens avec la comptabilité
    account_move_id = fields.Many2one('account.move',string="Écriture Comptable")

    # Liens avec cash movements
    cash_move_id = fields.Many2one('efund.fund.cash.move',string="Mouvement Cash Associé")

    # Devise
    currency_id = fields.Many2one('res.currency',related='fund_id.currency_id',store=True)

    # Champs calculés
    average_price = fields.Monetary(string="Prix Moyen Pondéré",currency_field='currency_id',compute='_compute_average_price')

    @api.depends('move_type')
    def _compute_direction(self):
        for move in self:
            move.direction = 'buy' if move.move_type in ['purchase', 'transfer_in', 'dividend_reinvestment'] else 'sell'

    @api.depends('quantity', 'price', 'brokerage_fees', 'transaction_fees', 'taxes')
    def _compute_amounts(self):
        for move in self:
            move.total_amount = move.quantity * move.price

            if move.direction == 'buy':
                # Achat: montant + frais
                move.net_amount = move.total_amount + move.brokerage_fees + move.transaction_fees + move.taxes
            else:
                # Vente: montant - frais
                move.net_amount = move.total_amount - move.brokerage_fees - move.transaction_fees - move.taxes

    @api.depends('total_amount', 'quantity')
    def _compute_average_price(self):
        for move in self:
            if move.quantity:
                move.average_price = move.total_amount / move.quantity
            else:
                move.average_price = 0.0

    def action_confirm(self):
        """Confirmer l'ordre de transaction"""
        for move in self:
            if move.state != 'draft':
                continue
            move.write({'state': 'confirmed'})

            # Mettre à jour le portefeuille (position temporaire)
            self._update_portfolio_position(move, provisional=True)

    def action_execute(self):
        """Exécuter la transaction"""
        for move in self:
            if move.state != 'confirmed':
                continue

            # 1. Mettre à jour définitivement le portefeuille
            self._update_portfolio_position(move, provisional=False)

            # 2. Créer le mouvement de cash associé
            cash_move = self._create_cash_move(move)
            move.cash_move_id = cash_move.id

            # 3. Créer l'écriture comptable
            account_move = self._create_accounting_entry(move)
            move.account_move_id = account_move.id

            move.write({'state': 'executed'})

    def action_settle(self):
        """Marquer comme réglé/livré"""
        for move in self:
            if move.state != 'executed':
                continue

            # Vérifier que le cash a effectivement été reçu/payé
            if move.cash_move_id and move.cash_move_id.state == 'posted':
                move.write({'state': 'settled'})

    def _update_portfolio_position(self, move, provisional=False):
        """Mettre à jour la position dans le portefeuille"""
        portfolio_line = self.env['efund.fund.portfolio.line'].search([
            ('portfolio_id', '=', move.portfolio_id.id),
            ('asset_id', '=', move.asset_id.id),
        ], limit=1)

        if move.direction == 'buy':
            # ACHAT
            if portfolio_line:
                # Mise à jour d'une ligne existante
                new_quantity = portfolio_line.quantity + move.quantity
                new_cost = (portfolio_line.cost_value + move.net_amount)

                portfolio_line.write({
                    'quantity': new_quantity,
                    'average_cost': new_cost / new_quantity if new_quantity > 0 else 0,
                    'cost_value': new_cost,
                })
            else:
                # Création d'une nouvelle ligne
                self.env['efund.fund.portfolio.line'].create({
                    'portfolio_id': move.portfolio_id.id,
                    'asset_id': move.asset_id.id,
                    'asset_type': move.asset_id.asset_type,
                    'asset_code': move.asset_id.isin,
                    'asset_name': move.asset_id.name,
                    'quantity': move.quantity,
                    'average_cost': move.net_amount / move.quantity if move.quantity > 0 else 0,
                    'current_price': move.price,  # Prix initial
                    'cost_value': move.net_amount,
                    'current_value': move.total_amount,
                })

        else:
            # VENTE
            if portfolio_line:
                if portfolio_line.quantity < move.quantity:
                    raise UserError(_("Quantité à vendre supérieure à la position existante"))

                # Calcul du coût des parts vendues (FIFO)
                cost_of_sale = (move.quantity / portfolio_line.quantity) * portfolio_line.cost_value

                # Mise à jour
                new_quantity = portfolio_line.quantity - move.quantity
                new_cost = portfolio_line.cost_value - cost_of_sale

                portfolio_line.write({
                    'quantity': new_quantity,
                    'cost_value': new_cost,
                    'average_cost': new_cost / new_quantity if new_quantity > 0 else 0,
                })

                # Si quantité = 0, archiver la ligne
                if new_quantity == 0:
                    portfolio_line.unlink()

    def _create_cash_move(self, move):
        """Créer le mouvement de cash associé"""
        fund_cash = self.env['efund.fund.cash'].search([
            ('fund_id', '=', move.fund_id.id)
        ], limit=1)

        if not fund_cash:
            raise UserError(_("Aucun compte de trésorerie trouvé pour ce fonds"))

        cash_move_type = 'investment_out' if move.direction == 'buy' else 'divestment_in'

        cash_move = self.env['efund.fund.cash.move'].create({
            'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
            'fund_cash_id': fund_cash.id,
            'date': move.settlement_date,
            'amount': move.net_amount,
            'move_type': cash_move_type,
            'liquidity_type': 'liquid',
            'state': 'posted',
            'fund_id': move.fund_id.id,
            'partner_id': move.counterparty_id.id,
            'asset_move_id': move.id,  # Nouveau champ à ajouter dans efund.fund.cash.move
        })

        return cash_move

    def _create_accounting_entry(self, move):
        """Créer l'écriture comptable"""
        # Cette méthode dépendrait de votre plan comptable
        # Voici un exemple simplifié
        journal = self.env['account.journal'].search([
            ('type', '=', 'general'),
            ('company_id', '=', move.fund_id.company_id.id),
        ], limit=1)

        account_move = self.env['account.move'].create({
            'journal_id': journal.id,
            'date': move.trade_date,
            'ref': move.name,
            'line_ids': [
                # Lignes d'écriture selon le plan comptable
                # À adapter selon vos besoins
            ],
        })

        account_move.action_post()
        return account_move