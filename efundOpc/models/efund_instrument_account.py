from odoo import models, fields, api, _

class EfundInstrumentAccount(models.Model):
    _name = 'efund.instrument.account'
    _description = 'Liaison Instrument - Compte par Société'

    instrument_id = fields.Many2one('efund.vehicule.instrument.core', required=True)
    company_id = fields.Many2one('res.company', required=True)
    account_id = fields.Many2one('account.account', string="Compte Titre (211xxx)")
    usage_type = fields.Selection([
        ('balance', 'Bilan (Valeur)'),
        ('off_balance', 'Hors-Bilan (Quantité)')
    ], string="Usage du compte", default='balance')

    _sql_constraints = models.Constraint([
        ('uniq_inst_comp', 'unique(instrument_id, company_id)', 'Un compte existe déjà pour cet instrument dans cette société.')])