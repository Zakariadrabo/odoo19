# fichier : efund_asset_trading_service.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import logging

_logger = logging.getLogger(__name__)


class EfundAssetTradingService(models.Model):
    _name = 'efund.asset.trading.service'
    _description = 'Service de Trading d\'Actifs'

    @api.model
    def execute_purchase_order(self, fund_id, asset_id, quantity, price, broker_id=None):
        """
        Exécuter un ordre d'achat

        Args:
            fund_id (int): ID du fonds
            asset_id (int): ID de l'actif
            quantity (float): Quantité à acheter
            price (float): Prix d'achat
            broker_id (int, optional): ID du courtier

        Returns:
            dict: Résultat de l'opération
        """
        try:
            fund = self.env['efund.fund'].browse(fund_id)
            asset = self.env['efund.asset'].browse(asset_id)

            # 1. Vérifier la liquidité du fonds
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            total_cost = quantity * price
            if fund_cash.available_balance < total_cost:
                raise UserError(_("Liquidité insuffisante pour cet achat"))

            # 2. Vérifier les limites d'investissement
            self._check_investment_limits(fund_id, asset_id, total_cost)

            # 3. Créer le mouvement d'actif
            portfolio = self.env['efund.fund.portfolio'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            asset_move = self.env['efund.fund.asset.move'].create({
                'fund_id': fund_id,
                'portfolio_id': portfolio.id,
                'move_type': 'purchase',
                'asset_id': asset_id,
                'trade_date': fields.Date.today(),
                'settlement_date': self._calculate_settlement_date(asset.asset_type),
                'quantity': quantity,
                'price': price,
                'broker_id': broker_id,
                'counterparty_id': broker_id,  # Ou autre contrepartie
            })

            # 4. Exécuter la transaction
            asset_move.action_confirm()
            asset_move.action_execute()

            _logger.info(f"Achat exécuté: {quantity} x {asset.isin} pour {total_cost}")

            return {
                'success': True,
                'message': _("Achat exécuté avec succès"),
                'asset_move_id': asset_move.id,
                'cash_move_id': asset_move.cash_move_id.id,
                'quantity': quantity,
                'total_amount': total_cost,
            }

        except Exception as e:
            _logger.error(f"Erreur exécution achat: {str(e)}")
            raise UserError(_(f"Erreur lors de l'achat: {str(e)}"))

    @api.model
    def execute_sale_order(self, fund_id, asset_id, quantity, price=None, broker_id=None):
        """
        Exécuter un ordre de vente

        Args:
            fund_id (int): ID du fonds
            asset_id (int): ID de l'actif
            quantity (float): Quantité à vendre
            price (float, optional): Prix de vente (si None, prix marché)
            broker_id (int, optional): ID du courtier

        Returns:
            dict: Résultat de l'opération
        """
        try:
            fund = self.env['efund.fund'].browse(fund_id)
            asset = self.env['efund.asset'].browse(asset_id)

            # Vérifier la position existante
            portfolio = self.env['efund.fund.portfolio'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            portfolio_line = self.env['efund.fund.portfolio.line'].search([
                ('portfolio_id', '=', portfolio.id),
                ('asset_id', '=', asset_id),
            ], limit=1)

            if not portfolio_line or portfolio_line.quantity < quantity:
                raise UserError(_("Position insuffisante pour cette vente"))

            # Utiliser le prix marché si non spécifié
            if price is None:
                price = asset.last_price or portfolio_line.current_price

            # Créer le mouvement d'actif
            asset_move = self.env['efund.fund.asset.move'].create({
                'fund_id': fund_id,
                'portfolio_id': portfolio.id,
                'move_type': 'sale',
                'asset_id': asset_id,
                'trade_date': fields.Date.today(),
                'settlement_date': self._calculate_settlement_date(asset.asset_type),
                'quantity': quantity,
                'price': price,
                'broker_id': broker_id,
            })

            # Exécuter la transaction
            asset_move.action_confirm()
            asset_move.action_execute()

            # Calculer le P&L
            cost_of_sale = (quantity / portfolio_line.quantity) * portfolio_line.cost_value
            sale_amount = quantity * price
            pnl = sale_amount - cost_of_sale

            _logger.info(f"Vente exécutée: {quantity} x {asset.isin} - P&L: {pnl}")

            return {
                'success': True,
                'message': _("Vente exécutée avec succès"),
                'asset_move_id': asset_move.id,
                'cash_move_id': asset_move.cash_move_id.id,
                'quantity': quantity,
                'sale_amount': sale_amount,
                'pnl': pnl,
            }

        except Exception as e:
            _logger.error(f"Erreur exécution vente: {str(e)}")
            raise UserError(_(f"Erreur lors de la vente: {str(e)}"))

    @api.model
    def _check_investment_limits(self, fund_id, asset_id, amount):
        """Vérifier les limites d'investissement"""
        # 1. Limite par actif (max 10% du fonds par exemple)
        fund = self.env['efund.fund'].browse(fund_id)
        portfolio = self.env['efund.fund.portfolio'].search([
            ('fund_id', '=', fund_id)
        ], limit=1)

        if portfolio.total_value > 0:
            current_position = 0
            line = self.env['efund.fund.portfolio.line'].search([
                ('portfolio_id', '=', portfolio.id),
                ('asset_id', '=', asset_id),
            ], limit=1)

            if line:
                current_position = line.current_value

            new_position = current_position + amount
            percentage = (new_position / portfolio.total_value) * 100

            # Limite configurable (à mettre dans efund.fund)
            if percentage > 10:  # 10% max par actif
                raise UserError(_(
                    f"L'investissement dans cet actif dépasserait {percentage:.1f}% du fonds "
                    f"(limite: 10%)"
                ))

        # 2. Limite par secteur/classe d'actif
        # ... logique similaire

        return True

    @api.model
    def _calculate_settlement_date(self, asset_type, trade_date=None):
        """Calculer la date de règlement selon le type d'actif"""
        if trade_date is None:
            trade_date = fields.Date.today()

        # Règles de règlement standard (T+...)
        settlement_rules = {
            'equity': 2,  # T+2 pour les actions
            'bond': 2,  # T+2 pour les obligations
            'fund': 1,  # T+1 pour les fonds
            'etf': 2,  # T+2 pour les ETF
            'money_market': 0,  # T+0 pour le marché monétaire
            'derivative': 1,  # T+1 pour les dérivés
            'other': 2,  # T+2 par défaut
        }

        days_to_add = settlement_rules.get(asset_type, 2)

        # Calcul simple (dans la réalité, il faudrait tenir compte des jours ouvrés)
        from datetime import timedelta
        return trade_date + timedelta(days=days_to_add)

    @api.model
    def process_corporate_action(self, fund_id, asset_id, action_type, details):
        """
        Traiter une action corporate (division, fusion, dividendes, etc.)

        Args:
            fund_id (int): ID du fonds
            asset_id (int): ID de l'actif
            action_type (str): Type d'action
            details (dict): Détails spécifiques
        """
        try:
            portfolio = self.env['efund.fund.portfolio'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            portfolio_line = self.env['efund.fund.portfolio.line'].search([
                ('portfolio_id', '=', portfolio.id),
                ('asset_id', '=', asset_id),
            ], limit=1)

            if not portfolio_line:
                return

            if action_type == 'stock_split':
                # Ex: division 1:2
                ratio = details.get('ratio', 2)
                new_quantity = portfolio_line.quantity * ratio
                new_avg_cost = portfolio_line.cost_value / new_quantity

                portfolio_line.write({
                    'quantity': new_quantity,
                    'average_cost': new_avg_cost,
                })

                # Créer un mouvement pour tracer l'action
                self.env['efund.fund.asset.move'].create({
                    'fund_id': fund_id,
                    'portfolio_id': portfolio.id,
                    'move_type': 'corporate_action',
                    'asset_id': asset_id,
                    'trade_date': fields.Date.today(),
                    'quantity': new_quantity - portfolio_line.quantity,
                    'price': 0,  # Pas de flux de cash
                    'state': 'executed',
                })

            elif action_type == 'dividend':
                # Dividende en cash
                amount_per_share = details.get('amount_per_share', 0)
                total_dividend = portfolio_line.quantity * amount_per_share

                # Créer un mouvement de cash
                fund_cash = self.env['efund.fund.cash'].search([
                    ('fund_id', '=', fund_id)
                ], limit=1)

                if fund_cash:
                    self.env['efund.fund.cash.move'].create({
                        'fund_cash_id': fund_cash.id,
                        'date': fields.Date.today(),
                        'amount': total_dividend,
                        'move_type': 'dividend_in',
                        'state': 'posted',
                    })

            _logger.info(f"Action corporate traitée: {action_type} sur {asset_id}")

        except Exception as e:
            _logger.error(f"Erreur traitement action corporate: {str(e)}")
            raise