from odoo import models, fields, api, _

class FundInstrumentOpcvm(models.Model):
    _name = "efund.fund.instrument.core.opcvm"
    _description = "Instrument - OPCVM"
    _inherits = {'efund.fund.instrument.core': 'instrument_id'}

    instrument_id = fields.Many2one('efund.fund.instrument.core', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related='instrument_id.currency_id')

    # CHAMPS SPÉCIFIQUES DAT
    dat_principal = fields.Monetary(string="Montant du DAT")
    dat_interest_rate = fields.Float(string="Taux DAT (%)", digits=(16, 4))
    dat_start_date = fields.Date(string="Date de début DAT")
    dat_maturity_date = fields.Date(string="Date d'échéance DAT")

    def compute_dat_amortized_value(self, date):
        """Calcul spécifique des DAT"""
        pass