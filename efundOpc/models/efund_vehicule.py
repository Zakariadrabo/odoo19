import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class EfundVehicle(models.Model):
    _name = 'efund.vehicule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Véhicule de gestion'

    # =========================================================
    # 2. CADRE RÉGLEMENTAIRE
    # =========================================================
    name = fields.Char(required=True, string="Nom")
    vehicle_type = fields.Selection([('fund', 'Fonds'), ('mandate', 'Mandat')], string="Type")
    vehicule_code = fields.Char(string="Référence", default=lambda self: self.env['ir.sequence'].next_by_code('efund.vehicule'))
    company_id = fields.Many2one('res.company', string='Compagnie', ondelete='cascade')
    management_company_id = fields.Many2one('efund.management.company', string='Société de gestion',
                                            domain="[('company_id', '!=', company_id)]")
    currency_id = fields.Many2one('res.currency',)
    created_date = fields.Date(string='Date de création')
    start_date = fields.Date(string="Date d'opération")
    phone = fields.Char(string="Contact")
    address = fields.Char(string="Adresse")

    # =========================================================
    # 2. CADRE RÉGLEMENTAIRE
    # =========================================================
    license_number = fields.Char(string="N° Agrément")
    license_date = fields.Date(string="Date d’agrément")
    info_visa_number = fields.Char(string="N° Visa Note d'information")
    info_visa_date = fields.Date(string="Date édition note")
    regulatory_note = fields.Text(string="Informations réglementaires")

    state = fields.Selection(
        [('draft', 'Draft'), ('active', 'Active'), ('suspended', 'Suspended'), ('liquidated', 'Liquidated'), ],
        string='Status', default='draft')

    ##################################################
    ## RELATIONS
    ##################################################

    depositary_id = fields.Many2one("efund.depositaire", string="Dépositaire")
    expenses_ids = fields.One2many('efund.fund.expense', 'vehicule_id')
    position_ids = fields.One2many('efund.vehicule.portfolio', 'vehicule_id', string="Positions")
    vehicule_cash_move_ids = fields.One2many('efund.vehicule.cash.move', 'vehicule_id', string="Flux financiers")
    cash_operation_ids = fields.One2many('efund.vehicule.cash.operation', 'vehicule_id', string="Opérations diverses")
    cashflow_ids = fields.One2many('efund.vehicule.cashflow', 'vehicule_id', string="Flux de trésorerie prévus")
    analytic_account_id = fields.Many2one('account.analytic.account', string='Compte analytique')
    cash_account_id = fields.Many2one('account.account',string="Compte Espèces Dépositaire",help="Compte comptable utilisé pour les règlements/livraisons")
    all_portfolio_cashflows = fields.One2many('efund.portfolio.amortization.line', compute='_compute_all_cashflows', string="Échéancier Global des Flux")

    def _compute_all_cashflows(self):
        for vehicule in self:
            # On récupère toutes les lignes d'amortissement de toutes les positions
            # dont la date est supérieure ou égale à aujourd'hui
            lines = self.env['efund.portfolio.amortization.line'].search([
                ('portfolio_id.vehicule_id', '=', vehicule.id),
                ('date', '>=', fields.Date.today())
            ], order='date asc')
            vehicule.all_portfolio_cashflows = lines

    @api.model_create_multi
    def create(self, vals_list):
        """Create a res.company automatically when creating a Fund."""
        funds = self.env[self._name]
        management_company = self.env['efund.management.company'].search([], limit=1)
        if not management_company:
            raise UserError(_("Pas de société de gestion. Merci d'en créer une d'abord."))

        for vals in vals_list:
            fund_name = vals.get('name')
            if not fund_name:
                raise ValidationError(_("Le nom est obligatoire."))

            # Récupère ou détermine la devise
            currency_id = vals.get('currency_id') or self.env.company.currency_id.id
            if not currency_id:
                raise ValidationError(_("Pas de money par défaut pour la compagnie"))

            # Vérifie s'il existe déjà une société avec ce nom
            existing_company = self.env['res.company'].sudo().search([('name', '=', fund_name)], limit=1)
            if existing_company:
                raise ValidationError(_("Existence du même nom"))

            is_mandate = self.env.context.get('is_mandate_creation') or vals.get('vehicle_type') == 'mandate'

            # On ne crée la compagnie QUE si ce n'est PAS un mandat
            if not is_mandate:
                company = self.env['res.company'].sudo().create({
                    'name': fund_name,
                    'currency_id': currency_id,
                    'is_funder': True,
                    'is_management_company': False,
                })

                # Met à jour le partner associé
                partner = company.partner_id
                partner.write({'is_fund': True})
                vals['company_id'] = company.id
            else:
                # 1. Vérifier/Créer la société MANDATS
                company_mandat = self._get_or_create_mandat_company(management_company.currency_id.id)

            # Injecte les champs dépendants

            vals['management_company_id'] = management_company.id
            vals['currency_id'] = management_company.currency_id.id

            # Appel du super
            vehicules = super(EfundVehicle, self).create(vals_list)

            # 2. Parcours des fonds créés pour configurer la comptabilité

            for vehicule in vehicules:
                # 1. Appel du Handler pour créer la structure comptable et analytique
                self.env['efund.event.handler'].on_vehicule_created(vehicule)

            return vehicules


    def _get_or_create_mandat_company(self, currency):
        """ Recherche la société MANDATS, la crée et la configure si besoin """
        company_name = "MANDATS"
        company = self.env['res.company'].search([('name', '=', company_name)], limit=1)

        if not company:
            # Création de la société
            company = self.env['res.company'].create({
                'name': company_name,
                'company_code': 'MANDATS',
                'currency_id': currency,  # FCFA par défaut pour UMOA
            })
            _logger.info("Société pivot MANDATS créée.")

        # Vérifier si le plan comptable est installé
        if not company.chart_template:
            self.env['efund.event.handler'].get_chart_account_data(company.id)

        return company



    def action_revalue_positions(self):
        pass
