from odoo import models, fields

class FundDepositaire(models.Model):
    _name = "efund.depositaire"
    _description = "Dépositaire du fond"
    _order = "name"

    name = fields.Char("Raison Social", required=True)
    sigle = fields.Char("Sigle")
    forme_juridique = fields.Selection([
        ('sa', 'Société anonyme'),
        ('sas','Société anonyme simplifiée'),
        ('sarl', 'Société à responsabilité limitée'),
    ], default='sa', string='forme juridique')
    type_depositaire = fields.Selection([('sbt', 'Société de Bourse'), ('depositaire', 'Dépositaire')])
    country_id = fields.Many2one("res.country", string="Pays")
    account_cash = fields.Char(string="Compte espèces")
    account_part = fields.Char(string="Compte titre")
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
