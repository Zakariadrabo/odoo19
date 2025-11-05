from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.models import Constraint


# models/fund.py
class Fund(models.Model):
    _name = 'efund.fund'
    _description = 'Fund'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Fund Name", required=True)
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        ondelete='cascade'
    )

    management_company_id = fields.Many2one(
        'efund.management.company',
        string='Management Company',
        domain="[('company_id', '!=', company_id)]"  # Évite bouclage
    )

    # Propriétés spécifiques fonds
    fund_type = fields.Selection([
        ('equity', 'Equity Fund'),
        ('bond', 'Bond Fund'),
        ('mixed', 'Mixed Fund'),
    ], string='Fund Type', required=True)

    risk_level = fields.Selection([
        ('low', 'Low Risk'),
        ('medium', 'Medium Risk'),
        ('high', 'High Risk'),
    ], string='Risk Level')

    nav_frequency = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string="NAV Frequency", default='daily')

    # Statuts
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('liquidated', 'Liquidated'),
    ], string='Status', default='draft')

    launch_date = fields.Date(string='Launch Date')
    ter = fields.Float(string='Total Expense Ratio (%)', digits=(6, 4))
    investment_objective = fields.Text(string='Investment Objective')
    benchmark_index = fields.Char(string='Benchmark Index')

    # Relations
    share_class_ids = fields.One2many('efund.fund.class', 'fund_id', string='Share Classes')
    currency_id = fields.Many2one(related='company_id.currency_id')

    # Comptabilité

    cash_account_id = fields.Many2one(
        'account.account',
        string='Cash Account',
        domain="[('account_type', '=', 'asset_cash')]",
        help="Compte bancaire principal du fonds"
    )

    capital_account_id = fields.Many2one(
        'account.account',
        string='Capital Account',
        domain="[('account_type', '=', 'equity')]",
        help="Compte de capital social du fonds"
    )

    # Comptes supplémentaires
    subscription_account_id = fields.Many2one(
        'account.account',
        string='Subscription Account'
    )

    redemption_account_id = fields.Many2one(
        'account.account',
        string='Redemption Account'
    )

    fee_income_account_id = fields.Many2one(
        'account.account',
        string='Fee Income Account'
    )
    # === JOURNAUX par Fonds ===
    subscription_journal_id = fields.Many2one(
        'account.journal',
        string='Subscription Journal',
        domain="[('type', '=', 'bank'), ('company_id', 'in', [company_id])]"
    )

    redemption_journal_id = fields.Many2one(
        'account.journal',
        string='Redemption Journal',
        domain="[('type', '=', 'bank'), ('company_id', 'in', [company_id])]"
    )

    operations_journal_id = fields.Many2one(
        'account.journal',
        string='Miscellaneous Journal',
        domain="[('type', '=', 'bank'), ('company_id', 'in', [company_id])]"
    )

    # Méthode utilitaire pour récupérer un journal
    def _get_default_journal(self, journal_type='bank'):
        """Retourne le journal par défaut selon le type"""
        return self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', journal_type)
        ], limit=1)


    @api.model_create_multi
    def create(self, vals_list):
        """Create a res.company automatically when creating a Fund."""
        funds = self.env[self._name]
        management_company = self.env['efund.management.company'].search([], limit=1)
        if not management_company:
            raise UserError(_("No Management Company found. Please create one first."))

        for vals in vals_list:
            fund_name = vals.get('name')
            if not fund_name:
                raise ValidationError(_("Fund name is required."))

            # Récupère ou détermine la devise
            currency_id = vals.get('currency_id') or self.env.company.currency_id.id
            if not currency_id:
                raise ValidationError(_("No default currency found for your company."))

            # Vérifie s'il existe déjà une société avec ce nom
            existing_company = self.env['res.company'].sudo().search([('name', '=', fund_name)], limit=1)
            if existing_company:
                raise ValidationError(_("A company with the same name already exists."))

            # Crée automatiquement la société associée
            company = self.env['res.company'].sudo().create({
                'name': fund_name,
                'currency_id': currency_id,
            })

            # Met à jour le partner associé
            partner = company.partner_id
            partner.write({'is_fund': True})

            # Injecte les champs dépendants
            vals['company_id'] = company.id
            vals['management_company_id'] = management_company.id
            vals['currency_id'] = currency_id

        # Appel du super
        funds = super(Fund, self).create(vals_list)

        # Post-traitement si nécessaire
        for fund in funds:
            fund._post_create_setup(fund.company_id)

        return funds

    def _post_create_setup(self, company):
        """Optional post-creation configuration."""
        return True

    def _post_create_setup(self, company):
        """Initialisation post-création : journaux, comptes, etc."""
        self.ensure_one()
        # Exemple : création automatique de journaux spécifiques au fonds
        journal_vals = {
            'name': f"{self.name} Bank Journal",
            'code': 'BANK',
            'type': 'bank',
            'company_id': company.id,
        }
        self.env['account.journal'].sudo().create(journal_vals)

    # ------------------------------------------------------------
    # ACTION METHODS
    # ------------------------------------------------------------
    def action_activate(self):
        for record in self:
            if not record.launch_date:
                raise ValidationError(_("Please define a launch date before activating the fund."))
            record.state = 'active'
            record.message_post(body=_("Fund has been activated."))

    def action_suspend(self):
        for record in self:
            if record.state != 'active':
                raise ValidationError(_("Only active funds can be suspended."))
            record.state = 'suspended'
            record.message_post(body=_("Fund has been suspended."))

    def action_liquidate(self):
        for record in self:
            if record.state not in ('active', 'suspended'):
                raise ValidationError(_("Only active or suspended funds can be liquidated."))
            record.state = 'liquidated'
            record.message_post(body=_("Fund has been liquidated."))

    def action_initial_valuation(self):
        """
        Méthode appelée quand on clique le bouton.
        Self = enregistrement(s) sélectionné(s) dans la tree view
        """
        self.ensure_one()  # S'assure qu'un seul fond est sélectionné

        # OUVRE le wizard de valorisation initiale
        return {
            'type': 'ir.actions.act_window',  # Ouvre une fenêtre
            'name': f'Valorisation Initiale - {self.name}',
            'res_model': 'efund.initial.valuation.wizard',  # Modèle transient
            'view_mode': 'form',
            'target': 'new',  # Fenêtre modale
            'context': {
                'default_fund_id': self.id,  # Pré-remplit le fond
                'default_share_class_id': self.share_class_ids[:1].id,
            }
        }
