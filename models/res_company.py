from odoo import models, fields, api
from odoo.exceptions import ValidationError


class ResCompany(models.Model):
    _inherit = 'res.company'

    # Champs de base
    est_societe_gestion = fields.Boolean(string='Est une société de gestion', default=False)
    est_fonds = fields.Boolean(string='Est un fonds', default=True)
    code_isin = fields.Char(string='Code ISIN', size=12)
    code_fonds = fields.Char(string='Code interne du fonds')

    # Relations inverses pour navigation facile
    """
    fund_management_company_id = fields.One2many(
        'efund.management.company',
        'company_id',
        string='Fund Management Company',
        readonly=True
    )

    fund_id = fields.One2many(
        'efund.fund',
        'company_id',
        string='Fund',
        readonly=True
    )
    # Propriétés computed pour compatibilité
    is_fund_management_company = fields.Boolean(
        string='Is Fund Management Company',
        compute='_compute_company_type',
        store=True
    )

    is_fund = fields.Boolean(
        string='Is Fund',
        compute='_compute_company_type',
        store=True
    )

    @api.depends('fund_management_company_id', 'fund_id')
    def _compute_company_type(self):
        for company in self:
            company.is_fund_management_company = bool(company.fund_management_company_id)
            company.is_fund = bool(company.fund_id)

    """