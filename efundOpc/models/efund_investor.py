# -*- coding: utf-8 -*-
import re
from logging import setLoggerClass

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

    partner_id = fields.Many2one('res.partner', string="Partner", required=False, ondelete='cascade',
                                 domain="[('is_investor', '=', True)]", )
    company_id = fields.Many2one('res.company', string="Context Company (Fund)", index=True)

    # store the name for easier reading (populated from partner)
    name = fields.Char(related="partner_id.name", store=True, readonly=True)

    #########################################
    # Obligation de connaissance du client
    ########################################
    investor_type = fields.Selection([("individual", "Personne physique"), ("company", "Personne morale"), ],
                                     string="Type de client", default="individual", required=True)

    # Personne physique
    civilite = fields.Selection([('Mr', 'Monsieur'), ('Mrs', 'Madame')])
    full_name = fields.Char(string="Nom complet", compute="_compute_full_name", store=True)
    nom = fields.Char(string="Nom", store=True)
    prenom = fields.Char(string="Prénom", store=True)
    nom_jeune_fille = fields.Char(string="Nom de Jeune", store=True)
    birthdate = fields.Date(string="Date de naissance")
    birthplace = fields.Char(string="Lieu de naissance")
    birth_country_id = fields.Many2one("res.country", string="Pays de naissance")
    sex = fields.Selection([('male', 'Homme'), ('female', 'Femme')], string="Sexe")
    country_id = fields.Many2one("res.country", string="Pays de résidence habituelle")
    address_place = fields.Char(string="Ville / Codepostal")
    address = fields.Char(string="Adresse de résidence principale")
    marital_status = fields.Selection(
        [('single', 'Célibataire'), ('married', 'Marié(e)'), ('divorced', 'Divorcé(e)'), ('widowed', 'Veuf/veuve')],
        string="Statut matrimonial")

    contact_adress = fields.Char(string="Adresse de correspondance (si différent)")
    other_nationnality = fields.Char(string="Autres Nationnalité")
    employer = fields.Char(string="Employeur")
    employer_address = fields.Char(string="Adresse de l'employeur")

    # Personne Morale
    company_name = fields.Char(string="Raison sociale")
    company_short_name = fields.Char(string="Sigle")
    legal_form = fields.Selection([('sa', 'Société Anonyme (SA)'), ('sas', 'Société par Actions Simplifiée (SAS)'),
                                   ('sarl', 'Société à Responsabilité Limitée (SARL)'),
                                   ('snc', 'Société en Nom Collectif (SNC)'),
                                   ('scs', 'Société en Commandite Simple (SCS)'),
                                   ('gie', "Groupement d'Intérêt Économique (GIE)"),
                                   ('sep', 'Société en Participation (SEP)'), ('coop', 'Société Coopérative'),
                                   ('other', 'Autre')], string="Forme Juridique", default='sa',
                                  help="Forme juridique selon le droit OHADA")
    license_number = fields.Char(string="N° Immatriculation")
    creation_date = fields.Date(string="Date de création")
    company_address = fields.Char(string="Adresse siège social")
    company_town = fields.Char(string="Ville siège social")
    company_country_id = fields.Many2one("res.country", string="Siège social")
    identical_address = fields.Boolean(string="Adresse identique", default=True)
    company_direction_address = fields.Char(string="Adresse Direction")
    company_direction_town = fields.Char(string="Ville Direction")
    company_direction_country_id = fields.Many2one("res.country", string="Pays Direction")
    social_object = fields.Char(string="Social")
    is_beneficiaire_effectif = fields.Boolean(string="Bénéficiaire", default=False)
    beneficiaire_effectif = fields.Char(string="Bénéficiaire effectif")
    registration_country_id = fields.Many2one("res.country", string="Pays d’immatriculation")
    company_duration_years = fields.Integer(string="Durée de la société (ans)")
    website = fields.Char(string="Site internet")
    main_activity_countries = fields.Char(string="Pays principaux activités")
    annual_turnover_range = fields.Selection(
        [("lt_100", "< 100 M FCFA"), ("100_500", "100 – 500 M FCFA"), ("500_2b", "500 M – 2 Mds FCFA"),
         ("gt_2b", "> 2 Mds FCFA"), ], string="Chiffre d’affaires annuel estimé")
    main_revenue_sources = fields.Char(string="Principales sources de revenus")
    funds_origin_pm = fields.Selection(
        [("operating", "Revenus d’exploitation"), ("capital", "Capital"), ("loan", "Emprunts"), ("other", "Autre"), ],
        string="Origine principale des fonds investis")
    funds_origin_pm_other = fields.Char(string="Autre origine des fonds")
    expected_operations_volume = fields.Selection(
        [("lt_100", "< 100 M FCFA"), ("100_500", "100 – 500 M FCFA"), ("500_2b", "500 M – 2 Mds FCFA"),
         ("gt_2b", "> 2 Mds FCFA"), ], string="Volume prévisionnel des opérations (annuel)")

    # infos commune
    account_type_titre = fields.Selection(
        [("00", "Ordinaire"), ("01", "Géré"), ("02", "Dédié à la bourse en ligne"), ("08", "titre nanti")],
        string="Compte Titre")
    account_type_espece = fields.Selection(
        [("10", "Ordinaire"), ("11", "Géré"), ("12", "Dédié à la bourse en ligne"), ("18", "titre nanti")],
        string="Compte Espèce")
    investor_category = fields.Selection(
        [("01", "Client Ordinaire"), ("02", "Non Client"), ("03", "Compte propre"), ("04", "Compte Emetteur")],
        string="Type d'investisseur")
    account_investor_type = fields.Selection(
        [("10", "Personne physique CEMAC"), ("11", "Personne physique Non CEMAC"), ("20", "Personne Morale CEMAC"),
         ("21", "Personne Morale Non CEMAC"), ("22", "Institution Financière CEMAC")], string="Type d'investisseur")
    account_order = fields.Char(string="N° d'Ordre")
    name_bank = fields.Char(string="Nom de la banque")
    bank_address = fields.Char(string="Adresse de la banque")
    account_number = fields.Char(string="Numéro de compte")
    iban = fields.Char(string="IBAN")
    swift_bic = fields.Char(string="SWIFT/BIC")
    entry_relation_date = fields.Date(string="Date d'entrée en relation")
    business_object_relation = fields.Char(string="Nature de la relation d'affaire")
    fund_country_origin = fields.Many2one("res.country", string="Pays d'origine des fonds")
    fund_country_destination = fields.Many2one("res.country", string="Pays de destination des fonds")
    market_knowledge = fields.Selection(
        [('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), ('6', '6'), ('7', '7'), ],
        string='Connaissance du marché', widget='Priority')
    activity_knowledge = fields.Selection(
        [('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), ('6', '6'), ('7', '7'), ],
        string='Connaissance de l\'activité', widget='Priority')
    risk_level_acceptable = fields.Selection(
        [('1', '1'), ('2', '2'), ('3', '3'), ('4', '4'), ('5', '5'), ('6', '6'), ('7', '7'), ],
        string='Niveau de risque acceptable', widget='Priority')
    email = fields.Char(string="Adresse Email")
    mobility_phone = fields.Char(string="Téléphone (mobile)")
    place_phone = fields.Char(string="Téléphone (domicile)")

    # lifecycle / compliance
    status = fields.Selection(
        [('draft', 'Brouillon'), ('kyc_approved', 'KYC approuvé'),('kyc_pending', 'KYC en attente'),('kyc_rejected', 'KYC refusé'), ('archived', 'Archivé')], default='draft', tracking=True)
    kyc_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], default='low')
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
    represented_person_ids = fields.One2many('efund.investor.represented', 'investor_id',
                                             string="Personnes représentées")

    heirs_person_ids = fields.One2many('efund.investor.heirs', 'investor_id',
                                       string="Héritiés et personne à contacter")
    intervention_mode_ids = fields.One2many('efund.investor.intervention.mode', 'investor_id', string="Investisseur")
    represented_company_ids = fields.One2many('efund.investor.company.represented', 'investor_id',
                                              string="Réprésentant de la société")

    active = fields.Boolean(default=True)

    fund_investor_ids = fields.One2many('efund.fund.investor', 'investor_id', string="Fonds")
    mandate_investor_ids = fields.One2many('efund.mandate.investor', 'investor_id', string="Mandats")

    cash_account_ids = fields.One2many('efund.investor.cash_account', 'investor_id', string="Comptes espèces")
    part_account_ids = fields.One2many('efund.investor.part_account', 'investor_id', string="Comptes titres")

    # compliance computed fields
    compliance_status = fields.Selection([('compliant', 'Compliant'), ('non_compliant', 'Non-Compliant'),
                                          ('medium_risk', 'Medium Risk'), ('high_risk', 'High Risk'),
                                          ('pending_review', 'Pending Review'),
                                          ], compute='_compute_compliance_status', store=True)
    compliance_score = fields.Integer(compute='_compute_compliance_status', store=True)
    last_compliance_check = fields.Datetime()
    compliance_notes = fields.Text()

    # Personal info (allow using form to create partner data)
    minor = fields.Boolean(string="Mineur ?")
    nationality = fields.Many2one("res.country", string="Nationalité principale")
    tranche = fields.Selection([("<55", "Jusqu'à 55ans"), ("56T74", "56-74"), (">75", ">75")])
    language_id = fields.Many2one("res.lang", string="Langue")

    # Situation professionnelle
    socio_professional_category = fields.Char(string="Catégorie socio-professionnelle")
    profession = fields.Char(string="Profession")
    function = fields.Char(string="Fonction")
    activity_sector = fields.Selection(
        [('agriculture', 'Agriculture'), ('industrie', 'Industrie'), ('batiment', 'Bâtiment et Travaux Publics'),
         ('commerce', 'Commerce'), ('transport', 'Transport et Logistique'), ('tourisme', 'Tourisme et Hôtellerie'),
         ('sante', 'Santé et Social'),
         ('education', 'Éducation et Formation'), ('finances', 'Finances et Assurance'), ('immobilier', 'Immobilier'),
         ('services', 'Services aux Entreprises'),
         ('tic', 'Technologies de l\'Information et Communication'), ('culture', 'Culture et Loisirs'),
         ('energie', 'Énergie et Environnement'),
         ('autre', 'Autre'), ], string="Secteur d'activité", default='finances')

    # Financial profile
    estimation = fields.Selection([('M5', '<5M'), ('E5', '5-50M'), ('P5', '>50M')], string="Patrimoine")
    revenu = fields.Selection([('M5', '<5M'), ('E5', '5-10M'), ('P5', '>10M')], string="Revenu annuel")
    montant_mois = fields.Integer(string="Montant estimé transactions / mois")
    periodicite = fields.Selection(
        [('Monthly', 'Mensuel'), ('Quarterly', 'Trimestriel'), ('Semi-Annual', 'Semestriel'), ('Annual', 'Annuel')],
        string="Fréquence des souscriptions")

    origine = fields.Selection(
        [('salary', 'Salaire'), ('investment', 'Revenus d\'activités'), ('estate', 'Revenus immobiliers'),
         ('legacy', 'Héritage / Donation'), ('savings', 'Epargne'), ('other', 'Autre')], string="Origine des fonds")
    other_origine = fields.Char(string="Autre origine")
    activite = fields.Selection(
        [('employee', 'Salarié'), ('liberal', 'Profession libérale'), ('business', 'Entrepreneur'),
         ('etudiant', 'Etudiant'), ('retraite', 'Rétraité'), ('sans_emploi', 'Sans emploi'), ('other', 'Autre')],
        string="Situation professionnelle")
    other_activite = fields.Char(string="Autre activité")
    objectif = fields.Selection(
        [('investissement', 'Investissement'), ('savings', 'Epargne'), ('transactions', 'Transactions'),
         ('other', 'Autre')], string="Objectif financier")
    other_objectif = fields.Char(string="Autre objectif")

    pep = fields.Selection([('Yes', 'Oui'), ('No', 'Non')], string="PEP (info)")
    violation = fields.Selection([('Yes', 'Oui'), ('No', 'Non')], string="Antécédents")

    # Accounts relations
    account_part_ids = fields.One2many('efund.investor.part', 'investor_id', string='Comptes Parts / Actions')
    account_cash_ids = fields.One2many('efund.investor.cash', 'investor_id', string='Comptes Espèces')

    # computed helper: available cash (sum of active cash accounts balances)
    available_cash = fields.Monetary(
        string='Available Cash (sum)',
        currency_field='company_currency_id',
        compute='_compute_available_cash',
        store=True
    )
    company_currency_id = fields.Many2one('res.currency', related='company_id.currency_id', store=True, readonly=True)

    ## Objet de smart bouton
    subscription_count = fields.Integer(compute='_compute_subscription_count', string="Souscriptions")
    deposit_count = fields.Integer(compute='_compute_deposit_count', string="Déposit")
    redemption_count = fields.Integer(compute='_compute_redemption_count', string="Rachat")
    withdraw_count = fields.Integer(compute='_compute_withdraw_count', string="Retrait Cash")

    # image
    image = fields.Binary(string="Photo / Logo",
                          help="Photo pour une personne physique, logo pour une personne morale",
                          attachment=True, store=True)
    image_1920 = fields.Image(
        string="Photo / Logo",
        max_width=1920,
        max_height=1920
    )

    # Rachide
    # --- Informations générales PM ---
    registration_country_id = fields.Many2one("res.country", string="Pays d’immatriculation")
    company_duration_years = fields.Integer(string="Durée de la société (ans)")
    company_zip = fields.Char(string="Code postal")
    website = fields.Char(string="Site internet")
    phone = fields.Char(string="Numéro de Téléphone")
    activite_sector = fields.Selection([('finance', 'Services Financiers'), ('tech', 'Nouvelles Technologies & IA'),
                                        ('green', 'Transition Écologique'),
                                        ('industry', 'Industrie & Transport'), ('agri', 'Agro-industrie'),
                                        ('public', 'Services Publics'),
                                        ('other', 'Autre')], string="Secteur d'activité")
    main_activity_countries = fields.Many2many("res.country", "efund_company_activity_country_rel", "investor_id",
                                               "country_id", string="Pays principal d’activité")

    # --- Informations financières PM ---
    annual_turnover_range = fields.Selection(
        [("lt_100", "< 100 M FCFA"), ("100_500", "100 – 500 M FCFA"), ("500_2b", "500 M – 2 Mds FCFA"),
         ("gt_2b", "> 2 Mds FCFA"), ], string="Chiffre d’affaires annuel estimé")
    main_revenue_sources = fields.Char(string="Principales sources de revenus")
    funds_origin_pm = fields.Selection(
        [("operating", "Revenus d’exploitation"), ("capital", "Capital"), ("loan", "Emprunts"), ("other", "Autre"), ],
        string="Origine principale des fonds investis")
    funds_origin_pm_other = fields.Char(string="Autre origine des fonds")
    expected_operations_volume = fields.Selection(
        [("lt_100", "< 100 M FCFA"), ("100_500", "100 – 500 M FCFA"), ("500_2b", "500 M – 2 Mds FCFA"),
         ("gt_2b", "> 2 Mds FCFA"), ], string="Volume prévisionnel des opérations (annuel)")

    # --- Connaissance financière PM ---
    market_knowledge_pm = fields.Integer(tring="Connaissance du marché (PM)")
    activity_knowledge_pm = fields.Integer(string="Connaissance de l’activité (PM)")
    risk_tolerance_pm = fields.Integer(string="Niveau de risque acceptable (PM)")
    business_relation_type = fields.Selection(
        [('souscription_opcvm', 'Souscription OPCVM'), ('gestion_mandat', 'Gestion sous mandat'),
         ('conseil_invest', 'Conseil en investissement'), ('autre', 'Autre')], string="Type de relation envisagée",
        default='souscription_opcvm')
    business_relation_type_autre = fields.Char(string="Préciser (Autre)",
                                               help="Saisir le type de relation si 'Autre' est sélectionné")
    fund_origin_country = fields.Many2one("res.country", string="Pays d’origine habituelle des fonds ")

    # legal_representative_ids = fields.One2many("efund.company.legal.representative", "investor_id", string="Représentant légal")

    @api.depends('nom', 'prenom')
    def _compute_full_name(self):
        for rec in self:
            rec.full_name = f"{rec.prenom} {rec.nom}" if rec.prenom or rec.nom else ""

    @api.constrains('email')
    def _check_email_format(self):
        email_regex = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")
        for record in self:
            if record.email and not email_regex.match(record.email):
                raise ValidationError(
                    "L'adresse e-mail '%s' n'est pas valide. Veuillez utiliser un format comme 'utilisateur@domaine.com'." % record.email)

    @api.onchange('nom', 'prenom')
    def _onchange_nom_prenom(self):
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
            "name": vals.get("nom") + ' ' + vals.get("prenom") if vals.get(
                "investor_type") == 'individual' else vals.get("company_name"),
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

    @api.depends('document_ids', 'kyc_score', 'pep_flag', 'sanctions_flag', 'kyc_last_update',
                 'document_ids.expiry_date')
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
            expired = rec.document_ids.filtered(
                lambda d: d.expiry_date and d.expiry_date < today and d.status != 'expired')
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
    def create_investor_accounts(self):
        """Créer automatiquement compte titre + compte espèces."""
        self.ensure_one()
        if self.account_part_ids or self.account_cash_ids:
            raise UserError(_("Cet investisseur possède déjà des comptes."))

        company_code = self.env['efund.company.number'].search([], limit=1)
        if not company_code:
            raise UserError(_("Aucun code de teneur de compte trouvé pour la société."))
        _logger.info(
            f"***** Company code found: {company_code.code_teneur_compte}, agence: {company_code.code_agence}, ")
        _logger.info(f"***** Account type: {self.account_type_titre or 'account_type_titre'}, {self.account_type_espece or 'account_type_espece'}, {self.account_investor_type or 'account_investor_type'}, {self.account_order or 'account_order'}")
        account_number_titre = company_code.code_teneur_compte + company_code.code_agence + "00" + self.account_type_titre + self.account_investor_type + self.account_order
        account_number_espece = company_code.code_teneur_compte + company_code.code_agence + "10" + self.account_type_espece + self.account_investor_type + self.account_order

        # Creation des comptes
        self.env['efund.investor.part_account'].create({
            'name': f"Compte Titre - {self.full_name or self.name or 'Investor'}",
            'investor_id': self.id,
            'account_number': account_number_titre,
            'total_parts': 0,
            'state': 'active',
        })

        self.env['efund.investor.cash_account'].create({
            'name': f"Compte Espèces - {self.full_name or self.name or 'Investor'}",
            'investor_id': self.id,
            'account_number': account_number_espece,
            'balance': 0,
            'state': 'active',
        })

    def action_create_investor_accounts(self):
        """Créer automatiquement compte titre + compte espèces."""
        self.ensure_one()
        if self.account_part_ids or self.account_cash_ids:
            raise UserError(_("Cet investisseur possède déjà des comptes."))

        country = (self.country_id.code or "XX").upper()
        inv_type = "PP"
        # if partner is a company
        if self.partner_id and self.partner_id.company_type == "company":
            inv_type = "PM"
        inv_id_fmt = str(self.id).zfill(4)
        seq_part = str(len(self.account_part_ids) + 1).zfill(3)
        account_part_number = f"CT-{inv_type}-{inv_id_fmt}-{seq_part}"
        part = self.env['efund.investor.part'].create({
            'name': f"Compte Titre - {self.full_name or self.name or 'Investor'}",
            'investor_id': self.id,
            'account_number': account_part_number,
            'total_parts': 0,
            'state': 'active',
        })
        seq_cash = str(len(self.account_cash_ids) + 1).zfill(3)
        account_cash_number = f"ES-{country}-{inv_type}-{inv_id_fmt}-{seq_cash}"
        cash = self.env['efund.investor.cash'].create({
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
            "res_model": "efund.investor.deposit.wizard",
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
            "res_model": "efund.investor.subscription",
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
                rec.sudo().write(
                    {'pep_flag': result.get('pep', False), 'sanctions_flag': result.get('sanctions', False)})
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
        return super(FundInvestor, self).action_check_kyc_compliance() if hasattr(super(),
                                                                                  'action_check_kyc_compliance') else {}

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
            #rec.create_investor_accounts()
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
        Subscription = self.env['efund.investor.subscription']
        for investor in self:
            investor.subscription_count = Subscription.search_count([
                ('investor_id', '=', investor.id),
                ('state', '!=', 'accounted')

            ])

    def _compute_deposit_count(self):
        Deposit = self.env['efund.investor.deposit']
        for investor in self:
            investor.deposit_count = Deposit.search_count([
                ('investor_id', '=', investor.id),
                ('state', '!=', 'accounted')

            ])

    def _compute_redemption_count(self):
        Redemption = self.env['efund.investor.redemption']
        for investor in self:
            investor.redemption_count = Redemption.search_count([
                ('investor_id', '=', investor.id),
                ('state', '!=', 'accounted')

            ])

    def _compute_withdraw_count(self):
        Withdraw = self.env['efund.investor.withdraw']
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
            'res_model': 'efund.investor.subscription',
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
            'res_model': 'efund.investor.deposit',
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
            'res_model': 'efund.investor.redemption',
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
            'res_model': 'efund.investor.withdraw',
            'view_mode': 'list,form',
            'domain': [('investor_id', '=', self.id)],
            'context': {
                'default_investor_id': self.id,
                'search_default_investor_id': self.id,
            }
        }

    def action_print(self):
        return (self.env.ref('efundOpc.action_report_investor').report_action(self))

    # Ajout l'investisseur à un compte

    def open_join_fund_wizard(self):
        """ Ouvre la fenêtre pour choisir le fonds """
        return {
            'name': _('Adhésion à un nouveau Fonds'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.investor.join.fund.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_investor_id': self.id}
        }

    def action_join_fund(self, fund_id):
        """ Création des comptes Titres et Espèces """
        self.ensure_one()

        # 1. Création du Compte Titres
        part_account_obj = self.env['efund.investor.part_account']
        existing_part = part_account_obj.search([
            ('investor_id', '=', self.id),
            ('vehicule_id', '=', fund_id.vehicule_id.id)
        ])
        if not existing_part:
            part_account_obj.create({
                'name': f"Compte Titres - {fund_id.name}",
                'investor_id': self.id,
                'vehicule_id': fund_id.vehicule_id.id,
                'account_number': self._generate_account_number('part'),
                'date_opened': fields.Date.today(),
            })

        # 2. Création du Compte Espèces
        cash_account_obj = self.env['efund.investor.cash_account']
        existing_cash = cash_account_obj.search([
            ('investor_id', '=', self.id),
            ('vehicule_id', '=', fund_id.vehicule_id.id)
        ])
        if not existing_cash:
            cash_account_obj.create({
                'name': f"Compte Espèces - {fund_id.name}",
                'investor_id': self.id,
                'vehicule_id': fund_id.vehicule_id.id,
                'account_number': self._generate_account_number('cash'),
                'date_opened': fields.Date.today(),
            })
        return True

    def _generate_account_number(self, account_type):
        """ Génère un numéro de compte conforme à la circulaire UMOA 001-2022 """
        self.ensure_one()
        config = self.env['efund.company.number'].search([], limit=1)
        if not config:
            raise UserError("Veuillez configurer les codes Teneur et Agence dans les paramètres.")

        # 1. Détermination des segments
        teneur = config.code_teneur_compte.zfill(4)
        agence = config.code_agence.zfill(3)

        # Type de compte (UMOA : 00=Titres, 01=Espèces)
        type_compte = '00' if account_type == 'part' else '01'

        # Catégorie & Type Client (Dynamique selon l'investisseur)
        categorie = ''
        if self.investor_category == '00':
            categorie = '00'  if account_type == 'part' else 10
        elif self.investor_category == '01':
            categorie = '01' if account_type == 'part' else 11
        elif self.investor_category == '02':
            categorie = '02' if account_type == 'part' else 12
        else:
            categorie = '08' if account_type == 'part' else 18


        type_client = "10" if self.investor_type == "individual" else "20"

        # Numéro chronologique (Séquence Odoo de 5 chiffres)
        sequence = self.env['ir.sequence'].next_by_code('efund.investor.account.number') or '00001'
        sequence = sequence[-5:]  # On s'assure d'avoir 5 chiffres

        # 2. Construction du radical (18 chiffres)
        radical = f"{teneur}{agence}{type_compte}{categorie}{type_client}{sequence}"

        # 3. Calcul de la Clé de Contrôle (Algorithme Modulo 97)
        # Selon la circulaire : Reste de (Radical * 1000) / 97, puis 97 - Reste
        # Note : Pour les grands nombres en Python, on peut manipuler l'entier directement
        val_for_key = int(radical + "000")
        reste = val_for_key % 97
        cle = 97 - reste

        # Formatage final sur 2 chiffres
        cle_str = str(cle).zfill(2)

        return f"{radical}{cle_str}"
