from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundAccountPart(models.Model):
    _name = 'efund.account.part'
    _description = 'Compte Parts / Actions'

    name = fields.Char(string="Libellé", required=True, copy=False)
    account_number = fields.Char(string="Numéro compte", required=True, copy=False)
    investor_id = fields.Many2one('efund.investor', string="Investisseur", ondelete='cascade')
    fund_id = fields.Many2one('efund.fund', string="Fond", required=True, ondelete='cascade')
    company_id = fields.Many2one('res.company',related='fund_id.company_id',store=True,index=True,readonly=True)
    total_parts = fields.Float(compute='_compute_total_parts',store=False)
    total_value = fields.Float(string="Valeur totale (FCFA)", store=False)
    state = fields.Selection([
        ('draft', 'Non Activé'),
        ('active', 'Activé'),
        ('suspended', 'Désactivé'),
    ], string="Status", default='draft',)

    def action_redeem_parts(self):
        self.ensure_one()

        if self.state != 'active':
            raise UserError(_("Le compte titres n’est pas actif."))

        if self.total_parts <= 0:
            raise UserError(_("Aucune part disponible pour le rachat."))

        if self.investor_id.compliance_status != 'compliant':
            raise UserError(_("Investisseur non conforme KYC."))

        # ouvrir le wizard de rachat
        return {
            'type': 'ir.actions.act_window',
            'name': _("Rachat de parts"),
            'res_model': 'efund.fund.redemption.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_account_part_id': self.id,
                'default_investor_id': self.investor_id.id,
                'default_fund_id': self.fund_id.id,
                'default_company_id': self.company_id.id,
            }
        }

    _account_number_fund_uniq = models.Constraint(
        'unique(account_number, fund_id)',
        'Numéro de compte titres déjà utilisé pour ce fonds'
    )
    _investor_id_fund_uniq = models.Constraint(
        'unique(investor_id, fund_id)',
        'Un investisseur ne peut avoir qu’un compte titres par fonds'
    )

    def _compute_total_parts(self):
        for acc in self:
            moves = self.env['efund.account.part.move'].search([
                ('part_account_id', '=', acc.id)
            ])
            acc.total_parts = sum(
                m.parts if m.move_type == 'subscription' else -m.parts
                for m in moves
            )

