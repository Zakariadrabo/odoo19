from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class EfundFundTypeAllocation(models.Model):
    _name = 'efund.fund.type.allocation'

    fund_type_id = fields.Many2one('efund.fund.type', required=True)
    asset_class_id = fields.Many2one('efund.asset.class', required=True)
    min_pct = fields.Float(string="Minimum Allocation (%)", required=True)
    max_pct = fields.Float(string="Maximum Allocation (%)",required=True)

    @api.constrains('min_pct', 'max_pct')
    def _check_min_max(self):
        for rec in self:
            if rec.min_pct < 0 or rec.max_pct < 0:
                raise ValidationError("Les pourcentages ne peuvent pas être négatifs.")
            if rec.min_pct > rec.max_pct:
                raise ValidationError("Le minimum ne peut pas dépasser le maximum.")
