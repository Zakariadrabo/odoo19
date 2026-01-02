from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class ActivateAccountWizard(models.TransientModel):
    _name = 'efund.account.activate.wizard'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _description = 'Activation de compte'

    account_model = fields.Selection([
        ('cash','Compte espèces'),
        ('part','Compte titres'),
    ], required=True, string="Type compte")

    cash_account_id = fields.Many2one('efund.account.cash', string="Compte espèces")
    part_account_id = fields.Many2one('efund.account.part', string="Compte titre")

    fund_id = fields.Many2one('efund.fund', readonly=True, string="Fond")
    mandat_id = fields.Many2one('efund.mandate', readonly=True, string="Mandat")
    investor_id = fields.Many2one('efund.investor', readonly=True, string="Investisseur")
    reason = fields.Text(string="Motif d’activation", required=True)

    def action_confirm(self):
        self.ensure_one()

        account = self.cash_account_id or self.part_account_id

        # 🔐 Sécurités métier
        if account.state != 'draft':
            raise UserError(_("Ce compte n’est pas en attente d’activation."))

        # Investisseur validé pour le fonds
        if  account.fund_id.id:
            fund_inv = self.env['efund.fund.investor'].search([
                ('investor_id', '=', account.investor_id.id),
                ('fund_id', '=', account.fund_id.id),
                ('state', '=', 'validated')
            ], limit=1)
        elif account.mandate_id.id:
            fund_inv = self.env['efund.mandat.investor'].search([
                ('investor_id', '=', account.investor_id.id),
                ('mandate_id', '=', account.mandate_id.id),
                ('state', '=', 'validated')
            ], limit=1)
        else:
            raise UserError(_("Compte sans fonds ou mandat associé."))

        if not fund_inv:
            raise UserError(_("Investisseur non validé pour ce fonds ou mandat."))

        # Activation
        account.write({'state': 'active'})

        # Traçabilité
        account.message_post(
            body=_(
                "Compte activé par %s.<br/>Motif : %s"
            ) % (self.env.user.name, self.reason)
        )
