from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FundTransaction(models.Model):
    _name = "efund.fund.transaction"
    _description = "Transaction sur fonds (OPCVM)"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "date desc, id desc"

    # --- Informations principales ---
    name = fields.Char(string="Reference", required=True, copy=False, readonly=True,
                       default=lambda self: _('New'))
    fund_id = fields.Many2one('efund.fund',string="Fonds concerné", required=True,index=True )
    investor_id = fields.Many2one('efund.investor',string="Investisseur",required=True)
    transaction_type = fields.Selection([
        ('subscription', 'Souscription'),
        ('redemption', 'Rachat'),
        ('transfer', 'Transfert'),
        ('arbitrage', 'Arbitrage'),
        ('dividend', 'Distribution de dividendes'),
        ('fee', 'Frais de gestion')
    ], string="Type de transaction", required=True)
    date = fields.Date(required=True, default=fields.Date.today, index=True)
    currency_id = fields.Many2one('res.currency',required=True,default=lambda self: self.env.company.currency_id)

    # --- Données financières ---
    nav_id = fields.Many2one('efund.fund.nav',string="Valorisation de référence",help="Valorisation du fonds utilisée pour cette transaction.")
    unit_value = fields.Monetary(string="Valeur liquidative (VL)", currency_field='currency_id')
    units = fields.Float(string="Nombre de parts", digits=(16, 6))
    amount = fields.Monetary(string="Montant total", currency_field='currency_id')
    is_initial_capital = fields.Boolean(string="Initial capital", default=False)
    share_class_id = fields.Many2one('efund.fund.class',string='Share Class',required=True,domain="[('fund_id', '=', fund_id), ('state', '=', 'active')]")

    # --- Suivi opérationnel ---
    status = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validée'),
        ('done', 'Comptabilisée'),
        ('cancelled', 'Annulée')
    ], string="Statut", default='draft', tracking=True)
    related_move_id = fields.Many2one('account.move', string="Écriture comptable liée", readonly=True)
    journal_id = fields.Many2one('account.journal', string="Journal comptable", domain="[('type','in',('bank','cash'))]")

    # --- Informations complémentaires ---
    payment_reference = fields.Char(string="Référence de paiement / Virement")
    notes = fields.Text(string="Commentaires")
    operator_id = fields.Many2one('res.users', string="Opérateur", default=lambda self: self.env.user)


    # --- Calculs automatiques ---
    @api.onchange('units', 'unit_value')
    def _onchange_amount(self):
        """Calcule automatiquement le montant à partir du nombre de parts et de la VL."""
        for rec in self:
            if rec.units and rec.unit_value:
                rec.amount = rec.units * rec.unit_value

    @api.onchange('amount', 'unit_value')
    def _onchange_units(self):
        """Calcule le nombre de parts à partir du montant et de la VL."""
        for rec in self:
            if rec.amount and rec.unit_value:
                rec.units = rec.amount / rec.unit_value

    # --- Contraintes ---
    @api.constrains('units', 'unit_value', 'amount')
    def _check_amounts(self):
        for rec in self:
            if rec.transaction_type in ['subscription', 'redemption']:
                if rec.units <= 0:
                    raise ValidationError(_("Le nombre de parts doit être positif."))
                if rec.unit_value <= 0:
                    raise ValidationError(_("La valeur liquidative doit être positive."))
                expected = round(rec.units * rec.unit_value, 2)
                if abs(rec.amount - expected) > 0.01:
                    raise ValidationError(_("Le montant ne correspond pas au produit Parts × VL."))

    # --- Actions principales ---
    def action_validate(self):
        """Valide la transaction avant comptabilisation"""
        for rec in self:
            if rec.status != 'draft':
                continue
            if not rec.nav_id:
                raise UserError(_("La transaction doit être liée à une valorisation (VL)."))
            rec.status = 'validated'

    def action_post(self):
        """Comptabilise la transaction"""
        for rec in self:
            if rec.status != 'validated':
                raise UserError(_("La transaction doit être validée avant comptabilisation."))

            rec._create_accounting_entry()
            rec.status = 'done'

    def _create_accounting_entry(self):
        """Création automatique de l’écriture comptable associée à la transaction"""
        self.ensure_one()

        cash_account = self.fund_id.cash_account_id
        capital_account = self.fund_id.capital_account_id
        journal = self.fund_id.subscription_journal_id

        if self.transaction_type == 'subscription':
            journal = self.fund_id.subscription_journal_id.id
        elif self.transaction_type == 'redemption':
            journal = self.fund_id.redemption_journal_id.id
        else:
            journal = self.fund_id.redemption_journal_id.id



        if not journal:
            raise UserError(_("Aucun journal de trésorerie trouvé pour le fonds %s.") % self.fund_id.name)

        move_lines = []
        if self.transaction_type == 'subscription':
            debit_account = cash_account
            credit_account = capital_account
            label = _("Souscription de parts par %s") % self.investor_id.name

        elif self.transaction_type == 'redemption':
            debit_account = capital_account
            credit_account = cash_account
            label = _("Rachat de parts de %s") % self.investor_id.name

        else:
            raise UserError(_("Type de transaction non encore géré comptablement."))

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': self.date,
            'ref': self.name,
            'journal_id': journal,
            'company_id': self.fund_id.company_id.id,
            'line_ids': [
                (0, 0, {'account_id': debit_account.id, 'debit': self.amount, 'name': label}),
                (0, 0, {'account_id': credit_account.id, 'credit': self.amount, 'name': label}),
            ],
        })

        move.action_post()
        self.related_move_id = move.id

    # --- Sequence automatique ---
    @api.model
    def create(self, vals):
        # Si plusieurs transactions sont créées à la fois
        if isinstance(vals, list):
            records = super().create(vals)
            for rec in records:
                if rec.status == 'validated':
                    rec._create_accounting_entry()
            return records

        # Cas normal (création unique)
        record = super().create(vals)
        if record.status == 'validated':
            record._create_accounting_entry()
        return record
