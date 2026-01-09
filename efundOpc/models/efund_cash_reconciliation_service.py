from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from contextlib import contextmanager
import json
import logging
import traceback
from datetime import datetime

_logger = logging.getLogger(__name__)


class EfundCashReconciliationService(models.Model):
    _name = 'efund.cash.reconciliation.service'
    _description = 'Service de Réconciliation Cash Investisseur/Fonds'

    @api.model
    @contextmanager
    def reconciliation_logging(self, operation_type, source_record=None, deposit_id=None,withdraw_id=None,subscription_id=None,redemption_id=None):
        """
        Context manager pour logger les opérations de réconciliation

        Usage:
        with self.reconciliation_logging('deposit', deposit_record) as log:
            # Votre code de réconciliation
            log.add_info("Message d'info")
            log.add_warning("Message d'avertissement")
            log.add_created_record('efund.account.cash.move', move_id)
        """
        # Créer le log
        log_record = self.env['efund.operation.reconciliation.log'].create({
            'operation_type': operation_type,
            'state': 'pending',
            'start_date': fields.Datetime.now(),
            'user_id': self.env.user.id,
            'deposit_id': deposit_id,
            'withdraw_id': withdraw_id,
            'subscription_id': subscription_id,
            'redemption_id': redemption_id,
        })

        # Lier au record source si fourni
        if source_record:
            model_field = f"{source_record._name.replace('.', '_')}_id"
            if hasattr(log_record, model_field):
                log_record.write({model_field: source_record.id})

        # Initialiser les structures de données
        log_data = {
            'info': [],
            'warnings': [],
            'errors': [],
            'created': {},
            'updated': {},
            'deleted': {},
        }

        class ReconciliationLogger:
            def __init__(self, log_record, log_data):
                self.log_record = log_record  # L'enregistrement réel dans la BD
                self.log_data = log_data

            def add_info(self, message, data=None):
                log_data['info'].append({
                    'timestamp': fields.Datetime.now(),
                    'message': message,
                    'data': data,
                })
                _logger.info(f"[Reconciliation {log_record.id}] {message}")

            def add_warning(self, message, data=None):
                log_data['warnings'].append({
                    'timestamp': fields.Datetime.now(),
                    'message': message,
                    'data': data,
                })
                _logger.warning(f"[Reconciliation {log_record.id}] {message}")

            def add_error(self, message, data=None):
                log_data['errors'].append({
                    'timestamp': fields.Datetime.now(),
                    'message': message,
                    'data': data,
                })
                _logger.error(f"[Reconciliation {log_record.id}] {message}")

            def add_created_record(self, model, record_id, details=None):
                if model not in log_data['created']:
                    log_data['created'][model] = []
                log_data['created'][model].append({
                    'id': record_id,
                    'timestamp': fields.Datetime.now(),
                    'details': details,
                })

            def add_updated_record(self, model, record_id, changes=None):
                if model not in log_data['updated']:
                    log_data['updated'][model] = []
                log_data['updated'][model].append({
                    'id': record_id,
                    'timestamp': fields.Datetime.now(),
                    'changes': changes,
                })

            def add_deleted_record(self, model, record_id, details=None):
                if model not in log_data['deleted']:
                    log_data['deleted'][model] = []
                log_data['deleted'][model].append({
                    'id': record_id,
                    'timestamp': fields.Datetime.now(),
                    'details': details,
                })

        logger = ReconciliationLogger(log_record, log_data)

        try:
            yield logger

            # Succès
            log_record.write({
                'state': 'success',
                'end_date': fields.Datetime.now(),
                'info_messages': json.dumps(log_data['info'], default=str, indent=2),
                'warning_messages': json.dumps(log_data['warnings'], default=str, indent=2),
                'error_messages': json.dumps(log_data['errors'], default=str, indent=2),
                'created_records': json.dumps(log_data['created'], default=str, indent=2),
                'updated_records': json.dumps(log_data['updated'], default=str, indent=2),
                'deleted_records': json.dumps(log_data['deleted'], default=str, indent=2),
                'records_created': sum(len(ids) for ids in log_data['created'].values()),
                'records_updated': sum(len(ids) for ids in log_data['updated'].values()),
                'records_deleted': sum(len(ids) for ids in log_data['deleted'].values()),
            })

        except Exception as e:
            # Échec
            error_traceback = traceback.format_exc()
            logger.add_error(f"Erreur: {str(e)}")

            log_record.write({
                'state': 'failed',
                'end_date': fields.Datetime.now(),
                'error_messages': json.dumps(log_data['errors'], default=str, indent=2),
                'traceback': error_traceback,
                'info_messages': json.dumps(log_data['info'], default=str, indent=2),
                'warning_messages': json.dumps(log_data['warnings'], default=str, indent=2),
            })

            raise

    # Ce modèle sert de conteneur pour les méthodes de service
    # Il n'a pas de vue ou d'enregistrements, seulement des méthodes statiques

    @api.model
    def reconcile_investor_deposit_with_logging(self, deposit_data, user_id=None):
        """
        Réconcilier un dépôt avec logging complet
        """
        # Démarrer le logging
        with self.reconciliation_logging('deposit', deposit_data,deposit_data.id) as logger:
            logger.add_info(f"Début réconciliation dépôt: {deposit_data.name}")

            # 1. Vérifier si le compte cash du fonds existe
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', deposit_data.fund_id.id)
            ], limit=1)

            if not fund_cash:
                # Créer automatiquement le compte cash du fonds s'il n'existe pas
                logger.add_info("Création du compte cash du fonds (inexistant)")
                fund_cash = self.env['efund.fund.cash'].create({
                    'name': f"Trésorerie - {deposit_data.fund_id.name}",
                    'fund_id': deposit_data.fund_id.id,
                    'company_id': deposit_data.fund_id.company_id.id,
                })
                logger.add_created_record('efund.fund.cash', fund_cash.id, {
                    'name': fund_cash.name,
                    'fund': deposit_data.fund_id.name,
                })

            # 2. Créer le mouvement cash investisseur
            investor_move_vals = {
                'cash_account_id': deposit_data.cash_account_id.id,
                'move_type': 'deposit',
                'amount': deposit_data.amount,
            }
            investor_move = self.env['efund.investor.cash.move'].create(investor_move_vals)
            logger.add_created_record('efund.investor.cash.move', investor_move.id, {
                'reference': investor_move.name or str(investor_move.id),
                'amount': deposit_data.amount,
                'investor': deposit_data.investor_id.name,
            })

            # 3. Créer le mouvement cash fonds
            fund_move_vals = {
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'amount': deposit_data.amount,
                'move_type': 'deposit_in',
                'liquidity_type': 'liquid',
                'state': 'posted',
                'investor_cash_move_id': investor_move.id,
                'investor_id': deposit_data.investor_id.id if deposit_data.investor_id else False,
                'fund_id': deposit_data.fund_id.id,
            }

            fund_move = self.env['efund.fund.cash.move'].create(fund_move_vals)
            logger.add_created_record('efund.fund.cash.move', fund_move.id, {
                'reference': fund_move.name,
                'amount': deposit_data.amount,
                'fund': deposit_data.fund_id.name,
            })

            # 4. Mettre à jour la référence croisée
            investor_move.write({'fund_cash_move_id': fund_move.id})
            logger.add_updated_record('efund.investor.cash.move', investor_move.id, {
                'field': 'fund_cash_move_id',
                'old_value': None,
                'new_value': fund_move.id,
            })

            # 5. Mettre à jour les balances (via compute fields)
            # Les champs compute se mettront à jour automatiquement

            logger.add_info(f"Réconciliation terminée avec succès. Montant: {deposit_data.amount}")

            return {
                'success': True,
                #'log_id': logger.get_log_id(),  # ID du log créé
                'investor_cash_move_id': investor_move.id,
                'fund_cash_move_id': fund_move.id,
                'investor_move_ref': investor_move.name or str(investor_move.id),
                'fund_move_ref': fund_move.name,
            }

    @api.model
    def reconcile_investor_withdrawal_with_logging(self, withdrawal_data, user_id=None):
        with self.reconciliation_logging('withdrawal', withdrawal_data,None,withdrawal_data.id) as logger:
            logger.add_info(f"Début réconciliation de retrait: {withdrawal_data.name}")

            # 1- Vérifier le solde de l'investisseur
            investor_cash_account = withdrawal_data.cash_account_id
            if investor_cash_account.balance < withdrawal_data.amount:
                raise UserError(_(
                    "Solde insuffisant pour ce retrait. "
                    f"Solde disponible: {investor_cash_account.balance}, "
                    f"Montant demandé: {withdrawal_data.amount}"
                ))

            # Vérifier la liquidité du fonds
            fund_cash = self.env['efund.fund.cash'].search([
                ('fund_id', '=', investor_cash_account.fund_id.id)
            ], limit=1)

            if not fund_cash:
                raise UserError(_("Aucun compte de trésorerie trouvé pour ce fonds"))

            if fund_cash.balance < withdrawal_data.amount:
                logger.add_warning("Liquidité insuffisante dans le fonds, vente d'actifs nécessaire")

            # 2. Créer le mouvement cash investisseur
            investor_move = self.env['efund.investor.cash.move'].create({
                'cash_account_id': investor_cash_account.id,
                'move_type': 'withdraw',
                'amount': withdrawal_data.amount,
            })
            logger.add_created_record('efund.investor.cash.move', investor_move.id, {
                'reference': investor_move.name or str(investor_move.id),
                'amount': withdrawal_data.amount,
                'investor': withdrawal_data.investor_id.name,
                'type': 'withdraw',
            })


            # 3. Créer le mouvement cash fonds
            fund_move = self.env['efund.fund.cash.move'].create({
                'name': self.env['ir.sequence'].next_by_code('efund.fund.cash.move'),
                'fund_cash_id': fund_cash.id,
                'date':  fields.Date.today(),
                'amount': withdrawal_data.amount,
                'move_type': 'withdraw_out',
                'liquidity_type': 'liquid',
                'state': 'posted',
                'investor_cash_move_id': investor_move.id,
                'investor_id': withdrawal_data.investor_id.id if withdrawal_data.investor_id else False,
                'fund_id': investor_cash_account.fund_id.id,
            })
            _logger.info(f"********* fund_move (fund cash move) = {fund_move}")
            logger.add_created_record('efund.fund.cash.move', fund_move.id, {
                'reference': fund_move.name,
                'amount': withdrawal_data.amount,
                'fund': withdrawal_data.fund_id.name,
            })

            # 4. Mettre à jour la référence croisée
            investor_move.write({'fund_cash_move_id': fund_move.id})
            logger.add_updated_record('efund.investor.cash.move', investor_move.id, {
                'field': 'fund_cash_move_id',
                'old_value': None,
                'new_value': fund_move.id,
            })

            # 5. Mettre à jour l'état du retrait
            withdrawal_data.write({
                'investor_cash_move_id': investor_move.id,
                'fund_cash_move_id': fund_move.id,
            })

            return {
                'success': True,
                #'log_id': log_record.id,
                'investor_cash_move_id': investor_move.id,
                'fund_cash_move_id': fund_move.id,
                'investor_move_ref': investor_move.name or str(investor_move.id),
                'fund_move_ref': fund_move.name,
                'amount': withdrawal_data.amount,
            }

