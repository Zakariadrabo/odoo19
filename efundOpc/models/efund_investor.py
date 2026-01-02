# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from datetime import date
import json, logging

_logger = logging.getLogger(__name__)

class FundInvestor(models.Model):
    _name = "efund.investor"
    _description = "Investor / Porteur - KYC record"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    partner_id = fields.Many2one('res.partner',string="Partner",required=False,ondelete='cascade',domain="[('is_investor', '=', True)]",)
    company_id = fields.Many2one('res.company', string="Context Company (Fund)", index=True)

    # store the name for easier reading (populated from partner)
    name = fields.Char(related="partner_id.name", store=True, readonly=True)

    #########################################
    # Obligation de connaissance du client
    ########################################
    investor_type = fields.Selection([("individual", "Personne physique"), ("company", "Personne morale"), ],
                                     string="Type de client", default="individual", required=True)

    #Personne physique
    civilite = fields.Selection([('Mr', 'Monsieur'), ('Mrs', 'Madame')])
    full_name = fields.Char(string="Nom complet", compute='_compute_full_name', store=True)
    nom = fields.Char(string="Nom", store=True)
    prenom = fields.Char(string="Prénom", store=True)
    birthdate = fields.Date(string="Date de naissance")
    birthplace = fields.Char(string="Lieu de naissance")
    birth_country_id = fields.Many2one("res.country", string="Pays de naissance")
    sex = fields.Selection([('male', 'Homme'), ('female', 'Femme')], string="Sexe")

    #Personne Morale
    # Identité Juridique
    company_name = fields.Char(string="Raison sociale")
    company_short_name = fields.Char(string="Sigle")
    legal_form = fields.Selection([('sa', 'Société anonyme'),('sas','Société anonyme simplifiée'),('sarl', 'Société à responsabilité limitée'),
    ], default='sa', string='forme juridique')
    license_number = fields.Char(string="N° Immatriculation")
    creation_date = fields.Date(string="Date de création")
    company_address = fields.Char(string="Adresse siège social")
    company_town = fields.Char(string="Ville siège social")
    company_country_id = fields.Many2one("res.country", string="Siège social")
    identical_address = fields.Boolean(string="Adresse identique", default=True)
    company_direction_address = fields.Char(string="Adresse Direction")
    company_direction_town = fields.Char(string="Ville Direction")
    company_direction_country_id = fields.Many2one("res.country", string="Pays Direction")


    # Création et Agrément

    insae_number = fields.Char(string="N° INSAE")


    # lifecycle / compliance
    status = fields.Selection([('draft', 'Brouillon'),('kyc_pending', 'KYC en attente'),('kyc_approved', 'KYC approuvé'),
        ('kyc_rejected', 'KYC refusé'),('archived', 'Archivé')], default='draft', tracking=True)
    kyc_level = fields.Selection([('low','Low'),('medium','Medium'),('high','High')], default='low')
    kyc_score = fields.Integer(default=0)
    kyc_last_update = fields.Datetime()
    kyc_operator_id = fields.Many2one('res.users', string="KYC Operator")
    pep_flag = fields.Boolean(default=False)
    sanctions_flag = fields.Boolean(default=False)
    risk_category = fields.Char()
    whitelisted = fields.Boolean(default=False)
    notes = fields.Text()

    # relations
    document_ids = fields.One2many('efund.kyc.document', 'investor_id', string="KYC Documents")
    kyc_check_ids = fields.One2many('efund.kyc.check', 'investor_id', string="KYC Checks")
    aml_alert_ids = fields.One2many('efund.aml.alert', 'investor_id', string="AML Alerts")
    active = fields.Boolean(default=True)

    fund_investor_ids = fields.One2many('efund.fund.investor','investor_id',string="Fonds")
    mandate_investor_ids = fields.One2many('efund.mandate.investor','investor_id',string="Mandats")

    cash_account_ids = fields.One2many('efund.account.cash','investor_id',string="Comptes espèces")
    part_account_ids = fields.One2many('efund.account.part','investor_id',string="Comptes titres")

    # compliance computed fields
    compliance_status = fields.Selection([('compliant','Compliant'),('non_compliant','Non-Compliant'),
        ('medium_risk','Medium Risk'),('high_risk','High Risk'),('pending_review','Pending Review'),
    ], compute='_compute_compliance_status', store=True)
    compliance_score = fields.Integer(compute='_compute_compliance_status', store=True)
    last_compliance_check = fields.Datetime()
    compliance_notes = fields.Text()

    # Personal info (allow using form to create partner data)


    minor = fields.Boolean(string="Mineur ?")
    nationality = fields.Char(string="Nationalité")

    tranche = fields.Selection([("<55","Jusqu'à 55ans"),("56T74","56-74"),(">75",">75")])

    country_id = fields.Many2one("res.country", string="Pays")
    city = fields.Char(string="Ville")
    address = fields.Char(string="Adresse")
    language_id = fields.Many2one("res.lang",string="Langue")
    marital_status=fields.Selection([('single','Célibataire'),('married','Marié(e)'),('divorced','Divorcé(e)'),('widowed','Veuf/veuve')])

    # Situation professionnelle
    socio_professional_category = fields.Char(string="Catégorie socio-professionnelle")
    profession = fields.Char(string="Profession")
    function = fields.Char(string="Fonction")
    activity_sector = fields.Char(string="Secteur d’activité")


    # Financial profile
    estimation = fields.Selection([('M5','<5M'),('E5','5-50M'),('P5','>50M')], string="Patrimoine")
    revenu = fields.Selection([('M5','<5M'),('E5','5-10M'),('P5','>10M')], string="Revenu annuel")
    montant_mois = fields.Integer(string="Montant estimé transactions / mois")
    periodicite = fields.Selection([('Monthly','Mensuel'),('Quarterly','Trimestriel'),('Semi-Annual','Semestriel'),('Annual','Annuel')])

    origine = fields.Selection([('salary','Salaire'),('investment','Investissement'),('legacy','Héritage'),('savings','Epargne'),('other','Autre')])
    activite = fields.Selection([('employee','Salarié'),('liberal','Profession libérale'),('business','Entrepreneur'),('other','Autre')])
    objectif = fields.Selection([('investment','Investissement'),('savings','Epargne'),('transactions','Transactions'),('other','Autre')])

    pep = fields.Selection([('Yes','Oui'),('No','Non')], string="PEP (info)")
    violation = fields.Selection([('Yes','Oui'),('No','Non')], string="Antécédents")

    # Accounts relations
    account_part_ids = fields.One2many('efund.account.part', 'investor_id', string='Comptes Parts / Actions')
    account_cash_ids = fields.One2many('efund.account.cash', 'investor_id', string='Comptes Espèces')

    # computed helper: available cash (sum of active cash accounts balances)
    available_cash = fields.Monetary(
        string='Available Cash (sum)',
        currency_field='company_currency_id',
        compute='_compute_available_cash',
        store=True
    )
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True, readonly=True)

    ## Objet de smart bouton
    subscription_count = fields.Integer(compute='_compute_subscription_count',string="Souscriptions")
    deposit_count = fields.Integer(compute='_compute_deposit_count', string="Déposit")
    redemption_count = fields.Integer(compute='_compute_redemption_count', string="Rachat")
    withdraw_count = fields.Integer(compute='_compute_withdraw_count', string="Retrait Cash")

    def _compute_full_name(self):
        for rec in self:
            rec.full_name = f"{rec.prenom} {rec.nom}" if rec.prenom or rec.nom else ""

    @api.onchange(
        'identical_address',
        'company_address',
        'company_town',
        'company_country_id'
    )
    def _onchange_identical_address(self):
        for rec in self:
            if rec.identical_address:
                rec.company_direction_address = rec.company_address
                rec.company_direction_town = rec.company_town
                rec.company_direction_country_id = rec.company_country_id

    # Sécurité : limiter la création manuelle
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get("partner_id"):
                partner_vals = self._prepare_partner_vals(vals)
                partner = self.env["res.partner"].create(partner_vals)
                vals["partner_id"] = partner.id

        investors = super().create(vals_list)

        # Marquer le partner comme investisseur
        for investor in investors:
            if investor.partner_id:
                investor.partner_id.write({"is_investor": True})

        return investors

    def _prepare_partner_vals(self, vals):
        """Convertit les champs EfundInvestor → res.partner proprement."""
        return {
            "name": vals.get("full_name") or _("New Investor"),
            "email": vals.get("email"),
            "phone": vals.get("phone"),
            "street": vals.get("address"),
            "city": vals.get("city"),
            "country_id": vals.get("country_id"),
            "is_investor": True,
        }

    # -------------------------
    # BUSINESS / COMPUTED
    # -------------------------
    @api.depends('account_cash_ids.balance', 'account_cash_ids.state')
    def _compute_available_cash(self):
        for rec in self:
            total = 0.0
            for acc in rec.account_cash_ids.filtered(lambda a: a.state == 'active'):
                total += float(acc.balance or 0.0)
            rec.available_cash = total

    @api.depends('document_ids', 'kyc_score', 'pep_flag', 'sanctions_flag', 'kyc_last_update', 'document_ids.expiry_date')
    def _compute_compliance_status(self):
        for rec in self:
            score = 100
            status = 'compliant'
            required_docs = ['id_card', 'proof_of_address']
            existing = rec.document_ids.mapped('document_type')
            missing = [d for d in required_docs if d not in existing]
            if missing:
                score -= 30 * len(missing)
                status = 'non_compliant'
            # expired docs
            today = date.today()
            expired = rec.document_ids.filtered(lambda d: d.expiry_date and d.expiry_date < today and d.status != 'expired')
            if expired:
                score -= 20
                status = 'non_compliant'
            # risk flags
            if rec.sanctions_flag:
                score -= 50
                status = 'high_risk'
            elif rec.pep_flag and not rec.whitelisted:
                score -= 25
                status = 'medium_risk'
            if rec.kyc_score >= 70:
                score -= rec.kyc_score - 70
                status = 'medium_risk' if rec.kyc_score < 90 else 'high_risk'
            if rec.kyc_last_update:
                try:
                    days = (today - fields.Date.to_date(rec.kyc_last_update)).days
                    if days > 365:
                        score -= 15
                        status = 'non_compliant'
                except Exception:
                    pass
            rec.compliance_score = max(0, int(score))
            rec.compliance_status = status

    # -------------------------
    # ACTIONS / UTILITIES
    # -------------------------
    def action_create_investor_accounts(self):
        """Créer automatiquement compte titre + compte espèces."""
        self.ensure_one()
        if self.account_part_ids or self.account_cash_ids:
            raise UserError(_("Cet investisseur possède déjà des comptes."))

        country = (self.country_id.code or "XX").upper()
        inv_type = "IND"
        # if partner is a company
        if self.partner_id and self.partner_id.company_type == "company":
            inv_type = "COR"
        inv_id_fmt = str(self.id).zfill(4)
        seq_part = str(len(self.account_part_ids) + 1).zfill(3)
        account_part_number = f"PT-{country}-{inv_type}-{inv_id_fmt}-{seq_part}"
        part = self.env['efund.account.part'].create({
            'name': f"Compte Titre - {self.full_name or self.name or 'Investor'}",
            'investor_id': self.id,
            'account_number': account_part_number,
            'total_parts': 0,
            'state': 'active',
        })
        seq_cash = str(len(self.account_cash_ids) + 1).zfill(3)
        account_cash_number = f"ES-{country}-{inv_type}-{inv_id_fmt}-{seq_cash}"
        cash = self.env['efund.account.cash'].create({
            'name': f"Compte Espèces - {self.full_name or self.name or 'Investor'}",
            'investor_id': self.id,
            'account_number': account_cash_number,
            'balance': 0,
            'state': 'active',
        })
        _logger.info("Comptes créés: %s / %s", account_part_number, account_cash_number)
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Comptes créés"),
                'message': _("Le compte titre et le compte espèces ont été créés avec succès."),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_open_cash_deposit_wizard(self):
        self.ensure_one()
        if not self.account_cash_ids:
            raise UserError(_("Aucun compte espèces n’est associé à cet investisseur."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Dépôt sur compte espèces"),
            "res_model": "efund.cash.deposit.wizard",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_investor_id": self.id,
                "default_cash_account_id": self.account_cash_ids[0].id,
                "default_currency_id": self.company_id.currency_id.id,
                "default_date_operation": fields.Date.context_today(self),
            }
        }

    def action_open_subscription_wizard(self):
        self.ensure_one()
        if not self.account_cash_ids:
            raise UserError(_("L'investisseur n'a pas de compte espèces."))
        return {
            "type": "ir.actions.act_window",
            "name": _("Nouvelle souscription"),
            "res_model": "efund.fund.subscription",
            "view_mode": "form",
            "target": "new",
            "context": {
                "default_investor_id": self.id,
                "default_cash_account_id": self.account_cash_ids[0].id,
                "default_company_id": self.company_id.id,
                "default_currency_id": self.company_id.currency_id.id,
            }
        }

    # existing KYC/AML scheduling & checks kept (you already had them)
    def _schedule_initial_screening(self):
        for rec in self:
            rec._run_screening()

    def _run_screening(self):
        for rec in self:
            rec.sudo().write({'pep_flag': False, 'sanctions_flag': False})
            try:
                result = self._mocked_external_checks()
                rec.sudo().write({'pep_flag': result.get('pep', False), 'sanctions_flag': result.get('sanctions', False)})
            except Exception:
                _logger.exception("Screening failed for investor %s", rec.id)
            # compute score via pluggable engine (keep existing call pattern)
            try:
                score = self.env['fund.aml.engine'].compute_score_for_investor(rec.id)
            except Exception:
                score = 0
            rec.sudo().write({'kyc_score': score, 'kyc_last_update': fields.Datetime.now()})
            if rec.kyc_score >= 80 or rec.sanctions_flag:
                rec.sudo().write({'status': 'kyc_pending', 'kyc_level': 'high'})
                if rec.sanctions_flag:
                    self.env['fund.aml.alert'].create({
                        'investor_id': rec.id,
                        'fund_id': rec.company_id.id,
                        'trigger': 'sanctions_match',
                        'severity': 'critical',
                        'status': 'new',
                        'notes': _('Sanctions match detected during initial screening.')
                    })
            elif rec.kyc_score >= 40:
                rec.sudo().write({'status': 'kyc_pending', 'kyc_level': 'medium'})
            else:
                rec.sudo().write({'status': 'kyc_approved', 'kyc_level': 'low'})

    def _mocked_external_checks(self):
        name = (self.partner_id.name or "").lower() if self.partner_id else (self.full_name or "").lower()
        return {'pep': 'prez' in name, 'sanctions': 'blocked' in name}

    def action_check_kyc_compliance(self):
        # keep your existing implementation (omitted here for brevity)
        return super(FundInvestor, self).action_check_kyc_compliance() if hasattr(super(), 'action_check_kyc_compliance') else {}

    def action_create_aml_alert(self):
        _logger.info("test")

        # Workflow

    def action_submit_kyc(self):
        for rec in self:
            if rec.status != "draft":
                raise UserError("Seuls les investisseurs en draft peuvent être soumis au KYC.")
            rec.status = "kyc_pending"

    def action_approve_kyc(self):
        for rec in self:
            if rec.status != "kyc_pending":
                raise UserError("Seuls les investisseurs en attente peuvent être approuvés.")
            rec.status = "kyc_approved"

    def action_reject_kyc(self):
        for rec in self:
            if rec.status != "kyc_pending":
                raise UserError("Seuls les investisseurs en attente peuvent être rejetés.")
            rec.status = "kyc_rejected"

    def action_archive(self):
        for rec in self:
            rec.status = "archived"

    def _check_kyc_approved(self):
        for rec in self:
            if rec.status != 'kyc_approved':
                raise UserError("Le client doit être KYC validé pour effectuer cette action.")



    def _compute_subscription_count(self):
        Subscription = self.env['efund.fund.subscription']
        for investor in self:
            investor.subscription_count = Subscription.search_count([
                ('investor_id', '=', investor.id),
                ('state', '!=', 'accounted')

            ])

    def _compute_deposit_count(self):
        Deposit = self.env['efund.fund.cash.deposit']
        for investor in self:
            investor.deposit_count = Deposit.search_count([
                ('investor_id', '=', investor.id),
                ('state', '!=', 'accounted')

            ])

    def _compute_redemption_count(self):
        Redemption = self.env['efund.fund.redemption']
        for investor in self:
            investor.redemption_count = Redemption.search_count([
                ('investor_id', '=', investor.id),
                ('state', '!=', 'accounted')

            ])

    def _compute_withdraw_count(self):
        Withdraw = self.env['efund.fund.cash.withdraw']
        for investor in self:
            investor.withdraw_count = Withdraw.search_count([
                ('investor_id', '=', investor.id),
                ('state', '!=', 'accounted')

            ])

    def action_open_subscriptions(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Souscriptions',
            'res_model': 'efund.fund.subscription',
            'view_mode': 'list,form',
            'domain': [('investor_id', '=', self.id)],
            'context': {
                'default_investor_id': self.id,
                'search_default_investor_id': self.id,
            }
        }
    def action_open_deposit(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Souscriptions',
            'res_model': 'efund.fund.cash.deposit',
            'view_mode': 'list,form',
            'domain': [('investor_id', '=', self.id)],
            'context': {
                'default_investor_id': self.id,
                'search_default_investor_id': self.id,
            }
        }
    def action_open_redemption(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Souscriptions',
            'res_model': 'efund.fund.redemption',
            'view_mode': 'list,form',
            'domain': [('investor_id', '=', self.id)],
            'context': {
                'default_investor_id': self.id,
                'search_default_investor_id': self.id,
            }
        }
    def action_open_withdraw(self):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Souscriptions',
            'res_model': 'efund.fund.cash.withdraw',
            'view_mode': 'list,form',
            'domain': [('investor_id', '=', self.id)],
            'context': {
                'default_investor_id': self.id,
                'search_default_investor_id': self.id,
            }
        }



