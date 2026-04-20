from odoo import models, fields, api

class FundInstrumentIssuer(models.Model):
    _name = "efund.vehicule.instrument.issuer"
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
        ('etat', 'État'),
        ('autre', 'Autre')
    ], default='finance', string='Industries')
    website = fields.Char("Site Web")
    description = fields.Text("Informations complémentaires")
    #Nouveau
    issuer_type = fields.Selection([
        ('sovereign', 'Titre souverain(État)'),
        ('financial', 'Institution Financière'),
        ('supranational', 'Institution Régionale'),
        ('corporate', 'Société'),
    ], string='Type Emetteur', )

    #instrument_count = fields.Integer(string="Nombre d'instruments", compute="_compute_instrument_count")
    rating = fields.Char("Notation (S&P / Moody’s / Bloomfield / Fitch)")
    rating_ids = fields.One2many('efund.vehicule.instrument.issuer.rating', 'issuer_id', string="Historique des Notations")

    current_rating = fields.Char( string="Note Actuelle", compute="_compute_current_rating", store=True,  help="Affiche la note la plus récente")

    @api.depends('rating_ids.rating_value', 'rating_ids.rating_date')
    def _compute_current_rating(self):
        for rec in self:
            # On récupère la notation la plus récente
            latest = rec.rating_ids.sorted('rating_date', reverse=True)
            if latest:
                rec.current_rating = f"{latest[0].agency_id.upper()}: {latest[0].rating_value}"
            else:
                rec.current_rating = "Non noté"

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
