from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundRedemptionWizard(models.TransientModel):
    _name = 'efund.fund.redemption.wizard'
    _description = 'Wizard de rachat de parts (partiel / total)'

    # contexte
    investor_id = fields.Many2one(
        'efund.investor',
        string="Investisseur",
        required=True,
        readonly=True
    )

    account_part_id = fields.Many2one(
        'efund.account.part',
        string="Compte titres",
        required=True,
        readonly=True
    )

    fund_id = fields.Many2one(
        'efund.fund',
        string="Fonds",
        required=True,
        readonly=True
    )

    company_id = fields.Many2one(
        'res.company',
        string="Société (Fonds)",
        required=True,
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        readonly=True
    )

    # rachat
    redemption_type = fields.Selection(
        [
            ('partial', 'Rachat partiel'),
            ('total', 'Rachat total'),
        ],
        string="Type de rachat",
        default='partial',
        required=True
    )

    total_parts_available = fields.Float(
        string="Parts disponibles",
        readonly=True
    )

    parts_to_redeem = fields.Float(
        string="Nombre de parts à racheter"
    )

    # info VL (prévisionnelle)
    nav_date = fields.Date(
        string="Date VL appliquée",
        default=fields.Date.context_today,
        required=True
    )

    estimated_nav = fields.Monetary(
        string="VL estimée",
        help="VL indicative (à confirmer)",
    )

    estimated_amount = fields.Monetary(
        string="Montant estimé du rachat",
        compute="_compute_estimated_amount",
        store=False
    )

    # -------------------------
    # INIT
    # -------------------------
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)

        account = self.env['efund.account.part'].browse(
            self.env.context.get('default_account_part_id')
        )

        if not account:
            raise UserError(_("Compte titres introuvable."))

        res.update({
            'account_part_id': account.id,
            'investor_id': account.investor_id.id,
            'fund_id': account.fund_id.id,
            'company_id': account.company_id.id,
            'total_parts_available': account.total_parts,
        })
        return res

    # -------------------------
    # COMPUTE
    # -------------------------
    @api.depends('redemption_type', 'parts_to_redeem', 'total_parts_available', 'estimated_nav')
    def _compute_estimated_amount(self):
        for wiz in self:
            parts = wiz.total_parts_available if wiz.redemption_type == 'total' else wiz.parts_to_redeem or 0.0
            wiz.estimated_amount = parts * (wiz.estimated_nav or 0.0)

    # -------------------------
    # VALIDATION
    # -------------------------
    def action_confirm_redemption(self):
        self.ensure_one()

        account = self.account_part_id
        investor = self.investor_id

        # sécurité métier
        if account.state != 'active':
            raise UserError(_("Le compte titres n’est pas actif."))

        if investor.compliance_status != 'compliant':
            raise UserError(_("Investisseur non conforme KYC / AML."))

        if self.redemption_type == 'partial':
            if self.parts_to_redeem <= 0:
                raise UserError(_("Le nombre de parts doit être supérieur à zéro."))
            if self.parts_to_redeem > self.total_parts_available:
                raise UserError(_("Parts insuffisantes pour ce rachat."))

            parts = self.parts_to_redeem
        else:
            parts = self.total_parts_available

        # création de la demande de rachat
        redemption = self.env['efund.fund.redemption'].create({
            'investor_id': investor.id,
            'account_part_id': account.id,
            'fund_id': self.fund_id.id,
            'company_id': self.company_id.id,
            'redemption_type': self.redemption_type,
            'parts': parts,
            'nav_date': self.nav_date,
            'estimated_nav': self.estimated_nav,
            'state': 'draft',
        })

        return {
            'type': 'ir.actions.act_window',
            'name': _("Demande de rachat"),
            'res_model': 'efund.fund.redemption',
            'view_mode': 'form',
            'res_id': redemption.id,
            'target': 'current',
        }
