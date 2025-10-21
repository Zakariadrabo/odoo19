from odoo import models, fields, api
from odoo.exceptions import UserError,ValidationError

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


    @api.constrains('company_id')
    def _check_company_is_management(self):
        """Vérifie que la company n'est pas déjà un fond"""
        for mgmt_company in self:
            if mgmt_company.company_id.fund_id:
                raise ValidationError(
                    ("This company is already used as a fund and cannot be a management company.")
                )

    # Computed fields
    @api.depends('managed_funds')
    def _compute_funds_count(self):
        for record in self:
            record.funds_count = len(record.managed_funds)