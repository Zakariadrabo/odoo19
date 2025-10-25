from odoo import models, fields, api, _
from odoo.exceptions import UserError,ValidationError
import logging

_logger = logging.getLogger(__name__)

class FundManagementCompany(models.Model):
    _name = 'efund.management.company'
    _description = 'Fund Management Company'

    company_id = fields.Many2one(
        'res.company',
        string='Company',
        required=True,
        ondelete='cascade'
    )

    # Propriétés spécifiques société de gestion
    regulatory_license = fields.Char(string='Regulatory License Number')
    aum = fields.Monetary(string='Assets Under Management', currency_field='currency_id')
    risk_management_policy = fields.Text(string='Risk Management Policy')
    compliance_officer_id = fields.Many2one('res.partner', string='Compliance Officer')

    funds_count = fields.Integer(
        string='Number of Funds',
        compute='_compute_funds_count'
    )

    # Related fields
    currency_id = fields.Many2one(
        related='company_id.currency_id',
        string='Currency'
    )

    name = fields.Char(
        related='company_id.name',
        string='Management Company Name',
        readonly=True,
        store=True
    )

    # Relations
    managed_funds = fields.One2many('efund.fund', 'management_company_id', string='Managed Funds')

    @api.model_create_multi
    def create(self, vals_list):
        """Ensure only one management company globally."""
        if self.search_count([]) > 0:
            raise UserError(_("Only one Management Company can exist in the system."))

        for vals in vals_list:
            company = self.env['res.company'].browse(vals.get('company_id'))
            if not company:
                raise ValidationError(_("A valid company must be linked."))

            company.is_management_company = True

            # Met à jour le partner associé
            partner = company.partner_id
            partner.write({'is_management_company': True})

        return super().create(vals_list)


    # Computed fields
    @api.depends('managed_funds')
    def _compute_funds_count(self):
        for record in self:
            record.funds_count = len(record.managed_funds)