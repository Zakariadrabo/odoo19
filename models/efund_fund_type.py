from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class EfundFundType(models.Model):
    _name = 'efund.fund.type'
    _description = 'Type de fonds OPCVM'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    _order = 'name'

    name = fields.Char(string="Type de fonds",required=True)
    code = fields.Char(string="Code",required=True)
    description = fields.Text(string="Description")
    allocation_rule_ids = fields.One2many('efund.fund.type.allocation','fund_type_id',string="Règles d’allocation")
    state = fields.Selection([('draft', 'Draft'),('validated', 'Validé'), ('archived', 'Archivé'),], default='draft')

    def action_validate(self):
        self.write({'state': 'validated'})

    def action_archived(self):
        self.write({'state': 'archived'})


