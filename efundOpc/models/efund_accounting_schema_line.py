from odoo import api, fields, models, _
from datetime import datetime

class FundAccountingSchemaLine(models.Model):
    _name = "efund.accounting.schema.line"
    _description = "Accounting Schema Line"
    _order = "sequence, id"

    schema_id = fields.Many2one('efund.accounting.schema',required=True,ondelete='cascade')
    sequence = fields.Integer(default=10, string="Ordre")
    account_id = fields.Many2one('account.account',required=True, string="Compte")
    account_selection_type = fields.Selection([('always', 'Toujours ce compte'), ('if_positive', 'Uniquement si Positif'), ('if_negative', 'Uniquement si Négatif'), ], required=True, default='always', string="Condition de signe")
    side = fields.Selection([('debit', 'Debit'),('credit', 'Credit')], string="Sens", required=True)
    amount_type = fields.Selection([('gross', 'Montant Brut'),('net', 'Montant Net'),('fees', 'Frais/Commissions'),
                                    ('capital_init','Souscription Exercice'),('non_distribuable','Sommes Non Distribuables'),
                                    ('res_anterieurs','Résultat Antérieur'),('res_clos','Résultat Clos'),
                                    ('res_en_cours','Résultat En Cours'),('entry_load','Droit entrée'),('exit_load','Droit sortie'),('reliquat','Reliquat'),
        ('capital', 'Part Capital'),('income', 'Part Revenu'),('tax', 'Taxes/Prélèvements'),], string="Source du Montant", required=True)
    label = fields.Char(help="Libellé de la ligne")
    use_analytic = fields.Boolean(string="Utiliser l'analytique du mandat", default=True,
                                  help="Si coché, l'écriture sera marquée avec le compte analytique du mandat lié.")

