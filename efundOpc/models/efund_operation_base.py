from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class FundOperation(models.AbstractModel):
    _name = 'efund.operation.base'
    _description = 'Opération OPCVM (base)'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(readonly=True)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('submitted', 'Soumis'),
        ('validated', 'Validé'),
        ('executed', 'Exécuté'),
        ('accounted', 'Comptabilisé'),
        ('reconciled', 'Réconcilié'),
        ('cancelled', 'Annulé'),

    ], default='draft', tracking=True)

    vehicule_id = fields.Many2one('efund.vehicule', string="Véhicule", required=True, tracking=True)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", required=True, tracking=True)
    company_id = fields.Many2one('res.company',related='vehicule_id.company_id',store=True)

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_validate(self):
        self.write({'state': 'validated'})

    def action_execute(self):
        raise NotImplementedError("À implémenter dans les modèles enfants")
