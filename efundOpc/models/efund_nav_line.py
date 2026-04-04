from odoo import models, fields, api, _

class EfundNavLine(models.Model):
    _name = 'efund.nav.line'
    _description = "Ligne d'inventaire VL"

    session_id = fields.Many2one('efund.nav.session', ondelete='cascade')
    name = fields.Char(string="Libellé", required=True)
    type = fields.Selection([
        ('asset', 'Actif'),
        ('liability', 'Passif')
    ], string="Type", required=True)
    amount = fields.Monetary(string="Valeur")
    currency_id = fields.Many2one(related='session_id.currency_id')