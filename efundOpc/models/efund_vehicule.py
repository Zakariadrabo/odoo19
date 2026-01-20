from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundVehicle(models.Model):
    _name = 'efund.vehicule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Véhicule de gestion'

    # =========================================================
    # 2. CADRE RÉGLEMENTAIRE
    # =========================================================
    name = fields.Char(required=True, string="Nom")
    vehicle_type = fields.Selection([('fund', 'Fonds'), ('mandate', 'Mandat')],  string="Type")
    company_id = fields.Many2one('res.company', string='Compagnie', ondelete='cascade')
    management_company_id = fields.Many2one('efund.management.company', string='Société de gestion', domain="[('company_id', '!=', company_id)]")
    currency_id = fields.Many2one('res.currency', required=True)
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
    position_ids = fields.One2many('efund.fund.position', 'vehicule_id', string="Positions")

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
        funds = super(EfundVehicle, self).create(vals_list)

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

