from odoo import models, fields, api, _

class EfundNavSession(models.Model):
    _name = 'efund.nav.session'
    _description = 'Séance de calcul de la VL'
    _inherit = ['mail.thread']

    name = fields.Char(string="Référence", readonly=True, default='/')
    fund_id = fields.Many2one('efund.vehicule.fund', string="Fonds", required=True)
    valuation_date = fields.Date(string="Date de VL", required=True, default=fields.Date.today)

    # Résultats globaux
    total_assets = fields.Monetary(string="Total Actif", compute="_compute_nav")
    total_liabilities = fields.Monetary(string="Total Passif", compute="_compute_nav")
    net_asset_value = fields.Monetary(string="Actif Net", compute="_compute_nav")

    nb_parts = fields.Float(string="Nombre de parts", digits=(16, 4))
    unit_nav = fields.Float(string="VL Unitaire", digits=(16, 4), compute="_compute_nav", store=True)

    currency_id = fields.Many2one(related='fund_id.currency_id')
    state = fields.Selection([('draft', 'Brouillon'), ('validated', 'Validée')], default='draft')
    line_ids = fields.One2many('efund.nav.line', 'session_id', string="Détails de l'Inventaire")

    @api.depends('line_ids', 'nb_parts')
    def _compute_nav(self):
        for rec in self:
            assets = sum(rec.line_ids.filtered(lambda l: l.type == 'asset').mapped('amount'))
            liabilities = sum(rec.line_ids.filtered(lambda l: l.type == 'liability').mapped('amount'))
            rec.total_assets = assets
            rec.total_liabilities = liabilities
            rec.net_asset_value = assets - liabilities
            rec.unit_nav = rec.net_asset_value / rec.nb_parts if rec.nb_parts else 0

    def action_generate_lines(self):
        self.ensure_one()
        # Nettoyage des anciennes lignes si on recalcule
        self.line_ids.unlink()

        lines_vals = []

        # --- 1. VALORISATION DES TITRES (Actif) ---
        # On récupère les positions du fonds (en supposant un champ position_ids sur le fonds)
        for pos in self.fund_id.position_ids:
            # On récupère le dernier prix (votre méthode existante)
            # La valorisation = (Quantité * Prix) + Coupons Courus
            total_valuation = pos.market_value + pos.accrued_interest

            lines_vals.append((0, 0, {
                'name': f"Titre : {pos.instrument_id.name}",
                'type': 'asset',
                'amount': total_valuation,
                'session_id': self.id
            }))

        # --- 2. RÉCUPÉRATION DU CASH (Actif) ---
        # On interroge la balance du compte 121001 pour ce mandat/fond
        cash_balance = self.env['account.analytic.account'].browse(
            self.fund_id.analytic_account_id.id)._compute_account_balance('121001')

        lines_vals.append((0, 0, {
            'name': "Liquidités (Compte 121001)",
            'type': 'asset',
            'amount': cash_balance,
            'session_id': self.id
        }))

        # --- 3. PROVISION DES FRAIS DE GESTION (Passif) ---
        # Exemple de calcul simplifié : (Actif Brut * Taux / 365)
        gross_assets = sum(l[2]['amount'] for l in lines_vals if l[2]['type'] == 'asset')
        daily_fees = (gross_assets * (self.fund_id.management_fee_rate / 100)) / 365

        lines_vals.append((0, 0, {
            'name': "Provision Frais de Gestion (Journalier)",
            'type': 'liability',
            'amount': daily_fees,
            'session_id': self.id
        }))

        # --- 4. RÉCUPÉRATION DU NOMBRE DE PARTS ---
        # On peut soit le lire sur un champ du fonds, soit via le compte 371100
        # Ici on suppose un champ technique qui suit les parts
        self.nb_parts = self.fund_id.total_shares_count

        self.write({'line_ids': lines_vals})
        return True