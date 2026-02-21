from odoo import api, fields, models, _
from datetime import datetime


class FundAccountingSchema(models.Model):
    _name = "efund.accounting.schema"
    _description = "Mapping comptable des fonds"

    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)

    event_type = fields.Selection(
        [('CASH_IN', 'Déposit'), ('CASH_OUT', 'Rétrait'), ('SUB_VALIDATED', 'Souscription Validée'),
         ('RED_VALIDATED', 'Rachat Validé'), ('TRADE_EXECUTED', 'Transaction Titre Exécutée'),
         ('NAV_CALCULATED', 'Valeur Liquidative Calculée'),('FEE_COMPUTED', 'Frais Provisionnés'),
         ('DIV_DECLARED', 'Dividende/Coupon Déclaré'),], string="Type d'Événement", required=True)
    company_id = fields.Many2one('res.company', required=True, index=True)
    journal_id = fields.Many2one('account.journal', string="Journal", required=True,
                                 domain="[('company_id', '=', company_id)]")
    active = fields.Boolean(default=True)
    line_ids = fields.One2many('efund.accounting.schema.line', 'schema_id', string="Lignes comptables")
