from odoo import models, fields, api, _

class FundInstrument(models.Model):
    _name = "efund.fund.instrument.core"
    _description = "Instrument Financier - Core"


    # Identification
    name = fields.Char(required=True, string='Nom instrument')
    isin = fields.Char(index=True,string="Code ISIN")

    instrument_type = fields.Selection([('equity', 'Action'), ('bond', 'Obligation'),('dat', 'DAT'), ('tcn', 'TCN'), ('opcvm', 'OPCVM'),], required=True)
    currency_id = fields.Many2one('res.currency', required=True)
    issuer_id = fields.Many2one('efund.instrument.issuer')
    asset_class_id = fields.Many2one('efund.asset.class', required=True)

    #last_validated_price = fields.Float(compute='_compute_last_validated_price', string="Dernier cours validé",digits=(16, 4))
    #last_price_date = fields.Date(compute='_compute_last_validated_price', string="Date dernier cours")

    is_listed = fields.Boolean()
    #market = fields.Selection([...])
    #state = fields.Selection([...])
    #is_active = fields.Boolean(default=True)

    # Relations techniques
    #price_ids = fields.One2many(...)
    #position_ids = fields.One2many(...)

    # Liens vers satellites
    #equity_id = fields.One2one('efund.fund.instrument.equity')
    #bond_id = fields.One2many('efund.fund.instrument.core.bond','instrument_id')
    #dat_id = fields.One2one('efund.fund.instrument.dat')
    #tcn_id = fields.One2one('efund.fund.instrument.tcn')



