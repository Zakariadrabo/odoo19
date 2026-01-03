from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FundSubscription(models.Model):
    _name = "efund.fund.subscription"
    _description = "Fund Subscription"
    _inherits = {'efund.fund.operation': 'operation_id'}

    operation_id = fields.Many2one('efund.fund.operation', required=True, ondelete='cascade', index=True)
    payment_mode = fields.Selection([('bank', 'Bank Transfer'), ('cheque', 'Cheque'), ('cash', 'Cash')],string='Payment Mode')
    reference_payment = fields.Char(string='Payment Reference')
    bank_id = fields.Many2one('res.bank', string='Bank')
    is_initial = fields.Boolean(string='Initial Subscription', default=False)
    available_cash = fields.Monetary(
        string="Cash disponible",
        currency_field="currency_id",
        compute="_compute_available_cash",
        store=False,
        readonly=True,)
    cash_account_id = fields.Many2one('efund.account.cash',string="Compte espèces",ondelete='restrict')

    @api.depends("investor_id", "cash_account_id")
    def _compute_available_cash(self):
        for rec in self:
            rec.available_cash = 0.0

            if not rec.investor_id or not rec.cash_account_id:
                continue

            cash_account = self.env['efund.account.cash'].search([
                ('investor_id', '=', rec.investor_id.id),
                ('fund_id', '=', rec.fund_id.id),
            ], limit=1)

            rec.available_cash = cash_account.balance if cash_account else 0.0

    @api.model
    def create(self, vals):
        # Création de l'opération pivot si pas fournie
        if 'operation_id' not in vals:
            op_vals = {
                'operation_type': 'subscription',
                'investor_id': vals.get('investor_id'),
                'fund_id': vals.get('fund_id'),
                'date_operation': vals.get('date_operation'),
                'nb_parts': vals.get('nb_parts'),
                'vl': vals.get('vl'),
                'amount': vals.get('amount'),
                'company_id': vals.get('company_id'),
            }
            op = self.env['efund.fund.operation'].create(op_vals)
            vals['operation_id'] = op.id

        sub = super(FundSubscription, self).create(vals)

        # Log KYC/AML à la création de la souscription
        sub._log_kyc_aml_on_subscription()

        return sub

    # Validation de la souscription
    def action_validate_subscription(self):
        self.ensure_one()
        investor = self.operation_id.investor_id

        # Récupérer le compte espèces
        cash_account = investor.account_cash_ids[:1]
        if not cash_account:
            raise UserError(_("Cet investisseur ne possède pas de compte espèces."))

        if cash_account.balance < self.amount:
            raise UserError(
                _("Solde insuffisant : disponible %s, requis %s")
                % (cash_account.balance, self.amount)
            )

        # Débiter le compte espèces
        cash_account.balance -= self.amount

        # Valider l’opération
        self.operation_id.state = 'validated'
        self.message_post(body=_("Souscription validée, montant débité du compte espèces."))
        return True

    # --------------------------------------------------------
    # KYC / AML LOGGING
    # --------------------------------------------------------
    def _log_kyc_aml_on_subscription(self):
        """
        Crée des logs de conformité KYC/AML à chaque souscription :
        - message dans le chatter de l'investisseur
        - message dans le chatter du fonds
        - éventuelle alerte AML si montant + risque élevé
        """
        for sub in self:
            investor = sub.investor_id
            fund = sub.fund_id
            amount = sub.amount or 0.0

            # 1) Message sur l'investisseur
            if investor:
                msg_inv = _(
                    "Nouvelle souscription enregistrée :<br/>"
                    "- Fonds : %s<br/>"
                    "- Montant : %.2f<br/>"
                    "- Nombre de parts : %.6f<br/>"
                    "- VL utilisée : %.6f<br/>"
                    "- Statut conformité : %s (score %s)"
                ) % (
                              fund.name if fund else '',
                              amount,
                              sub.nb_parts or 0.0,
                              sub.vl or 0.0,
                              investor.compliance_status or 'n/a',
                              investor.compliance_score or 0
                          )
                investor.message_post(
                    body=msg_inv,
                    subject=_("Log KYC/AML - Souscription")
                )

            # 2) Message sur le fonds
            if fund:
                msg_fund = _(
                    "Souscription de l'investisseur %s : montant %.2f (parts: %.6f, VL: %.6f). "
                    "Status KYC: %s."
                ) % (
                               investor.name or investor.partner_id.name if investor else '',
                               amount,
                               sub.nb_parts or 0.0,
                               sub.vl or 0.0,
                               investor.compliance_status or 'n/a'
                           )
                fund.message_post(
                    body=msg_fund,
                    subject=_("Log KYC/AML - Souscription")
                )

            # 3) Éventuelle alerte AML si gros montant + profil à risque
            threshold_amount = 10000000.0  # à paramétrer (10M FCFA par ex.)
            high_risk_status = investor.compliance_status in ('high_risk', 'non_compliant')
            sanctions_hit = getattr(investor, 'sanctions_flag', False)

            if amount >= threshold_amount and (high_risk_status or sanctions_hit):
                self.env['efund.aml.alert'].create({
                    'investor_id': investor.id,
                    'fund_id': fund.company_id.id if fund and fund.company_id else False,
                    'trigger': 'large_subscription_with_risk',
                    'severity': 'critical' if sanctions_hit else 'suspicious',
                    'status': 'new',
                    'score': investor.compliance_score or 0,
                    'notes': _(
                        "Souscription importante (%.2f) effectuée par un investisseur à risque (%s)."
                    ) % (amount, investor.compliance_status),
                })

    # Comptabilisation
    # Dans efund_fund_subscription_old.py, ajoutez ces méthodes après action_validate_subscription

    def action_account(self):
        """
        Comptabiliser la souscription en créant les écritures comptables
        """
        self.ensure_one()

        # Vérifier que la souscription est validée
        if self.state != 'validated':
            raise UserError(_("La souscription doit être validée avant d'être comptabilisée."))

        # Vérifier que la souscription n'est pas déjà comptabilisée
        if self.journal_entry_id:
            raise UserError(_("Cette souscription est déjà comptabilisée."))

        # Vérifier les informations nécessaires
        if not self.investor_id:
            raise UserError(_("L'investisseur est requis pour la comptabilisation."))

        if not self.fund_id:
            raise UserError(_("Le fonds est requis pour la comptabilisation."))

        if not self.amount or self.amount <= 0:
            raise UserError(_("Le montant de la souscription doit être positif."))

        try:
            # Créer l'écriture comptable
            move = self._create_accounting_entry()

            # Mettre à jour l'état
            self.operation_id.state = 'accounted'
            self.journal_entry_id = move.id

            # Créer les parts de l'investisseur
            self._create_investor_shares()

            # Mettre à jour le capital du fonds
            self._update_fund_capital()

            # Poste un message
            self.message_post(
                body=_("Souscription comptabilisée. Écriture %s créée.") % move.name,
                subject=_("Comptabilisation")
            )

            return {
                'type': 'ir.actions.act_window',
                'name': _('Écriture comptable'),
                'res_model': 'account.move',
                'res_id': move.id,
                'view_mode': 'form',
                'target': 'current',
            }

        except Exception as e:
            raise UserError(_("Erreur lors de la comptabilisation : %s") % str(e))

    def _create_accounting_entry(self):
        """
        Créer l'écriture comptable pour la souscription
        """
        # Récupérer les comptes comptables configurés
        journal = self._get_accounting_journal()
        account_debit = self._get_subscription_debit_account()
        account_credit = self._get_subscription_credit_account()

        # Préparer les lignes d'écriture
        line_vals = [
            # Débit: Compte de souscription
            (0, 0, {
                'account_id': account_debit.id,
                'debit': self.amount,
                'credit': 0.0,
                'name': _("Souscription %s - %s") % (self.name, self.investor_id.name),
                'partner_id': self.investor_id.partner_id.id,
            }),
            # Crédit: Capital du fonds
            (0, 0, {
                'account_id': account_credit.id,
                'debit': 0.0,
                'credit': self.amount,
                'name': _("Souscription %s - Capital") % self.name,
                'partner_id': self.fund_id.partner_id.id if self.fund_id.partner_id else False,
            }),
        ]

        # Créer l'écriture
        move_vals = {
            'journal_id': journal.id,
            'date': self.date_operation or fields.Date.today(),
            'ref': _("Souscription %s") % self.name,
            'line_ids': line_vals,
            'company_id': self.company_id.id,
            'move_type': 'entry',
        }

        move = self.env['account.move'].create(move_vals)

        # Valider l'écriture si nécessaire
        if journal.post_at == 'bank_rec':
            move.action_post()

        return move

    def _get_accounting_journal(self):
        """
        Récupérer le journal comptable approprié
        """
        # Chercher d'abord un journal spécifique aux souscriptions
        journal = self.env['account.journal'].search([
            ('company_id', '=', self.company_id.id),
            ('type', '=', 'general'),
            ('code', '=', 'SUB'),  # Code spécifique pour souscriptions
        ], limit=1)

        # Sinon, prendre le premier journal général
        if not journal:
            journal = self.env['account.journal'].search([
                ('company_id', '=', self.company_id.id),
                ('type', '=', 'general'),
            ], limit=1)

        if not journal:
            raise UserError(_("Aucun journal comptable trouvé pour la société %s.") % self.company_id.name)

        return journal

    def _get_subscription_debit_account(self):
        """
        Récupérer le compte de débit (compte de souscription en attente)
        """
        # Chercher un compte spécifique configuré
        account = self.company_id.subscription_account_id

        if not account:
            # Sinon, chercher par code
            account = self.env['account.account'].search([
                ('company_id', '=', self.company_id.id),
                ('code', '=like', '471%'),  # Compte de régularisation actif
                ('deprecated', '=', False),
            ], limit=1)

        if not account:
            raise UserError(
                _("Veuillez configurer un compte de souscription dans la société %s.") % self.company_id.name)

        return account

    def _get_subscription_credit_account(self):
        """
        Récupérer le compte de crédit (capital du fonds)
        """
        # Chercher dans le fonds
        if self.fund_id and self.fund_id.capital_account_id:
            return self.fund_id.capital_account_id

        # Sinon, chercher un compte capital par défaut
        account = self.env['account.account'].search([
            ('company_id', '=', self.company_id.id),
            ('code', '=like', '101%'),  # Capital social
            ('deprecated', '=', False),
        ], limit=1)

        if not account:
            raise UserError(_("Veuillez configurer un compte de capital pour le fonds %s.") % self.fund_id.name)

        return account

    def _create_investor_shares(self):
        """
        Créer les parts pour l'investisseur
        """
        investor = self.investor_id
        fund = self.fund_id

        # Vérifier si l'investisseur a déjà un compte parts pour ce fonds
        share_account = investor.account_part_ids.filtered(
            lambda a: a.fund_id == fund
        )

        if share_account:
            # Mettre à jour le compte existant
            share_account.write({
                'total_parts': share_account.total_parts + (self.nb_parts or 0),
                'last_update': fields.Date.today(),
            })
        else:
            # Créer un nouveau compte parts
            account_vals = {
                'investor_id': investor.id,
                'fund_id': fund.id,
                'name': _("Compte parts %s - %s") % (investor.name, fund.name),
                'total_parts': self.nb_parts or 0,
                'state': 'active',
                'company_id': self.company_id.id,
            }

            # Créer le compte parts
            share_account = self.env['efund.account.part'].create(account_vals)

            # Lier au compte espèces si disponible
            if self.cash_account_id:
                share_account.cash_account_id = self.cash_account_id.id

        # Enregistrer l'opération dans l'historique des parts
        self.env['efund.part.history'].create({
            'account_part_id': share_account.id,
            'operation_id': self.operation_id.id,
            'date_operation': self.date_operation or fields.Date.today(),
            'nb_parts': self.nb_parts or 0,
            'unit_price': self.vl or 0,
            'amount': self.amount,
            'operation_type': 'subscription',
            'company_id': self.company_id.id,
        })

    def _update_fund_capital(self):
        """
        Mettre à jour le capital total du fonds
        """
        if self.fund_id:
            # Ajouter le montant au capital souscrit
            self.fund_id.write({
                'subscribed_capital': (self.fund_id.subscribed_capital or 0) + self.amount,
                'total_shares': (self.fund_id.total_shares or 0) + (self.nb_parts or 0),
            })

            # Mettre à jour la dernière souscription
            self.fund_id.last_subscription_date = self.date_operation or fields.Date.today()

    # Ajouter également ces champs computed au modèle si nécessaire
    available_cash = fields.Float(
        string="Solde disponible",
        compute='_compute_available_cash',
        store=False
    )

    @api.depends('cash_account_id', 'investor_id')
    def _compute_available_cash(self):
        """Calculer le solde disponible sur le compte espèces"""
        for record in self:
            if record.cash_account_id:
                record.available_cash = record.cash_account_id.balance
            elif record.investor_id and record.investor_id.account_cash_ids:
                record.available_cash = record.investor_id.account_cash_ids[0].balance
            else:
                record.available_cash = 0.0

