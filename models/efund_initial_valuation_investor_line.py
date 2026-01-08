from odoo import models, fields, api
from odoo.exceptions import ValidationError


class FundInitialValuationInvestorLine(models.TransientModel):
    _name = 'efund.initial.valuation.investor.line'
    _description = 'Initial Valuation Investor Line'

    wizard_id = fields.Many2one(
        'efund.initial.valuation.wizard',
        string='Wizard',
        readonly=True,
        ondelete='cascade'
    )

    investor_id = fields.Many2one(
        'efund.investor',
        string='Investor',
        required=True
    )

    amount = fields.Float(
        string='Investment Amount',
        required=True
    )

    units = fields.Float(
        string='Number of Shares',
        digits=(16, 2),
        compute='_compute_units',
        readonly=False,
        store=True
    )

    percentage_ownership = fields.Float(
        string='Ownership %',
        compute='_compute_percentage_ownership',
        digits=(5, 4)
    )
    sequence = fields.Integer(
        string='Sequence',
        default=10,
        help="Ordre d'affichage dans les listes"
    )

    @api.depends('amount', 'wizard_id.initial_nav_per_share')
    def _compute_units(self):
        for line in self:
            if line.wizard_id.initial_nav_per_share > 0:
                line.units = line.amount / line.wizard_id.initial_nav_per_share
            else:
                line.units = 0.0

    @api.depends('units', 'wizard_id.total_shares')
    def _compute_percentage_ownership(self):
        for line in self:
            if line.wizard_id.total_shares > 0:
                line.percentage_ownership = (line.units / line.wizard_id.total_shares)
            else:
                line.percentage_ownership = 0.0

    @api.constrains('amount')
    def _check_positive_amount(self):
        for line in self:
            if line.amount <= 0:
                raise ValidationError(_("Investment amount must be positive for %s") % line.investor_id.name)

    @api.model
    def default_get(self, fields_list):
        defaults = super().default_get(fields_list)
        wizard_id = self.env.context.get('default_wizard_id')
        if wizard_id and 'wizard_id' in fields_list:
            defaults['wizard_id'] = wizard_id
        return defaults
