from odoo import models, fields

class EfundFiscalYear(models.Model):
    _name = 'efund.fiscal.year'
    _description = "Exercice Fiscal eFund"

    name = fields.Char(string="Nom de l'exercice", required=True) 
    date_start = fields.Date(string="Date de début", required=True)
    date_end = fields.Date(string="Date de fin", required=True)
    company_id = fields.Many2one('res.company', string="Société de gestion")
    state = fields.Selection([('draft', 'Ouvert'), ('closed', 'Clôturé')], default='draft')

    def action_close(self):
        self.state = 'closed'

    def action_reopen(self):
        self.state = 'draft'