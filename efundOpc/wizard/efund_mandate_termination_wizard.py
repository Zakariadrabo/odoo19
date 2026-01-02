from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EfundMandateTerminationWizard(models.TransientModel):
    _name = 'efund.mandate.termination.wizard'
    _description = 'Wizard de clôture de mandat'

    mandate_id = fields.Many2one('efund.mandate', string="Mandat", required=True, readonly=True)
    cash_account_id = fields.Many2one('efund.account.cash', string="Compte espèce", store=True)
    company_id = fields.Many2one(related='mandate_id.management_company_id.company_id', store=True, readonly=True)
    capital_remaining = fields.Monetary(string="Capital restant à rembourser", readonly=True)
    currency_id = fields.Many2one(related='company_id.management_company_id.currency_id', store=True, readonly=True)
    execution_date = fields.Date(string="Date de clôture", default=fields.Date.today, required=True)
    reason = fields.Text(string="Motif de clôture", required=True)

    # -------------------------------------------------
    # INITIALISATION
    # -------------------------------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        mandate = self.env['efund.mandate'].browse(
            res.get('mandate_id')
        )

        if mandate:
            if mandate.state != 'active':
                raise UserError(
                    _("Seul un mandat actif peut être clôturé.")
                )

            res['capital_remaining'] = mandate.capital_remaining

        return res

    # -------------------------------------------------
    # CONFIRMATION DE CLÔTURE
    # -------------------------------------------------
    def action_confirm(self):
        self.ensure_one()
        mandate = self.mandate_id

        if mandate.state != 'active':
            raise UserError(_("Le mandat n’est pas actif."))

        # Sécurité multi-company
        if self.env.company != mandate.company_id:
            raise UserError(_("Contexte société incorrect."))

        # Récupération de l'Id du compte espèces du mandat
        Cash = self.env['efund.account.cash'].search([('mandate_id', '=', self.mandate_id.id), ], limit=1)

        # Sécurité : éviter les doublons
        if not Cash:
            raise UserError(_("Le compte espèce du mandant est introuvable."))

        # Remboursement du capital restant (s’il existe)
        if self.capital_remaining > 0:
            self.env['efund.mandate.termination'].create({
                'cash_account_id': Cash.id,
                'mandate_id': mandate.id,
                'move_type': 'capital_return',
                'amount': self.capital_remaining,
                'state': 'draft',
            })
        return {'type': 'ir.actions.act_window_close'}
