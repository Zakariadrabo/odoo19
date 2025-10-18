from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Champs de base
    est_societe_gestion = fields.Boolean(string='Est une société de gestion', default=False)
    est_fonds = fields.Boolean(string='Est un fonds', default=True)
    code_isin = fields.Char(string='Code ISIN', size=12)
    code_fonds = fields.Char(string='Code interne du fonds')
    societe_gestion_id = fields.Many2one(
        'res.company',
        string='Société de gestion responsable',
        domain=[('est_societe_gestion', '=', True)]
    )
    type_fond_id = fields.Many2one(
        'efund.type.fonds',
        string='Type de fond',
        domain=[('est_fonds', '=', True)]
    )
    forme_juridique_id = fields.Many2one(
        'efund.forme.juridique',
        string='Forme  juridique',
    )