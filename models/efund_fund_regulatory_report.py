from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EfundFundRegulatoryReport(models.Model):
    _name = 'efund.fund.regulatory.report'
    _description = 'État réglementaire AMF-UMOA'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'date desc'

    name = fields.Char(string="Référence",required=True,default=lambda self: _('État réglementaire OPCVM'))
    fund_id = fields.Many2one('efund.fund',string="Fonds",required=True)
    fund_type_id = fields.Many2one(related='fund_id.fund_type_id',store=True,readonly=True)
    company_id = fields.Many2one(related='fund_id.company_id',store=True,readonly=True)
    currency_id = fields.Many2one(related='fund_id.currency_id',store=True,readonly=True)
    date = fields.Date(string="Date de situation",required=True,default=fields.Date.today)
    snapshot_id = fields.Many2one('efund.fund.allocation.snapshot',string="Composition réelle",required=True,ondelete='restrict')
    control_id = fields.Many2one('efund.fund.allocation.control',string="Contrôle de conformité",required=True,ondelete='restrict')
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé'),
        ('submitted', 'Transmis AMF-UMOA'),
    ], default='draft', tracking=True)
    conclusion = fields.Text(string="Conclusion réglementaire",readonly=True)

    # -------------------------
    # ACTIONS
    # -------------------------
    def action_validate(self):
        for rec in self:
            if rec.control_id.state == 'breach':
                raise UserError(_(
                    "Impossible de valider : dépassement réglementaire détecté."
                ))

            rec.state = 'validated'
            rec.conclusion = _(
                "La composition du portefeuille est conforme "
                "au type de fonds déclaré."
            )

            rec.message_post(
                body=_("État réglementaire validé.")
            )

    def action_submit(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("L’état doit être validé avant transmission."))

            rec.state = 'submitted'
            rec.message_post(
                body=_("État réglementaire transmis à l’AMF-UMOA.")
            )
