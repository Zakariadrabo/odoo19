from odoo import models, fields

class FundInstrumentIssuer(models.Model):
    _name = "efund.instrument.issuer"
    _description = "Émetteur d'instrument financier"
    _order = "name"

    name = fields.Char("Nom de l'émetteur", required=True)
    country_id = fields.Many2one("res.country", string="Pays")
    instrument_count = fields.Integer(string="Nombre d'instruments", compute="_compute_instrument_count")
    rating = fields.Char("Notation (S&P / Moody’s / Bloomfield)")
    website = fields.Char("Site Web")
    description = fields.Text("Informations complémentaires")
    industry = fields.Selection([
        ('finance', 'FINANCE'),
        ('agriculture', 'AGRICULTURE'),
        ('distribution', 'DISTRIBUTION'),
        ('industrie', 'INDUSTRIE'),
        ('transport', 'TRANSPORT'),
        ('autre', 'AUTRE')
    ], default='finance')
    #Nouveau
    issuer_type = fields.Selection([
        ('sovereign', 'Sovereign (État)'),
        ('quasi_sovereign', 'Quasi-Sovereign'),
        ('supranational', 'Supranational'),
        ('corporate', 'Corporate'),
        ('financial', 'Financial Institution'),
        ('municipal', 'Municipal'),
    ], string='Issuer Type', )


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
