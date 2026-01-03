from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)



class FundInitialValuationWizard(models.TransientModel):
    _name = 'efund.initial.valuation.wizard'
    _description = 'Wizard for Initial Fund Valuation with Investors'

    fund_id = fields.Many2one('efund.fund',string='Fund',required=True,domain="[('state', '=', 'draft')]")
    share_class_id = fields.Many2one('efund.fund.class',string='Share Class',required=True,domain="[('fund_id', '=', fund_id), ('state', '=', 'active')]")
    valuation_date = fields.Date(string='Valuation Date',required=True,default=fields.Date.context_today)
    initial_nav_per_share = fields.Float(string='Initial NAV per Share',default=10000.0,required=True)

    # Lignes détaillées pour chaque investisseur
    investor_line_ids = fields.One2many('efund.initial.valuation.investor.line','wizard_id',string='Investors and Their Subscriptions',required=True)
    total_capital = fields.Float(string='Total Capital',compute='_compute_totals')
    total_shares = fields.Float(string='Total Shares',digits=(16, 2),compute='_compute_totals' )
    show_create_button = fields.Boolean(compute="_compute_show_button")

    @api.depends('total_capital')
    def _compute_show_button(self):
        for rec in self:
            rec.show_create_button = rec.total_capital > 0

    @api.depends('investor_line_ids.amount', 'investor_line_ids.units')
    def _compute_totals(self):
        for wizard in self:
            wizard.total_capital = sum(line.amount for line in wizard.investor_line_ids)
            wizard.total_shares = sum(line.units for line in wizard.investor_line_ids)

    @api.constrains('investor_line_ids')
    def _check_investor_lines(self):
        for wizard in self:
            if not wizard.investor_line_ids:
                raise ValidationError(_("At least one investor is required for initial valuation."))

            if any(line.amount <= 0 for line in wizard.investor_line_ids):
                raise ValidationError(_("All investment amounts must be positive."))

    def action_create_initial_valuation(self):
        """Crée la première valorisation avec les parts détaillées par investisseur"""
        self.ensure_one()

        # Validation des données
        if self.total_capital <= 0:
            raise ValidationError(_("Total capital must be positive."))

        # 1. Création de la première NAV
        nav_record = self._create_initial_nav()
        nav_record.flush_recordset()
        self.env.cr.commit()
        # self.env.flush_model('efund.fund.nav') # forcement le commit dans la BD


        # 2. Création des transactions individuelles pour chaque investisseur
        _logger.info(f"******* *******l'id du nav créé est : {nav_record.id}")
        transactions = self._create_initial_subscriptions(nav_record.id)

        # 3. Création des écritures comptables
        accounting_entry = self._create_accounting_entries()

        # 4. Mise à jour du statut du fonds
        self.fund_id.write({'state': 'active'})

        # 5. Création des positions initiales pour chaque investisseur
        self._create_initial_positions()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Initial NAV Created'),
            'res_model': 'efund.fund.nav',
            'res_id': nav_record.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _create_initial_nav(self):
        """Crée le premier enregistrement NAV"""
        return self.env['efund.fund.nav'].create({
            'fund_id': self.fund_id.id,
            'share_class_id': self.share_class_id.id,
            'computed_at': self.valuation_date,
            'date': self.valuation_date,
            'nav_per_share': self.initial_nav_per_share,
            'nav_total': self.total_capital,
            'total_shares': self.total_shares,
            'status': 'computed',
            'is_initial_valuation': True,
        })

    def _create_initial_subscriptions(self, nav_id):
        """Crée les transactions de souscription pour chaque investisseur"""
        transactions = self.env['efund.fund.transaction']

        for investor_line in self.investor_line_ids:
            transaction = self.env['efund.fund.transaction'].create({
                'nav_id': nav_id,
                'fund_id': self.fund_id.id,
                'investor_id': investor_line.investor_id.id,
                'share_class_id': self.share_class_id.id,
                'transaction_type': 'subscription',
                'date': self.valuation_date,
                'units': investor_line.units,
                'unit_value': self.initial_nav_per_share,
                'amount': investor_line.amount,
                'status': 'validated',
                'is_initial_capital': True,
                'name': f"INITIAL-{investor_line.investor_id.name}-{self.fund_id.name}",
            })
            transactions += transaction

        return transactions

    def _create_accounting_entries(self):
        """Crée les écritures comptables pour le capital initial"""
        # === METHODE 1 : Via res.company (recommandée) ===
        cash_account = self.fund_id.cash_account_id
        capital_account = self.fund_id.capital_account_id
        subscription_journal_id = self.fund_id.subscription_journal_id

        if not cash_account or not capital_account:
            raise ValidationError(_("Please configure accounting accounts for the fund first."))

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.valuation_date,
            'journal_id': subscription_journal_id.id,
            'company_id': self.fund_id.company_id.id,
            'ref': f"Capital initial - {self.fund_id.name}",
            'line_ids': [
                (0, 0, {
                    'account_id': cash_account.id,
                    'debit': self.total_capital,
                    'credit': 0,
                    'name': f"Apport capital initial - {self.fund_id.name}",
                }),
                (0, 0, {
                    'account_id': capital_account.id,
                    'debit': 0,
                    'credit': self.total_capital,
                    'name': f"Capital social - {self.fund_id.name}",
                }),
            ],
        })
        move.action_post()
        return move

    def _create_initial_positions(self):
        """Crée les positions initiales pour chaque investisseur"""
        for investor_line in self.investor_line_ids:
            self.env['efund.investor.position'].create({
                'investor_id': investor_line.investor_id.id,
                'fund_id': self.fund_id.id,
                'share_class_id': self.share_class_id.id,
                'units': investor_line.units,
                'average_price': self.initial_nav_per_share,
                'total_cost': investor_line.amount,
                'current_value': investor_line.amount,
                'as_of_date': self.valuation_date,
            })

    def _get_bank_journal(self):
        return self.env['account.journal'].search([
            ('company_id', '=', self.fund_id.company_id.id),
            ('type', '=', 'bank'),
        ], limit=1)