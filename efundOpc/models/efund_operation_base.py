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
        ('cancelled', 'Annulé'),
    ], default='draft', tracking=True)

    fund_id = fields.Many2one('efund.fund', required=True, string="Fonds", index=True)
    investor_id = fields.Many2one('efund.investor', required=True, string="Investisseur", index=True)
    company_id = fields.Many2one('res.company',related='fund_id.company_id',store=True)

    def action_submit(self):
        self.write({'state': 'submitted'})

    def action_validate(self):
        self.write({'state': 'validated'})

    def action_execute(self):
        raise NotImplementedError("À implémenter dans les modèles enfants")
