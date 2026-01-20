from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class Mandate(models.Model):
    _name = 'efund.vehicule.mandate'
    _inherits = {'efund.vehicule': 'vehicule_id'}

    vehicule_id = fields.Many2one('efund.vehicule', required=True, ondelete='cascade')
    vehicle_type = fields.Selection([('fund', 'Fonds'), ('mandate', 'Mandat')],default='mandate', required=True, string="Type")
    client_id = fields.Many2one('efund.investor', required=True)
    risk_profile = fields.Selection([('low', 'Prudent'), ('medium', 'Équilibré'), ('high', 'Dynamique')],  string='Profil de risque', required=True )

    @api.model_create_multi
    def create(self, vals_list):
        """Create a res.company automatically when creating a Fund."""
        funds = self.env[self._name]
        management_company = self.env['efund.management.company'].search([], limit=1)
        if not management_company:
            raise UserError(_("La société de gestion obligatoire. Please create one first."))

        for vals in vals_list:
            fund_name = vals.get('name')
            if not fund_name:
                raise ValidationError(_("Le nom mandat est obligatoire."))

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
        funds = super(Mandate, self).create(vals_list)

        # Post-traitement si nécessaire
        for fund in funds:
            fund._post_create_setup(fund.company_id)

        return funds


