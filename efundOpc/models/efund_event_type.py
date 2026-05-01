from odoo import models, fields

class FundDepositaire(models.Model):
    _name = "efund.event.type"
    _description = "Les types d'évènements"
    _order = "name"

    name = fields.Char("Nom du type", required=True)
    code = fields.Char("Code Type")
    state = fields.Selection([
        ('draft', 'Draft'),
        ('validated', 'Validé'),
        ('archived', 'Archivé'),
    ], default='draft')

    # ---------------------------------------------------------------------
    # ACTIONS
    # ---------------------------------------------------------------------
    def action_validate(self):
        for rec in self:
            rec.state = 'validated'

    def action_archived(self):
        for rec in self:
            rec.state = 'archived'
