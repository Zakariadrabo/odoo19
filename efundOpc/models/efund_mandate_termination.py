from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.models import Constraint

class EfundMandateTermination(models.Model):
    _name = 'efund.mandate.termination'
    _description = 'Clôture de mandat'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    mandate_id = fields.Many2one('efund.mandate',required=True)
    cash_account_id = fields.Many2one('efund.account.cash',string="Compte espèce",store=True)
    company_id = fields.Many2one(related="mandate_id.management_company_id.company_id", string='Company', ondelete='cascade')
    capital_remaining = fields.Monetary(related='mandate_id.capital_remaining',compute='_compute_financial_summary')
    amount = fields.Monetary(string="Capital à rembourser",required=True)
    currency_id = fields.Many2one(related='mandate_id.management_company_id.company_id.currency_id',store=True)
    state = fields.Selection([('draft', 'Brouillon'),('validated', 'Validé'),('executed', 'Exécuté')], default='draft', tracking=True)
    reason = fields.Text(string='Raison de la clôture')
    execution_date = fields.Date()

    def action_execute(self):
        self.ensure_one()
        mandate = self.mandate_id

        if self.state != 'validated':
            raise UserError(_("La clôture doit être validée."))

        self.mandate_id.write({'state': 'terminated'})

        self.write({
            'state': 'executed',
            'execution_date': fields.Date.today(),
        })

        # Traçabilité
        mandate.message_post(
            body=_(
                "Mandat clôturé par %s.<br/>"
                "Date : %s<br/>"
                "Motif : %s<br/>"
                "Capital remboursé : %s"
            ) % (
                     self.env.user.name,
                     self.execution_date,
                     self.reason,
                     self.capital_remaining,
                 )
        )



