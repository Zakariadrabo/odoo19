from odoo import models, fields, api, _

class FundPrudentialResult(models.Model):
    _name = 'efund.fund.prudential.result'
    _description = 'Résultat ratio prudentiel'

    fund_id = fields.Many2one('efund.fund', string="Fonds", required=True)
    ratio_id = fields.Many2one('efund.fund.prudential.ratio',string="Ratio",required=True)

    date = fields.Date(required=True, string="Date")
    value = fields.Float(string="Valeur")

    status = fields.Selection([
        ('ok', 'Conforme'),
        ('warning', 'Alerte'),
        ('breach', 'Dépassement'),
    ], string="Statut", default='ok')
