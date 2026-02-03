from odoo import models, fields, api, _

class FundInstrumentOpcvm(models.Model):
    _name = "efund.vehicule.instrument.core.opcvm"
    _description = "Instrument - OPCVM"
    _inherits = {'efund.vehicule.instrument.core': 'instrument_id'}

    instrument_id = fields.Many2one('efund.vehicule.instrument.core', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='instrument_id.currency_id')

    opcvm_type = fields.Selection([('fcp', 'FCP (Fonds Commun de Placement)'), ('sicav', 'SICAV'), ], string="Nature juridique", required=True)
    classification_amf = fields.Selection([('monetary', 'Monétaire'), ('bond', 'Obligataire'),('equity', 'Actions'), ('diversified', 'Diversifié'),
    ], string="Classification", required=True)

    # Valorisation
    nav = fields.Float(string="Dernière VL", digits=(16, 6), help="Valeur Liquidative")
    nav_date = fields.Date(string="Date de la VL")

    # Paramètres de frais (spécifiques aux fonds)
    management_fee_rate = fields.Float(string="Frais de gestion annuels (%)")
    subscription_fee_rate = fields.Float(string="Frais de souscription max (%)")
    redemption_fee_rate = fields.Float(string="Frais de rachat max (%)")

    # Politique de dividende
    is_capitalization = fields.Boolean(
        string="Capitalisation",
        help="Si coché, les revenus sont réinvestis, sinon ils sont distribués."
    )



    def action_approve(self):
        for order in self:
            if order.state != 'draft':
                continue
            order.state = 'active'

    def action_archived(self):
        for order in self:
            if order.state != 'active':
                continue
            order.state = 'liquidated'