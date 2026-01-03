from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class MandatInvestor(models.Model):
    _name = 'efund.mandate.investor'
    _description = 'Investisseur validé pour un mandat'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    investor_id = fields.Many2one('efund.investor',string="Investisseur",required=True,index=True,ondelete='cascade')
    partner_id = fields.Many2one(related='investor_id.partner_id',string="Partenaire")
    full_name = fields.Char(related='investor_id.full_name',string="Nom complet")
    name=fields.Char(related='investor_id.name',string="Nom")
    mandate_id = fields.Many2one('efund.mandate', string="Mandat", index=True,ondelete='cascade')
    company_id = fields.Many2one('res.company',related='mandate_id.management_company_id.company_id',store=True,readonly=True,index=True)

    # -------------------------
    # STATUT METIER
    # -------------------------
    validation_date = fields.Datetime(readonly=True)
    validated_by = fields.Many2one('res.users', readonly=True)
    rejection_reason = fields.Text()
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('kyc_pending', 'KYC en cours'),
        ('validated', 'Validé'),
        ('rejected', 'Rejeté'),
        ('suspended', 'Suspendu'),
    ], default='draft', tracking=True)


    # -------------------------
    # PARAMÈTRES FONDS
    # -------------------------
    currency_id = fields.Many2one('res.currency',related='company_id.currency_id',store=True)
    compliance_status = fields.Selection(related='investor_id.compliance_status', compute='_compute_compliance_status', store=True)
    kyc_score = fields.Integer(related='investor_id.kyc_score',string='Score KYC')
    _investor_id_fund_uniq = models.Constraint('unique(investor_id, mandate_id)','Un investisseur est déjà rattaché à ce fonds.')

    # =========================
    # ACTIONS METIER
    # =========================

    def action_submit_kyc(self):
        """Passer en KYC en cours"""
        for rec in self:
            if rec.state != 'draft':
                continue

            if rec.investor_id.compliance_status not in ('pending_review', 'compliant'):
                raise UserError(
                    _("Le dossier KYC de l’investisseur n’est pas prêt.")
                )

            rec.state = 'kyc_pending'

    def action_validate(self):
        """Validation définitive pour le fonds"""
        for rec in self:
            if rec.state != 'kyc_pending':
                continue

            investor = rec.investor_id

            if investor.compliance_status != 'compliant':
                raise UserError(_("Investisseur non conforme KYC / AML."))

            rec.write({
                'state': 'validated',
                'validation_date': fields.Datetime.now(),
                'validated_by': self.env.user.id,
            })

            rec._create_accounts_for_fund()

    def action_reject(self):
        """Rejet pour le fonds"""
        for rec in self:
            if rec.state != 'kyc_pending':
                continue
            rec.state = 'rejected'

    def action_suspend(self):
        """Suspension d’un investisseur déjà validé"""
        for rec in self:
            if rec.state != 'validated':
                continue
            rec.state = 'suspended'

    # =========================
    # LOGIQUE COMPTES
    # =========================

    def _create_accounts_for_fund(self):
        """Créer les comptes espèces et titres après validation"""
        self.ensure_one()

        Cash = self.env['efund.account.cash']

        # Sécurité : éviter les doublons
        if Cash.search([
            ('investor_id', '=', self.investor_id.id),
            ('mandate_id', '=', self.mandate_id.id),
        ], limit=1):
            return

        cash_account = Cash.create({
            'name': f"Compte Espèces-{self.mandate_id.name}-{self.full_name or self.name or 'Investor'}",
            'investor_id': self.investor_id.id,
            'mandate_id': self.mandate_id.id,
            'date_opened': fields.Date.today(),
            'account_number': self._generate_cash_account_number(),
        })

        self.message_post(
            body=_(
                "Comptes créés automatiquement :<br/>"
                "- Compte espèces : %s<br/>"

            ) % (cash_account.account_number)
        )

    # =========================
    # GÉNÉRATION DES NUMÉROS
    # =========================

    def _generate_cash_account_number(self):
        self.ensure_one()
        inv_type = "IND"
        if self.partner_id and self.partner_id.company_type == "company":
            inv_type = "COR"
        return f"ES-{inv_type}-{self.mandate_id.code or self.mandate_id.id}-{str(self.investor_id.id).zfill(6)}"

