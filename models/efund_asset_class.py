from odoo import models, fields


class EfundAssetClass(models.Model):
    _name = 'efund.asset.class'
    _description = "Classe d'actif"
    _order = 'sequence, name'

    name = fields.Char(string="Classe d'actif",required=True)
    code = fields.Char(string="Code",required=True)
    description = fields.Text()
    sequence = fields.Integer(default=10)
    state = fields.Selection([('draft', 'Draft'),('validated', 'Validé'), ('archived', 'Archivé'),], default='draft')

    # Pour la réglementation / reporting
    regulatory_category = fields.Selection([
        ('equity', 'Actions'),
        ('bond', 'Obligations'),
        ('opcvm', 'OPCVM'),
        ('cash', 'Liquidités'),
        ('other', 'Autres actifs'),
    ], required=True, string='Catégorie réglementaire')

    def action_validate(self):
        self.write({'state': 'validated'})

    def action_archived(self):
        self.write({'state': 'archived'})
