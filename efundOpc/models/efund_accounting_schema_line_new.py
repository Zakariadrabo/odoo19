from odoo import api, fields, models, _
from datetime import datetime

class FundAccountingSchemaLine(models.Model):
    _name = "efund.accounting.schema.line.new"
    _description = "Accounting Schema Line"
    _order = "sequence, id"

    schema_id = fields.Many2one('efund.accounting.schema.new',required=True,ondelete='cascade')
    sequence = fields.Integer(default=10, string="Ordre")
    account_resolution_type = fields.Selection([('fixed', 'Compte Fixe'),('instrument', 'Compte lié à l\'Instrument'), ('liquidity', 'Compte Liquidité du Véhicule')
    ], default='fixed')
    account_code = fields.Selection([
        ('111001','Compte espèce'),('553200', 'Frais sur Titre'),('727110','Interet couru obl'),
        ('121001', 'Compte courant'), ('371200', 'Clients, compte espèces'), ('389008', 'Coupon à récevoir'),
        ('710200', 'Révenu Obligation'), ('141710', 'Interet couru bilan dat tcn'), ('551801', 'plus value obl'),
        ('581300', 'résultat antérieur'), ('591110', 'Résultat clos'), ('770000', 'résultat encours'),('572100', 'Souscription exercice'), ('389951', 'droit entré'),
        ('217100', 'interet couru obl bilan'),('727120', 'interet couru dat'),('141710', 'interet couru dat bilan'),
        ('553100',' Diff Est'),('217500','Diff OPC'),('389400','Frais Gestion Bilan'),('603100','Frais Gestion Result'),
        ('217300','Diff Obl'),('217300','Diff Action'),('217400','Diff Obl'),('217500','Diff OPC')
    ], string="Compte")
    account_selection_type = fields.Selection([('always', 'Toujours ce compte'), ('if_positive', 'Uniquement si Positif'), ('if_negative', 'Uniquement si Négatif'), ], required=True, default='always', string="Condition de signe")
    side = fields.Selection([('debit', 'Debit'),('credit', 'Credit')], string="Sens", required=True)
    amount_type = fields.Selection([('gross', 'Montant Brut'),('net', 'Montant Net'),('fees', 'Frais/Commissions'),
                                    ('capital_init','Souscription Exercice'),('non_distribuable','Sommes Non Distribuables'),
                                    ('res_anterieurs','Résultat Antérieur'),('res_clos','Résultat Clos'),('interest','Intérêt couru'),
                                    ('res_en_cours','Résultat En Cours'),('entry_load','Droit entrée'),('exit_load','Droit sortie'),('reliquat','Reliquat'),
        ('capital', 'Part Capital'),('income', 'Revenu'),('tax', 'Taxes/Prélèvements'),('quantity','Quantité'),
                                    ('ic_obl','interet couru obl'),('ic_dat','interet couru dat tcn'),
                                    ], string="Source du Montant", required=True)
    label = fields.Char(help="Libellé de la ligne")
    use_analytic = fields.Boolean(string="Utiliser l'analytique du mandat", default=True,
                                  help="Si coché, l'écriture sera marquée avec le compte analytique du mandat lié.")

