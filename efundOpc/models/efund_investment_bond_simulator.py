from odoo import models, fields

class BondSimulator(models.Model):
    _name = "efund.investment.bond.simulator"
    _description = "Simulateur de bond d'investissement"

    name = fields.Char(string="Nom du simulateur", required=True)
    price_date = fields.Date(string="Date du prix")
    price = fields.Float(string="Prix du bond", digits=(10, 2))
    start_date = fields.Date(string="Date de début")
    end_date = fields.Date(string="Date de fin")
    bond_id = fields.Many2one('efund.vehicule.instrument.core.bond', required=True)

