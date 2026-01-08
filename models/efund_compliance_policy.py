from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundCompliancePolicy(models.Model):
    _name = "efund.compliance.policy"
    _description = "Compliance and Risk Policies"

    company_id = fields.Many2one('efund.management.company', required=True, ondelete='cascade')
    name = fields.Char(required=True, string="Policy Title")
    policy_type = fields.Selection([
        ('risk', 'Gestion des Risques'),
        ('aml', 'Lutte contre le blanchiment'),
        ('compliance', 'Conformité Générale'),
        ('other', 'Autre'),
    ], string="Policy Type", required=True)
    description = fields.Text(string="Description")
    document_id = fields.Many2one('ir.attachment', string="Document attaché")
    effective_date = fields.Date(string="Date d’application")
    next_review_date = fields.Date(string="Prochaine révision")
    status = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validée'),
        ('expired', 'Expirée')
    ], default='draft', string="Statut")
    responsible_id = fields.Many2one('res.users', string="Responsable")
