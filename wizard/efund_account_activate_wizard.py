from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ActivateAccountWizard(models.TransientModel):
    _name = 'efund.account.activate.wizard'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Activation de compte'

    account_model = fields.Selection([
        ('cash','Compte espèces'),
        ('part','Compte titres'),
    ], required=True)

    cash_account_id = fields.Many2one('efund.account.cash')
    part_account_id = fields.Many2one('efund.account.part')

    fund_id = fields.Many2one('efund.fund', readonly=True)
    investor_id = fields.Many2one('efund.investor', readonly=True)

    reason = fields.Text(string="Motif d’activation", required=True)

    def action_confirm(self):
        self.ensure_one()

        account = self.cash_account_id or self.part_account_id

        # 🔐 Sécurités métier
        if account.state != 'draft':
            raise UserError(_("Ce compte n’est pas en attente d’activation."))

        # Investisseur validé pour le fonds
        fund_inv = self.env['efund.fund.investor'].search([
            ('investor_id', '=', account.investor_id.id),
            ('fund_id', '=', account.fund_id.id),
            ('state', '=', 'validated')
        ], limit=1)

        if not fund_inv:
            raise UserError(_("Investisseur non validé pour ce fonds."))

        # Activation
        account.write({'state': 'active'})

        # Traçabilité
        account.message_post(
            body=_(
                "Compte activé par %s.<br/>Motif : %s"
            ) % (self.env.user.name, self.reason)
        )
