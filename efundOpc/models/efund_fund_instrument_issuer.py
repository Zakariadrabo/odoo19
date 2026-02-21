from odoo import models, fields

class FundInstrumentIssuer(models.Model):
    _name = "efund.instrument.issuer"
    _description = "Émetteur d'instrument financier"
    _order = "name"

    name = fields.Char("Nom de l'émetteur", required=True)
    country_id = fields.Many2one("res.country", string="Pays")
    industry = fields.Selection([
        ('finance', 'Finance'),
        ('agriculture', 'Agriculture'),
        ('distribution', 'Distribution'),
        ('industrie', 'Industrie'),
        ('transport', 'Transport'),
        ('autre', 'Autre')
    ], default='finance', string='Industries')
    rating = fields.Char("Notation (S&P / Moody’s / Bloomfield / Fitch)")
    website = fields.Char("Site Web")
    description = fields.Text("Informations complémentaires")
    #Nouveau
    issuer_type = fields.Selection([
        ('sovereign', 'Titre souverain(État)'),
        ('financial', 'Institution Financière'),
        ('supranational', 'Institution Régionale'),
        ('corporate', 'Société'),
    ], string='Type Emetteur', )

    instrument_count = fields.Integer(
        string="Nombre d'instruments",
        compute="_compute_instrument_count"
    )

    def _compute_instrument_count(self):
        for rec in self:
            rec.instrument_count = self.env["efund.fund.instrument"].search_count([
                ("issuer_id", "=", rec.id)
            ])

    def action_open_instruments(self):
        return {
            "type": "ir.actions.act_window",
            "name": "Instruments émis",
            "res_model": "efund.fund.instrument",
            "view_mode": "list,form",
            "domain": [("issuer_id", "=", self.id)],
            "context": {"default_issuer_id": self.id},
        }
