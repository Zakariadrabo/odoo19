from odoo import models, fields

class FundDepositaire(models.Model):
    _name = "efund.depositaire"
    _description = "Dépositaire du fond"
    _order = "name"

    name = fields.Char("Dépositaire du fond", required=True)
    sigle = fields.Char("Sigle du fond")
    forme_juridique = fields.Selection([
        ('sa', 'Société anonyme'),
        ('sas','Société anonyme simplifiée'),
        ('sarl', 'Société à responsabilité limitée'),
    ], default='sa', string='forme juridique')
    country_id = fields.Many2one("res.country", string="Pays")
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
