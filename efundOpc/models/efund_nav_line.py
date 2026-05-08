from odoo import models, fields, api, _

class EfundNavLine(models.Model):
    _name = 'efund.nav.line'
    _description = "Ligne d'inventaire VL"

    session_id = fields.Many2one('efund.nav.session', ondelete='cascade')
    name = fields.Char(string="Libellé", )
    type = fields.Selection([('asset', 'Actif'),('liability', 'Passif')], string="Type", )
    date = fields.Date(string="Date", )
    quantity = fields.Float(string="Quantité", )
    price_acquisition = fields.Float(string="Prix acquisition", )
    price = fields.Float(string="Prix", )
    price_diff = fields.Float(string="Différence de prix",compute="_compute_price_diff",store=True )
    interest = fields.Float(string="Intérêt", )
    total_amount = fields.Monetary(string="Valeur")
    currency_id = fields.Many2one(related='session_id.currency_id')

    @api.depends('price_acquisition','price','quantity')
    def _compute_price_diff(self):
        for line in self:
            line.price_diff = (line.price - line.price_acquisition) * line.quantity