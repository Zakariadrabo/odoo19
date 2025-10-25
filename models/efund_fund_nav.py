from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundNAV(models.Model):
    _name = "efund.fund.nav"
    _description = "Computed NAV for a fund"

    fund_id = fields.Many2one('res.company', domain="[('company_type','=','fonds')]", required=True)
    date = fields.Date(required=True, index=True)
    fund_currency_id = fields.Many2one('res.currency',string="Devise du fonds",required=True)
    nav_total = fields.Monetary(string="Actif net total",currency_field='fund_currency_id')
    nav_per_share = fields.Float()
    class_id = fields.Many2one('efund.fund.class')
    status = fields.Selection([('draft','Draft'),('computed','Computed'),('posted','Posted')], default='draft')
    computed_by = fields.Many2one('res.users')
    computed_at = fields.Datetime()
    accounting_move_id = fields.Many2one('account.move')

    def compute_nav(self):
        # Simplified placeholder: aggregate market_value from positions
        positions = self.env['fund.position'].search([('fund_id','=',self.fund_id.id),('valuation_date','=',self.date)])
        total = sum(positions.mapped('market_value') or [0.0])
        self.nav_total = total
        if self.class_id and self.class_id.shares_outstanding:
            self.nav_per_share = total / self.class_id.shares_outstanding
        else:
            self.nav_per_share = 0.0
        self.status = 'computed'
        self.computed_by = self.env.user
        self.computed_at = fields.Datetime.now()

    @api.model
    def compute_nav_batch(self):
        funds = self.env['res.company'].search([('company_type','=','fonds')])
        for fund in funds:
            nav = self.create({'fund_id': fund.id, 'date': fields.Date.today()})
            try:
                nav.compute_nav()
            except Exception as e:
                pass

    def calculate_nav(self):
        """Calcule la NAV pour une classe de parts"""
        self.ensure_one()

        # 1. Valorisation des actifs
        positions = self.env['fund.position'].search([
            ('fund_id', '=', self.fund_id.id)
        ])
        total_assets = sum(pos.market_value for pos in positions)

        # 2. Calcul des passifs
        fees_payable = self._calculate_accrued_fees()
        other_liabilities = self._calculate_other_liabilities()
        total_liabilities = fees_payable + other_liabilities

        # 3. Nombre de parts
        total_shares = self._calculate_outstanding_shares()

        # 4. Calcul final
        net_assets = total_assets - total_liabilities
        nav_per_share = net_assets / total_shares if total_shares > 0 else 0

        return {
            'total_net_assets': net_assets,
            'nav_per_share': nav_per_share,
            'total_shares': total_shares
        }

    """
        nav_checklist = [
    '✓ Tous les prix de marché reçus et validés',
    '✓ Positions mises à jour avec les dernières transactions',
    '✓ Frais de gestion courus calculés',
    '✓ Taux de change du jour appliqués',
    '✓ Nombre de parts mis à jour (souscriptions/rachats)',
    '✓ Calculs vérifiés par une seconde personne',
    '✓ NAV publiée avant la deadline réglementaire'
]
    """
