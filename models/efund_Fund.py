import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.models import Constraint

_logger = logging.getLogger(__name__)


# models/fund.py
class Fund(models.Model):
    _name = 'efund.fund'
    _description = 'Fund'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Fund Name", required=True)
    code = fields.Char(string="Fund Code", required=True)
    company_id = fields.Many2one('res.company', string='Company', ondelete='cascade')
    management_company_id = fields.Many2one('efund.management.company', string='Management Company',
                                            domain="[('company_id', '!=', company_id)]")

    # Propriétés spécifiques fonds
    fund_type = fields.Selection([('equity', 'Equity Fund'), ('bond', 'Bond Fund'), ('mixed', 'Mixed Fund'), ],
                                 string='Fund Type', required=True)
    risk_level = fields.Selection([('low', 'Low Risk'), ('medium', 'Medium Risk'), ('high', 'High Risk'), ],
                                  string='Risk Level')
    nav_frequency = fields.Selection([('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly'), ],
                                     string="NAV Frequency", default='daily')
    launch_date = fields.Date(string='Launch Date')
    ter = fields.Float(string='Total Expense Ratio (%)', digits=(6, 4))
    investment_objective = fields.Text(string='Investment Objective')
    benchmark_index = fields.Char(string='Benchmark Index')
    redemption_delay = fields.Selection([('J', 'J'), ('J1', 'J+1'), ('J2', 'J+2'), ], string="Délai de rachat",
                                        default='J2', required=True)
    cutoff_time = fields.Float(string="Heure de cut-off", default=16.0,
                               help="Heure limite de réception des ordres (format décimal).\nExemples : 14.0 = 14h00, 14.5 = 14h30, 16.75 = 16h45.")

    # Statuts
    state = fields.Selection(
        [('draft', 'Draft'), ('active', 'Active'), ('suspended', 'Suspended'), ('liquidated', 'Liquidated'), ],
        string='Status', default='draft')

    # Relations
    share_class_ids = fields.One2many('efund.fund.class', 'fund_id', string='Share Classes')
    currency_id = fields.Many2one(related='company_id.currency_id')

    # Comptabilité
    cash_account_id = fields.Many2one('account.account', string='Cash Account',
                                      domain="[('account_type', '=', 'asset_cash')]",
                                      help="Compte bancaire principal du fonds")
    capital_account_id = fields.Many2one('account.account', string='Capital Account',
                                         domain="[('account_type', '=', 'equity')]",
                                         help="Compte de capital social du fonds")
    subscription_account_id = fields.Many2one('account.account', string='Subscription Account',
                                              help="Compte de souscription du fonds")
    redemption_account_id = fields.Many2one('account.account', string='Redemption Account',
                                            help="Compte de rachat du fonds")
    fee_income_account_id = fields.Many2one('account.account', string='Fee Income Account',
                                            help="Compte de recettes de frais du fonds")
    # === JOURNAUX par Fonds ===
    subscription_journal_id = fields.Many2one('account.journal', string='Subscription Journal',
                                              domain="[('type', '=', 'bank'), ('company_id', 'in', [company_id])]",
                                              help="Journal de souscription du fonds")
    redemption_journal_id = fields.Many2one('account.journal', string='Redemption Journal',
                                            domain="[('type', '=', 'bank'), ('company_id', 'in', [company_id])]",
                                            help="Journal de rachat du fonds")
    operations_journal_id = fields.Many2one('account.journal', string='Miscellaneous Journal',
                                            domain="[('type', '=', 'bank'), ('company_id', 'in', [company_id])]",
                                            help="Journal divers du fonds")

    # Données sur les positions du fond
    position_ids = fields.One2many('efund.fund.position', 'fund_id', string="Positions")

    # Champs calculés pour le résumé
    total_market_value = fields.Monetary(string="Valeur totale du portfolio", currency_field='currency_id',
                                         compute='_compute_portfolio_summary', store=False)
    position_count = fields.Integer(string="Nombre de positions", compute='_compute_portfolio_summary', store=False)
    total_unrealized_pl = fields.Monetary(string="Total Plus/Moins-values", currency_field='currency_id',
                                          compute='_compute_portfolio_summary', store=False)
    last_valuation_date = fields.Date(string="Dernière valorisation", compute='_compute_portfolio_summary', store=False)
    portfolio_concentration = fields.Float(string="Concentration du top 5", compute='_compute_portfolio_concentration',
                                           digits=(16, 2))
    cash_available = fields.Monetary(compute='_compute_cash_available', currency_field='currency_id')
    cash_committed = fields.Monetary(compute='_compute_cash_committed', currency_field='currency_id')
    allow_fractional_parts = fields.Boolean(string="Autoriser les parts fractionnées", default=False,
                                            help="Si décoché, les souscriptions sont arrondies à l'entier inférieur.")

    ## TEST VL
    current_vl = fields.Float(string="VL actuelle")
    VL_share_class_id = fields.Many2one('efund.fund.class', string="Classes de partage VL")

    #Ajout
    # =========================================================
    # 1. IDENTIFICATION DU FONDS
    # =========================================================

    legal_form = fields.Char(
        string="Forme juridique"
    )

    commercial_register = fields.Char(
        string="Registre de commerce"
    )

    country_id = fields.Many2one(
        "res.country",
        string="Pays"
    )

    city = fields.Char(
        string="Ville"
    )

    active = fields.Boolean(
        default=True
    )

    # =========================================================
    # 2. CADRE RÉGLEMENTAIRE
    # =========================================================
    license_number = fields.Char(
        string="N° Agrément"
    )

    license_date = fields.Date(
        string="Date d’agrément"
    )

    info_visa_number = fields.Char(
        string="N° Visa Note d'information"
    )

    info_visa_date = fields.Date(
        string="Date édition note"
    )

    regulatory_note = fields.Text(
        string="Informations réglementaires"
    )

    # =========================================================
    # 3. ACTEURS DU FONDS
    # =========================================================
    issuer_id = fields.Many2one(
        "res.partner",
        string="Émetteur",
        domain=[("is_company", "=", True)]
    )

    depositary_id = fields.Many2one(
        "res.partner",
        string="Dépositaire",
        domain=[("is_company", "=", True)]
    )

    manager_id = fields.Many2one(
        "res.partner",
        string="Gestionnaire",
        domain=[("is_company", "=", True)]
    )

    # =========================================================
    # 4. PARAMÈTRES FINANCIERS
    # =========================================================
    currency_id = fields.Many2one(
        "res.currency",
        string="Devise",
        required=True,
        default=lambda self: self.env.company.currency_id
    )

    initial_price = fields.Selection([
        ('Cours Connu', 'Cours Connu'),
        ('Cours Inconnu', 'Cours Inconnu'),
    ], string='Type de Souscription ')

    current_price = fields.Monetary(
        string="Cours actuel",
        currency_field="currency_id"
    )

    initial_nav = fields.Monetary(
        string="VL d’origine",
        currency_field="currency_id"
    )

    current_nav = fields.Monetary(
        string="VL actuelle",
        currency_field="currency_id"
    )

    investment_value = fields.Monetary(
        string="Valeur de placement",
        currency_field="currency_id"
    )

    capital_amount = fields.Monetary(
        string="Capital",
        currency_field="currency_id"
    )

    investment_duration = fields.Integer(
        string="Durée de placement (mois)"
    )

    # =========================================================
    # 5. PARTS (GLOBAL FONDS)
    # =========================================================
    initial_units = fields.Float(
        string="Parts initiales",
        digits=(16, 4)
    )

    opening_units = fields.Float(
        string="Parts début exercice",
        digits=(16, 4)
    )

    current_units = fields.Float(
        string="Parts actuelles",
        digits=(16, 4)
    )

    # =========================================================
    # 6. FRAIS, TAXES & COMMISSIONS
    # =========================================================
    taf_rate = fields.Float(
        string="TAF (%)",
        digits=(16, 4)
    )

    subscription_fee_rate = fields.Float(
        string="Frais de souscription (%)",
        digits=(16, 4)
    )

    redemption_fee_rate = fields.Float(
        string="Frais de rachat (%)",
        digits=(16, 4)
    )

    retro_subscription_rate = fields.Float(
        string="Rétrocession souscription (%)",
        digits=(16, 4)
    )

    retro_redemption_rate = fields.Float(
        string="Rétrocession rachat (%)",
        digits=(16, 4)
    )

    # =========================================================
    # 7. EXERCICE & CALCUL VL
    # =========================================================
    nav_calculation_period = fields.Selection(
        [
            ("daily", "Quotidien"),
            ("weekly", "Hebdomadaire"),
            ("monthly", "Mensuel"),
        ],
        string="Périodicité calcul VL",
        default="daily"
    )

    fiscal_year_start = fields.Date(
        string="Début exercice"
    )

    fiscal_year_end = fields.Date(
        string="Fin exercice"
    )

    next_nav_date = fields.Date(
        string="Prochaine date VL"
    )
    # profil du fond

    fund_type = fields.Selection(
        [
            ("opcvm", "OPCVM"),
            ("fia", "FIA"),
            ("monetary", "Fonds monétaire"),
            ("bond", "Fonds obligataire"),
            ("equity", "Fonds actions"),
            ("balanced", "Fonds diversifié"),
        ],
        string="Type de fonds"
    )

    target_investors = fields.Selection(
        [
            ("retail", "Particuliers"),
            ("institutional", "Institutionnels"),
            ("both", "Mixtes"),
        ],
        string="Investisseurs ciblés"
    )
    investment_horizon = fields.Selection(
        [
            ("short", "Court terme"),
            ("medium", "Moyen terme"),
            ("long", "Long terme"),
        ],
        string="Horizon d’investissement"
    )

    #################################################
    #      Constrainte
    ################################################

    def _compute_cash_available(self):
        for fund in self:
            deposits = sum(fund.cash_account_id.move_line_ids.mapped('balance'))
            commitments = sum(
                fund.bourse_order_ids.filtered(
                    lambda o: o.state in ('validated', 'partial')
                ).mapped('amount')
            )
            fund.cash_available = deposits - commitments
            fund.cash_committed = commitments

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

    # Méthode positions
    @api.depends('position_ids', 'position_ids.market_value',
                 'position_ids.unrealized_pl', 'position_ids.valuation_date')
    def _compute_portfolio_summary(self):
        """Calcule les totaux du portfolio"""
        for fund in self:
            active_positions = fund.position_ids.filtered(
                lambda p: p.state == 'active'
            )

            fund.total_market_value = sum(active_positions.mapped('market_value'))
            fund.position_count = len(active_positions)
            fund.total_unrealized_pl = sum(active_positions.mapped('unrealized_pl'))

            if active_positions:
                fund.last_valuation_date = max(active_positions.mapped('valuation_date'))
            else:
                fund.last_valuation_date = False

    def _compute_portfolio_concentration(self):
        """Calcule la concentration du portfolio (top 5 positions)"""
        for fund in self:
            active_positions = fund.position_ids.filtered(
                lambda p: p.status == 'active'
            ).sorted('market_value', reverse=True)

            if fund.total_market_value > 0:
                top_5_value = sum(pos.market_value for pos in active_positions[:5])
                fund.portfolio_concentration = (top_5_value / fund.total_market_value) * 100
            else:
                fund.portfolio_concentration = 0.0

    # ========== MÉTHODES D'ACTION ==========
    def action_open_position_wizard(self):
        """Ouvrir le wizard pour ajouter une position"""
        self.ensure_one()
        return {
            'name': _('Ajouter une position'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.position.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_fund_id': self.id,
                'default_operation_type': 'add',
            }
        }

    def action_import_positions(self):
        """Ouvrir le wizard pour importer des positions"""
        self.ensure_one()
        return {
            'name': _('Importer des positions'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.position.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_fund_id': self.id,
                'default_operation_type': 'import',
            }
        }

    def action_portfolio_report(self):
        """Générer un rapport de portfolio"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web#action=efund_fund.action_portfolio_report&active_id={self.id}',
            'target': 'self',
        }

    def action_view_positions(self):
        """Voir toutes les positions du fonds"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Positions de %s') % self.name,
            'res_model': 'efund.fund.position',
            'view_mode': 'list,form',
            'domain': [('fund_id', '=', self.id)],
            'context': {'default_fund_id': self.id},
        }

    def action_update_position(self):
        """Ouvrir le wizard pour mettre à jour la position"""
        self.ensure_one()

        if self.status == 'closed':
            raise UserError(_("Impossible de modifier une position clôturée."))

        _logger.info(f"action_update_position: {self.id}")

        return {
            'name': _('Mettre à jour la position') % self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'efund.fund.position',
            'view_mode': 'list,form',
            'context': {
                'default_position_id': self.id,
                'default_fund_id': self.fund_id.id,
                'default_instrument_id': self.instrument_id.id,
                'default_current_quantity': self.quantity,
                'default_current_avg_cost': self.avg_cost,
                'default_current_date': self.valuation_date,
            }
        }

    def action_close_position(self):
        """Clôturer la position"""
        self.ensure_one()

        if self.status == 'closed':
            raise UserError(_("Cette position est déjà clôturée."))

        return {
            'name': _('Clôturer la position'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.position.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_position_id': self.id,
                'default_fund_id': self.fund_id.id,
                'default_instrument_id': self.instrument_id.id,
                'default_current_quantity': self.quantity,
                'default_market_value': self.market_value,
            }
        }

    def get_dashboard_data(self):
        self.ensure_one()

        latest_nav = self.env['efund.fund.nav'].search([
            ('fund_id', '=', self.id)
        ], limit=1, order="date desc")

        transactions = self.env['efund.fund.transaction'].search([
            ('fund_id', '=', self.id)
        ], limit=10, order="date desc")

        return {
            'fund': {
                'name': self.name,
                'fund_type': self.fund_type,
                'risk_level': self.risk_level,
                'benchmark_index': self.benchmark_index,
                'aum': self.aum if hasattr(self, 'aum') else 0,
                'nav_latest': latest_nav.nav_per_share if latest_nav else 0,
                'perf_ytd': 0,  # calcul à compléter
            },
            'transactions': [{
                'date': t.date,
                'type': t.transaction_type,
                'investor_id': t.investor_id,
                'amount': t.amount
            } for t in transactions]
        }
