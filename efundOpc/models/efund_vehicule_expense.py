from odoo import models, fields, api, _

class FundExpense(models.Model):
    _name = "efund.vehicule.expense"
    _description = "Charge du Fonds"
    _inherit = ['mail.thread', 'mail.activity.mixin']

    ##################################################
    ## RELATIONS
    ##################################################
    vehicule_id = fields.Many2one('efund.vehicule', required=True, ondelete='cascade')
    currency_id = fields.Many2one(related="vehicule_id.currency_id", string='Devise')

    name = fields.Char(required=True, string='Nom de la charge')
    expense_type = fields.Selection([('bank', 'Frais bancaires'),('regulator', 'Redevance du régulateur'),
        ('auditor', 'Commissaire aux comptes'),('custodian', 'Dépositaire'), ('management', 'Frais de gestion'),('other', 'Autres charges'),
    ], required=True, string='Type de charge')
    partner_id = fields.Many2one('efund.debit.partner', string="Bénéficiaire")
    frequency = fields.Selection([('daily', 'Quotidienne'),('monthly', 'Mensuelle'),('quarterly', 'Trimestrielle'),
        ('annual', 'Annuelle'),('one_off', 'Ponctuelle'),], required=True, string='Fréquence de paiement')
    calculation_method = fields.Selection([('fixed', 'Montant fixe'),('percentage_assets', '% des actifs'),
    ], required=True, string='Méthode de calcul')
    amount = fields.Monetary(string="Montant fixe")
    rate = fields.Float(string="Taux (%)")

    start_date = fields.Date( string='Date de début')
    end_date = fields.Date(string='Date de fin')
    state = fields.Selection([('draft', 'Draft'),('validated', 'Validé'),('archived', 'Archivé'),], default='draft',)

    def action_validate(self):
        pass
    def action_archive(self):
        pass
    def action_reactivate(self):
        pass
    def action_duplicate(self):
        pass
    def action_show_rate_details(self):
        pass
    def action_show_amount_details(self):
        pass