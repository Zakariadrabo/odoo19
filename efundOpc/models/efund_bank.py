from odoo import models, fields

class FundBank(models.Model):
    _name = "efund.bank"
    _description = "Dépositaire du fond"
    _order = "name"

    name = fields.Char(string="Nom", required=True,)
    sigle = fields.Char(string="Code")
    country_id = fields.Many2one("res.country", string="Pays")
    state = fields.Selection([('draft', 'Draft'), ('validated', 'Validé'), ('archived', 'Archivé'),], default='draft')

    # ---------------------------------------------------------------------
    # ACTIONS
    # ---------------------------------------------------------------------
    def action_validate(self):
        for rec in self:
            rec.state = 'validated'

    def action_archived(self):
        for rec in self:
            rec.state = 'archived'
