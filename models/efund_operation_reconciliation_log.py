from odoo import models, fields, api, _
from odoo.exceptions import UserError
import json
import logging

_logger = logging.getLogger(__name__)


class EfundReconciliationLog(models.Model):
    _name = 'efund.operation.reconciliation.log'
    _description = 'Log de Réconciliation'
    _order = 'create_date desc'
    _rec_name = 'reference'

    # Identification
    reference = fields.Char(
        string="Référence",
        default=lambda self: self.env['ir.sequence'].next_by_code('efund.opration.reconciliation.log')
    )

    # Liens vers les objets sources
    deposit_id = fields.Many2one('efund.investor.deposit', string="Dépôt Source")
    subscription_id = fields.Many2one('efund.investor.subscription', string="Souscription Source")
    redemption_id = fields.Many2one('efund.investor.redemption', string="Rachat Source")
    withdraw_id = fields.Many2one('efund.investor.withdraw', string="Retrait Source")

    # Type d'opération
    operation_type = fields.Selection([
        ('deposit', 'Dépôt'),
        ('withdrawal', 'Retrait'),
        ('subscription', 'Souscription'),
        ('redemption', 'Rachat'),
        ('purchase', 'Achat Actif'),
        ('sale', 'Vente Actif'),
        ('corporate_action', 'Action Corporate'),
    ], string="Type d'Opération", required=True)

    # Statut
    state = fields.Selection([
        ('pending', 'En Cours'),
        ('success', 'Succès'),
        ('partial', 'Partiel'),
        ('failed', 'Échec'),
        ('warning', 'Avertissement'),
    ], string="Statut", default='pending')

    # Détails techniques
    user_id = fields.Many2one('res.users', string="Utilisateur", default=lambda self: self.env.user)
    start_date = fields.Datetime(string="Début", default=fields.Datetime.now)
    end_date = fields.Datetime(string="Fin")
    duration_seconds = fields.Float(string="Durée (secondes)", compute='_compute_duration')

    # Résultats
    created_records = fields.Text(string="Enregistrements Créés")  # JSON format
    updated_records = fields.Text(string="Enregistrements Modifiés")
    deleted_records = fields.Text(string="Enregistrements Supprimés")

    # Messages
    info_messages = fields.Text(string="Messages d'Information")
    warning_messages = fields.Text(string="Messages d'Avertissement")
    error_messages = fields.Text(string="Messages d'Erreur")

    # Métriques
    records_created = fields.Integer(string="Enregistrements Créés")
    records_updated = fields.Integer(string="Enregistrements Modifiés")
    records_deleted = fields.Integer(string="Enregistrements Supprimés")

    # Audit
    ip_address = fields.Char(string="Adresse IP")
    session_id = fields.Char(string="Session")
    traceback = fields.Text(string="Traceback d'Erreur")

    # Champs calculés
    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for log in self:
            if log.start_date and log.end_date:
                delta = log.end_date - log.start_date
                log.duration_seconds = delta.total_seconds()
            else:
                log.duration_seconds = 0.0

    def action_view_related_records(self):
        """Ouvrir les enregistrements liés"""
        self.ensure_one()

        # Récupérer les IDs depuis le JSON
        try:
            created_data = json.loads(self.created_records or '{}')
            model = created_data.get('model')
            record_ids = created_data.get('ids', [])

            if model and record_ids:
                return {
                    'type': 'ir.actions.act_window',
                    'name': _("Enregistrements Créés"),
                    'res_model': model,
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', record_ids)],
                }
        except:
            pass

        return {'type': 'ir.actions.act_window_close'}