# fichier : efund_cash_reconciliation_service.py

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)


class EfundCashReconciliationService(models.Model):
    _name = 'efund.cash.reconciliation.service'
    _description = 'Service de Réconciliation Cash Investisseur/Fonds'

    # Ce modèle sert de conteneur pour les méthodes de service
    # Il n'a pas de vue ou d'enregistrements, seulement des méthodes statiques

    @api.model
    def reconcile_investor_deposit(self, investor_cash_move_id):
        """
        Réconcilier un dépôt d'investisseur avec le cash du fonds

        Args:
            investor_cash_move_id (int): ID du mouvement cash investisseur

        Returns:
            dict: Résultat de l'opération
        """
        try:
            investor_move = self.env['efund.investor.cash.move'].browse(investor_cash_move_id)

            if not investor_move:
                raise UserError(_("Mouvement investisseur introuvable"))

            if investor_move.move_type != 'deposit':
                raise UserError(_("Seuls les dépôts peuvent être réconciliés avec cette méthode"))

            # Trouver le compte cash du fonds
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', investor_move.fund_id.id)
            ], limit=1)

            if not fund_cash:
                # Créer automatiquement le compte cash du fonds s'il n'existe pas
                fund_cash = self.env['efund.fund.cash'].create({
                    'name': f"Trésorerie - {investor_move.fund_id.name}",
                    'fund_id': investor_move.fund_id.id,
                })

            # Créer le mouvement de cash du fonds
            fund_move = self.env['efund.fund.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'date': investor_move.date.date() if investor_move.date else fields.Date.today(),
                'amount': investor_move.amount,
                'move_type': 'deposit_in',
                'liquidity_type': 'liquid',
                'state': 'posted',
                'investor_cash_move_id': investor_move.id,
                'partner_id': investor_move.investor_id.partner_id.id if investor_move.investor_id.partner_id else False,
                'fund_id': investor_move.fund_id.id,
            })

            # Mettre à jour la référence croisée
            investor_move.write({
                'fund_cash_move_id': fund_move.id,
                'state': 'reconciled' if hasattr(investor_move, 'state') else False,
            })

            _logger.info(f"Dépôt réconcilié: Investisseur {investor_move.id} -> Fonds {fund_move.id}")

            return {
                'success': True,
                'message': _("Dépôt réconcilié avec succès"),
                'investor_move_id': investor_move.id,
                'fund_move_id': fund_move.id,
                'amount': investor_move.amount,
            }

        except Exception as e:
            _logger.error(f"Erreur réconciliation dépôt: {str(e)}")
            raise UserError(_(f"Erreur lors de la réconciliation: {str(e)}"))

    @api.model
    def reconcile_investor_withdrawal(self, investor_cash_move_id):
        """
        Réconcilier un retrait d'investisseur avec le cash du fonds

        Args:
            investor_cash_move_id (int): ID du mouvement cash investisseur

        Returns:
            dict: Résultat de l'opération
        """
        try:
            investor_move = self.env['efund.investor.cash.move'].browse(investor_cash_move_id)

            if not investor_move:
                raise UserError(_("Mouvement investisseur introuvable"))

            if investor_move.move_type != 'withdraw':
                raise UserError(_("Seuls les retraits peuvent être réconciliés avec cette méthode"))

            # Vérifier la liquidité du fonds
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', investor_move.fund_id.id)
            ], limit=1)

            if not fund_cash:
                raise UserError(_("Aucun compte de trésorerie trouvé pour ce fonds"))

            # Vérifier si le fonds a suffisamment de liquidité
            if fund_cash.available_balance < investor_move.amount:
                raise UserError(_("Fonds insuffisants dans la trésorerie du fonds pour ce retrait"))

            # Créer le mouvement de cash du fonds
            fund_move = self.env['efund.fund.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'date': investor_move.date.date() if investor_move.date else fields.Date.today(),
                'amount': investor_move.amount,
                'move_type': 'withdraw_out',
                'liquidity_type': 'liquid',
                'state': 'posted',
                'investor_cash_move_id': investor_move.id,
                'partner_id': investor_move.investor_id.partner_id.id if investor_move.investor_id.partner_id else False,
                'fund_id': investor_move.fund_id.id,
            })

            # Mettre à jour la référence croisée
            investor_move.write({
                'fund_cash_move_id': fund_move.id,
                'state': 'reconciled' if hasattr(investor_move, 'state') else False,
            })

            _logger.info(f"Retrait réconcilié: Investisseur {investor_move.id} -> Fonds {fund_move.id}")

            return {
                'success': True,
                'message': _("Retrait réconcilié avec succès"),
                'investor_move_id': investor_move.id,
                'fund_move_id': fund_move.id,
                'amount': investor_move.amount,
            }

        except Exception as e:
            _logger.error(f"Erreur réconciliation retrait: {str(e)}")
            raise UserError(_(f"Erreur lors de la réconciliation: {str(e)}"))

    @api.model
    def reconcile_subscription(self, subscription_order_id):
        """
        Réconcilier une souscription avec le cash du fonds et le portefeuille

        Args:
            subscription_order_id (int): ID de l'ordre de souscription

        Returns:
            dict: Résultat de l'opération
        """
        try:
            subscription = self.env['efund.subscription.order'].browse(subscription_order_id)

            if not subscription:
                raise UserError(_("Ordre de souscription introuvable"))

            if subscription.state != 'confirmed':
                raise UserError(_("L'ordre de souscription doit être confirmé"))

            # Trouver le compte cash du fonds
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', subscription.fund_id.id)
            ], limit=1)

            if not fund_cash:
                raise UserError(_("Aucun compte de trésorerie trouvé pour ce fonds"))

            # 1. Créer le mouvement de cash du fonds (entrée de cash)
            fund_cash_move = self.env['efund.fund.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'date': subscription.subscription_date,
                'amount': subscription.net_amount,
                'move_type': 'subscription_in',
                'liquidity_type': 'liquid',
                'state': 'posted',
                'subscription_id': subscription.id,
                'partner_id': subscription.investor_id.partner_id.id if subscription.investor_id.partner_id else False,
                'fund_id': subscription.fund_id.id,
            })

            # 2. Créer le mouvement de cash investisseur (sortie de cash)
            investor_cash_move = self.env['efund.investor.cash.move'].create({
                'cash_account_id': subscription.cash_account_id.id,
                'move_type': 'subscription_net',
                'amount': subscription.net_amount,
                'date': subscription.subscription_date,
                'fund_id': subscription.fund_id.id,
                'investor_id': subscription.investor_id.id,
            })

            # 3. Créer le mouvement de parts investisseur
            investor_part_move = self.env['efund.investor.part.move'].create({
                'part_account_id': subscription.part_account_id.id,
                'move_type': 'subscription',
                'parts': subscription.parts_allocated,
                'date': subscription.subscription_date,
                'fund_id': subscription.fund_id.id,
                'investor_id': subscription.investor_id.id,
            })

            # 4. Mettre à jour le portefeuille du fonds (si investissement immédiat)
            if subscription.investment_strategy == 'immediate':
                self._allocate_to_portfolio(subscription.fund_id.id, subscription.net_amount)

            # 5. Mettre à jour l'ordre de souscription
            subscription.write({
                'state': 'executed',
                'execution_date': fields.Date.today(),
                'fund_cash_move_id': fund_cash_move.id,
                'investor_cash_move_id': investor_cash_move.id,
                'investor_part_move_id': investor_part_move.id,
            })

            _logger.info(f"Souscription réconciliée: Ordre {subscription.id}, Montant: {subscription.net_amount}")

            return {
                'success': True,
                'message': _("Souscription réconciliée avec succès"),
                'subscription_id': subscription.id,
                'fund_cash_move_id': fund_cash_move.id,
                'investor_cash_move_id': investor_cash_move.id,
                'investor_part_move_id': investor_part_move.id,
            }

        except Exception as e:
            _logger.error(f"Erreur réconciliation souscription: {str(e)}")
            raise UserError(_(f"Erreur lors de la réconciliation de la souscription: {str(e)}"))

    @api.model
    def reconcile_redemption(self, redemption_order_id):
        """
        Réconcilier un rachat avec le cash du fonds et le portefeuille

        Args:
            redemption_order_id (int): ID de l'ordre de rachat

        Returns:
            dict: Résultat de l'opération
        """
        try:
            redemption = self.env['efund.redemption.order'].browse(redemption_order_id)

            if not redemption:
                raise UserError(_("Ordre de rachat introuvable"))

            if redemption.state != 'confirmed':
                raise UserError(_("L'ordre de rachat doit être confirmé"))

            # Vérifier la liquidité du fonds
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', redemption.fund_id.id)
            ], limit=1)

            if not fund_cash:
                raise UserError(_("Aucun compte de trésorerie trouvé pour ce fonds"))

            # Vérifier si le fonds a suffisamment de liquidité
            if fund_cash.available_balance < redemption.net_amount:
                # Si pas assez de liquidité, vendre des actifs du portefeuille
                self._liquidate_assets_for_redemption(redemption.fund_id.id, redemption.net_amount)

            # 1. Créer le mouvement de cash du fonds (sortie de cash)
            fund_cash_move = self.env['efund.fund.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'date': redemption.redemption_date,
                'amount': redemption.net_amount,
                'move_type': 'redemption_out',
                'liquidity_type': 'liquid',
                'state': 'posted',
                'redemption_id': redemption.id,
                'partner_id': redemption.investor_id.partner_id.id if redemption.investor_id.partner_id else False,
                'fund_id': redemption.fund_id.id,
            })

            # 2. Créer le mouvement de cash investisseur (entrée de cash)
            investor_cash_move = self.env['efund.investor.cash.move'].create({
                'cash_account_id': redemption.cash_account_id.id,
                'move_type': 'redemption_net',
                'amount': redemption.net_amount,
                'date': redemption.redemption_date,
                'fund_id': redemption.fund_id.id,
                'investor_id': redemption.investor_id.id,
            })

            # 3. Créer le mouvement de parts investisseur
            investor_part_move = self.env['efund.investor.part.move'].create({
                'part_account_id': redemption.part_account_id.id,
                'move_type': 'redemption',
                'parts': redemption.parts_redeemed,
                'date': redemption.redemption_date,
                'fund_id': redemption.fund_id.id,
                'investor_id': redemption.investor_id.id,
            })

            # 4. Mettre à jour l'ordre de rachat
            redemption.write({
                'state': 'executed',
                'execution_date': fields.Date.today(),
                'fund_cash_move_id': fund_cash_move.id,
                'investor_cash_move_id': investor_cash_move.id,
                'investor_part_move_id': investor_part_move.id,
            })

            _logger.info(f"Rachat réconcilié: Ordre {redemption.id}, Montant: {redemption.net_amount}")

            return {
                'success': True,
                'message': _("Rachat réconcilié avec succès"),
                'redemption_id': redemption.id,
                'fund_cash_move_id': fund_cash_move.id,
                'investor_cash_move_id': investor_cash_move.id,
                'investor_part_move_id': investor_part_move.id,
            }

        except Exception as e:
            _logger.error(f"Erreur réconciliation rachat: {str(e)}")
            raise UserError(_(f"Erreur lors de la réconciliation du rachat: {str(e)}"))

    @api.model
    def _allocate_to_portfolio(self, fund_id, amount):
        """
        Allouer des fonds au portefeuille d'actifs

        Args:
            fund_id (int): ID du fonds
            amount (float): Montant à allouer
        """
        try:
            # Récupérer le portefeuille du fonds
            portfolio = self.env['efund.fund.portfolio'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            if not portfolio:
                # Créer le portefeuille s'il n'existe pas
                portfolio = self.env['efund.fund.portfolio'].create({
                    'name': f"Portefeuille - {self.env['efund.fund'].browse(fund_id).name}",
                    'fund_id': fund_id,
                })

            # Pour l'instant, on alloue en cash
            # Dans une implémentation réelle, on utiliserait une stratégie d'investissement
            cash_line = portfolio.asset_line_ids.filtered(
                lambda l: l.asset_type == 'cash'
            )

            if cash_line:
                # Mettre à jour la ligne cash existante
                cash_line.write({
                    'quantity': cash_line.quantity + amount,
                    'current_price': 1.0,  # Le cash vaut toujours 1
                    'current_value': cash_line.current_value + amount,
                })
            else:
                # Créer une nouvelle ligne cash
                self.env['efund.fund.portfolio.line'].create({
                    'portfolio_id': portfolio.id,
                    'asset_type': 'cash',
                    'asset_name': 'Trésorerie',
                    'quantity': amount,
                    'average_cost': 1.0,
                    'current_price': 1.0,
                })

            _logger.info(f"Allocation portefeuille: Fonds {fund_id}, Montant: {amount}")

        except Exception as e:
            _logger.error(f"Erreur allocation portefeuille: {str(e)}")
            raise

    @api.model
    def _liquidate_assets_for_redemption(self, fund_id, amount_needed):
        """
        Liquider des actifs pour faire face à un rachat

        Args:
            fund_id (int): ID du fonds
            amount_needed (float): Montant nécessaire
        """
        try:
            # Récupérer le portefeuille du fonds
            portfolio = self.env['efund.fund.portfolio'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            if not portfolio:
                raise UserError(_("Aucun portefeuille trouvé pour ce fonds"))

            # Stratégie de liquidation simple: vendre d'abord le cash, puis les actifs les plus liquides
            total_liquidated = 0

            # 1. Vérifier le cash disponible dans le portefeuille
            cash_line = portfolio.asset_line_ids.filtered(
                lambda l: l.asset_type == 'cash'
            )

            if cash_line and cash_line.current_value > 0:
                cash_available = min(cash_line.current_value, amount_needed)
                if cash_available > 0:
                    # Réduire le cash
                    cash_line.write({
                        'quantity': cash_line.quantity - cash_available,
                        'current_value': cash_line.current_value - cash_available,
                    })
                    total_liquidated += cash_available

            # 2. Si besoin, liquider d'autres actifs (simplifié)
            if total_liquidated < amount_needed:
                # Dans une implémentation réelle, on aurait une logique plus sophistiquée
                # pour choisir quels actifs vendre en priorité
                _logger.warning(
                    f"Liquidation nécessaire au-delà du cash disponible: {amount_needed - total_liquidated}")
                # Pour l'exemple, on suppose qu'on peut toujours liquider
                total_liquidated = amount_needed

            # Créer un mouvement de désinvestissement
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            if fund_cash:
                self.env['efund.fund.cash.move'].create({
                    'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                    'fund_cash_id': fund_cash.id,
                    'date': fields.Date.today(),
                    'amount': total_liquidated,
                    'move_type': 'divestment_in',
                    'liquidity_type': 'liquid',
                    'state': 'posted',
                    'fund_id': fund_id,
                })

            _logger.info(f"Liquidation pour rachat: Fonds {fund_id}, Montant liquidé: {total_liquidated}")

            return total_liquidated

        except Exception as e:
            _logger.error(f"Erreur liquidation actifs: {str(e)}")
            raise UserError(_(f"Erreur lors de la liquidation des actifs: {str(e)}"))

    @api.model
    def get_fund_liquidity_status(self, fund_id):
        """
        Obtenir le statut de liquidité d'un fonds

        Args:
            fund_id (int): ID du fonds

        Returns:
            dict: Statut de liquidité
        """
        try:
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            if not fund_cash:
                return {
                    'available_balance': 0.0,
                    'current_balance': 0.0,
                    'liquidity_ratio': 0.0,
                    'status': 'no_cash_account',
                }

            # Calculer le ratio de liquidité (cash disponible / total actifs)
            portfolio = self.env['efund.fund.portfolio'].search([
                ('fund_id', '=', fund_id)
            ], limit=1)

            total_assets = portfolio.total_value if portfolio else 0.0
            liquidity_ratio = (fund_cash.available_balance / total_assets * 100) if total_assets > 0 else 0.0

            # Déterminer le statut
            if liquidity_ratio >= 10:
                status = 'high_liquidity'
            elif liquidity_ratio >= 5:
                status = 'medium_liquidity'
            elif liquidity_ratio >= 2:
                status = 'low_liquidity'
            else:
                status = 'critical_liquidity'

            return {
                'available_balance': fund_cash.available_balance,
                'current_balance': fund_cash.current_balance,
                'liquidity_ratio': liquidity_ratio,
                'status': status,
                'status_label': self._get_liquidity_status_label(status),
            }

        except Exception as e:
            _logger.error(f"Erreur statut liquidité: {str(e)}")
            return {
                'error': str(e),
                'status': 'error',
            }

    @api.model
    def _get_liquidity_status_label(self, status):
        """
        Obtenir le libellé du statut de liquidité

        Args:
            status (str): Code du statut

        Returns:
            str: Libellé traduit
        """
        status_labels = {
            'high_liquidity': _("Haute Liquidité"),
            'medium_liquidity': _("Liquidité Moyenne"),
            'low_liquidity': _("Faible Liquidité"),
            'critical_liquidity': _("Liquidité Critique"),
            'no_cash_account': _("Pas de Compte Cash"),
            'error': _("Erreur"),
        }
        return status_labels.get(status, _("Inconnu"))

    @api.model
    def reconcile_daily_operations(self, fund_id=None, date=None):
        """
        Réconcilier toutes les opérations d'une journée

        Args:
            fund_id (int, optional): ID du fonds (si None, tous les fonds)
            date (date, optional): Date à réconcilier (si None, aujourd'hui)

        Returns:
            dict: Résumé des réconciliations
        """
        try:
            if date is None:
                date = fields.Date.today()

            funds_domain = [('fund_id', '!=', False)]
            if fund_id:
                funds_domain.append(('fund_id', '=', fund_id))

            # Récupérer les mouvements investisseurs non réconciliés
            unreconciled_moves = self.env['efund.investor.cash.move'].search([
                ('date', '>=', date),
                ('date', '<', date + ' 1 day'),
                ('fund_cash_move_id', '=', False),
                ('move_type', 'in', ['deposit', 'withdraw']),
            ])

            results = {
                'date': date,
                'total_moves': len(unreconciled_moves),
                'successful': 0,
                'failed': 0,
                'details': [],
            }

            for move in unreconciled_moves:
                try:
                    if move.move_type == 'deposit':
                        result = self.reconcile_investor_deposit(move.id)
                    elif move.move_type == 'withdraw':
                        result = self.reconcile_investor_withdrawal(move.id)
                    else:
                        continue

                    results['successful'] += 1
                    results['details'].append({
                        'move_id': move.id,
                        'type': move.move_type,
                        'amount': move.amount,
                        'status': 'success',
                        'message': result.get('message', ''),
                    })

                except Exception as e:
                    results['failed'] += 1
                    results['details'].append({
                        'move_id': move.id,
                        'type': move.move_type,
                        'amount': move.amount,
                        'status': 'failed',
                        'message': str(e),
                    })

            _logger.info(f"Réconciliation quotidienne: {results['successful']} succès, {results['failed']} échecs")

            return results

        except Exception as e:
            _logger.error(f"Erreur réconciliation quotidienne: {str(e)}")
            raise

    @api.model
    def generate_reconciliation_report(self, start_date, end_date, fund_id=None):
        """
        Générer un rapport de réconciliation

        Args:
            start_date (date): Date de début
            end_date (date): Date de fin
            fund_id (int, optional): ID du fonds

        Returns:
            dict: Rapport de réconciliation
        """
        try:
            domain = [
                ('date', '>=', start_date),
                ('date', '<=', end_date),
            ]

            if fund_id:
                domain.append(('fund_id', '=', fund_id))

            # Mouvements investisseurs
            investor_moves = self.env['efund.investor.cash.move'].search(domain)

            # Mouvements fonds
            fund_moves = self.env['efund.fund.cash.move'].search(domain)

            # Calculer les totaux par type
            investor_totals = {}
            fund_totals = {}

            for move_type in ['deposit', 'withdraw', 'subscription_net', 'redemption_net']:
                moves = investor_moves.filtered(lambda m: m.move_type == move_type)
                investor_totals[move_type] = sum(moves.mapped('amount'))

            for move_type in ['deposit_in', 'withdraw_out', 'subscription_in', 'redemption_out']:
                moves = fund_moves.filtered(lambda m: m.move_type == move_type)
                fund_totals[move_type] = sum(moves.mapped('amount'))

            # Vérifier les correspondances
            matched_count = 0
            unmatched_count = 0

            for investor_move in investor_moves.filtered(lambda m: m.move_type in ['deposit', 'withdraw']):
                if investor_move.fund_cash_move_id:
                    matched_count += 1
                else:
                    unmatched_count += 1

            report = {
                'period': f"{start_date} - {end_date}",
                'investor_moves_count': len(investor_moves),
                'fund_moves_count': len(fund_moves),
                'matched_count': matched_count,
                'unmatched_count': unmatched_count,
                'match_rate': (matched_count / (matched_count + unmatched_count) * 100) if (
                                                                                                   matched_count + unmatched_count) > 0 else 0,
                'investor_totals': investor_totals,
                'fund_totals': fund_totals,
                'reconciliation_status': 'balanced' if abs(
                    investor_totals.get('deposit', 0) - fund_totals.get('deposit_in', 0) +
                    investor_totals.get('withdraw', 0) - fund_totals.get('withdraw_out', 0)
                ) < 0.01 else 'unbalanced',
            }

            return report

        except Exception as e:
            _logger.error(f"Erreur génération rapport: {str(e)}")
            raise

    """
    # Exemples d'utilisation

        # 1. Réconcilier un dépôt
        service = env['efund.cash.reconciliation.service']
        result = service.reconcile_investor_deposit(investor_cash_move_id)
        
        # 2. Réconcilier une souscription
        result = service.reconcile_subscription(subscription_order_id)
        
        # 3. Obtenir le statut de liquidité
        liquidity_status = service.get_fund_liquidity_status(fund_id)
        
        # 4. Réconcilier les opérations quotidiennes
        report = service.reconcile_daily_operations(fund_id, date)
        
        # 5. Générer un rapport
        report = service.generate_reconciliation_report(start_date, end_date, fund_id)
    """
