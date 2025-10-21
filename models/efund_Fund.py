from odoo import models, fields, api
from odoo.exceptions import UserError,ValidationError
from odoo.models import Constraint

# models/fund.py
class Fund(models.Model):
    _name = 'efund.fund'
    _description = 'Fund'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        ondelete='cascade'
    )

    management_company_id = fields.Many2one(
        'efund.management.company',
        string='Management Company',
        required=True,
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
    #share_class_ids = fields.One2many('fund.share.class', 'fund_id', string='Share Classes')
    currency_id = fields.Many2one(related='company_id.currency_id')

    @api.model
    def create(self, vals):
        """Create a res.company automatically when creating a Fund."""
        # Vérification de l'existence d'une société avec le même nom
        existing_company = self.env['res.company'].sudo().search([('name', '=', vals.get('name'))], limit=1)
        if existing_company:
            raise ValidationError(_("A company with the same name already exists."))

        # Préparation des valeurs de la société associée
        company_vals = {
            'name': vals.get('name'),
            'currency_id': vals.get('currency_id'),
        }

        # Création de la société en superuser
        company = self.env['res.company'].sudo().create(company_vals)

        # Lier le fonds à la société nouvellement créée
        vals['company_id'] = company.id

        # Création du fonds
        fund = super(Fund, self).create(vals)

        # Ajout éventuel de configurations post-création
        fund._post_create_setup(company)

        return fund

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

        # ------------------------------------------------------------
        # DISPLAY NAME
        # ------------------------------------------------------------
        def name_get(self):
            result = []
            for record in self:
                name = f"{record.company_id.name or 'Unnamed Fund'}"
                result.append((record.id, name))
            return result