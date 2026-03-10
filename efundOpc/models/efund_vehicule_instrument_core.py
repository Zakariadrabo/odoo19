from odoo import models, fields, api, _

class FundInstrument(models.Model):
    _name = "efund.vehicule.instrument.core"
    _description = "Instrument Financier - Core"


    # Identification
    name = fields.Char(required=True, string='Nom instrument')
    isin = fields.Char(index=True,string="Code ISIN")
    instrument_type = fields.Selection([('equity', 'Action'), ('bond', 'Obligation'),('dat', 'DAT'), ('tcn', 'TCN'), ('opcvm', 'OPCVM'),], required=True)
    currency_id = fields.Many2one('res.currency')
    issuer_id = fields.Many2one('efund.instrument.issuer', string="Émetteur")
    asset_class_id = fields.Many2one('efund.asset.class', required=True, string="Classe d'actif")
    state = fields.Selection([('draft', 'Draft'), ('active', 'Active'), ('suspended', 'Suspended'), ('liquidated', 'Liquidated'), ],
        string='Status', default='draft')

    # Prise en compte des prix
    price_source = fields.Selection([('external', 'Externe'), ('internal', 'Interne'), ], string="Source des prix")
    last_validated_price = fields.Float(string="Dernier cours validé")
    last_price_date = fields.Date(string="Date dernier cours")
    is_listed = fields.Boolean(string='Est Coté', default=False)
    valuation_method = fields.Selection([('market', 'Au marché'), ('listed', 'Cours Lissé')], string="Valorisation")
    #valuation_type = fields.Selection([('actuarial', 'Actuarielle'), ('linear', 'Linéaire')])

    # Relations techniques
    position_ids = fields.One2many('efund.vehicule.position','instrument_id',string='Positions')
    instrument_fee_ids = fields.One2many('efund.vehicule.instrument.fee.rule', 'instrument_id', string="Frais",help="Frais sur cet instrument")
    orders_ids = fields.One2many('efund.investment.order', 'instrument_id', string="Commandes")
    instrument_price_ids = fields.One2many('efund.vehicule.instrument.core.price', 'instrument_id', string="Prix")

    @api.depends('instrument_price_ids')
    def _compute_last_validated_price(self):
        for instrument in self:
            last_price = instrument.instrument_price_ids.filtered(
                lambda p: p.is_validated
            ).sorted('date', reverse=True)

            if last_price:
                instrument.last_validated_price = last_price[0].price
                instrument.last_price_date = last_price[0].date
            else:
                instrument.last_validated_price = 0.0
                instrument.last_price_date = False







