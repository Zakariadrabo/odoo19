from odoo import models, fields, api, _

class FundInstrumentIssuerRating(models.Model):
    _name = "efund.vehicule.instrument.issuer.rating"
    _description = "Notation de l'émetteur"
    _order = "rating_date desc"

    issuer_id = fields.Many2one('efund.vehicule.instrument.issuer', string="Émetteur", ondelete='cascade')

    agency_id = fields.Selection([
        ('sp', 'S&P'),
        ('moodys', 'Moody’s'),
        ('fitch', 'Fitch'),
        ('bloomfield', 'Bloomfield'),
        ('gcr', 'GCR Ratings'),
    ], string="Agence de notation", required=True)

    rating_value = fields.Char("Note", required=True, help="Ex: AAA, Baa1, A-, etc.")
    rating_date = fields.Date("Date de notation", default=fields.Date.today)
    outlook = fields.Selection([
        ('stable', 'Stable'),
        ('positive', 'Positive'),
        ('negative', 'Négative'),
        ('evolving', 'En évolution'),
    ], string="Perspective", default='stable')