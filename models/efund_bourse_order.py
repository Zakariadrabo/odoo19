from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError


class EfundBourseOrder(models.Model):
    _name = "efund.bourse.order"
    _description = "Ordre de Bourse"
    _order = "order_date desc"

    # ---------------------------------------------------------------------
    # IDENTIFICATION
    # ---------------------------------------------------------------------
    name = fields.Char(string="Référence",default=lambda self: _('ORD/%s') % fields.Date.today(),readonly=True)
    order_date = fields.Date(string="Date Ordre",default=fields.Date.context_today,required=True)
    fund_id = fields.Many2one('efund.fund',string="Fonds (OPCVM)",equired=True,index=True,domain=lambda self: [('company_id', '=', self.env.company.id)])
    fund_name = fields.Char(related='fund_id.name',string="Fonds",store=True)
    company_id = fields.Many2one('res.company',string="Société",required=True,readonly=True,default=lambda self: self.env.company)
    execution_line_ids = fields.One2many('efund.bourse.order.execution.line','order_id',string="Historique d’exécution")
    # ---------------------------------------------------------------------
    # STATUT
    # ---------------------------------------------------------------------
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé'),
        ('sent', 'Envoyé à la SGI'),
        ('partially_executed', 'Partiellement exécuté'),
        ('executed', 'Exécuté'),
        ('cancelled', 'Annuler')
    ], default='draft', string="Statut")

    # ---------------------------------------------------------------------
    # TYPE D’ORDRE
    # ---------------------------------------------------------------------
    is_subscription = fields.Boolean(string="Souscription")
    is_buy = fields.Boolean(string="Achat")
    is_sell = fields.Boolean(string="Vente")
    order_type = fields.Selection([
        ('market', 'Au marché'),
        ('limit', 'À cours limité'),
        ('threshold', 'À seuil'),
    ], string="Type d’ordre", required=True)

    # ---------------------------------------------------------------------
    # INSTRUMENT FINANCIER
    # ---------------------------------------------------------------------
    instrument_id = fields.Many2one('efund.fund.instrument',string="Instrument Financier",required=True)
    depositaire_sgi = fields.Many2one('efund.depositaire',tring="Dépositaire du fond",required=True)
    symbol = fields.Char(related='instrument_id.ticker',string="Symbole",readonly=True)
    market_place = fields.Selection(related='instrument_id.market',string="Place",readonly=True)
    depository = fields.Selection(related='instrument_id.custodian', string="Dépositaire",readonly=True)

    # ---------------------------------------------------------------------
    # CONDITIONS FINANCIÈRES
    # ---------------------------------------------------------------------
    price_limit = fields.Float(string="Cours limite")
    quantity = fields.Float(string="Quantité", required=True)
    executed_quantity = fields.Float(string="Quantité exécutée", compute='_compute_executed_quantity', store=True)
    execution_price = fields.Float(string="Cours executed")
    average_execution_price = fields.Float(string="Cours moyen exécuté", store=True)
    execution_date = fields.Date(string="Date d'exécution", readonly=True)
    execution_type = fields.Selection(
        [('partial', 'Exécuté partiellement'),
         ('executed', 'Exécuté totalement')],
        string="Type d'exécution",
        readonly=True)
    allow_loss = fields.Boolean(string="P ? (Vente à perte autorisée)",help="Valable uniquement pour les ordres d'achat")
    expiry_date = fields.Date(string="Date limite")

    # ---------------------------------------------------------------------
    # PRÉNOTATION (CALCULÉE)
    # ---------------------------------------------------------------------
    gross_amount = fields.Monetary(string="Montant brut",compute="_compute_prenotation",currency_field="currency_id")
    commission_sgi = fields.Monetary(string="Commission SGI",compute="_compute_prenotation",currency_field="currency_id")
    commission_total = fields.Monetary(string="Total commissions",compute="_compute_prenotation",currency_field="currency_id")
    currency_id = fields.Many2one(related='company_id.currency_id',readonly=True)

    # ---------------------------------------------------------------------
    # SIGNATAIRES
    # ---------------------------------------------------------------------
    signatory_ids = fields.Many2many('res.partner',string="Signataires")
    comment = fields.Text(string="Commentaires")

    # ----------------------------------------------------
    # Contraintes
    # ----------------------------------------------------
    # Ajoutez un onchange pour auto-sélectionner le fond
    @api.depends('company_id')
    def _compute_fund_id(self):
        """Déterminer automatiquement le fond basé sur la compagnie"""
        for order in self:
            if order.company_id:
                # Recherche un fond lié à cette compagnie
                fund = self.env['efund.fund'].search([
                    ('company_id', '=', order.company_id.id),
                    ('state', '=', 'active')  # Seulement les fonds actifs
                ], limit=1)

                if fund:
                    order.fund_id = fund.id
                else:
                    order.fund_id = False
            else:
                order.fund_id = False

    @api.constrains('company_id', 'fund_id')
    def _check_fund_company_consistency(self):
        """Vérifier que le fond appartient à la compagnie"""
        for order in self:
            if order.fund_id and order.company_id:
                if order.fund_id.company_id != order.company_id:
                    raise ValidationError(_(
                        "Le fond sélectionné n'appartient pas à la compagnie %s. "
                        "Veuillez choisir un fond lié à cette compagnie."
                    ) % order.company_id.name)

    @api.depends('execution_line_ids.quantity')
    def _compute_executed_quantity(self):
        for order in self:
            order.executed_quantity = sum(order.execution_line_ids.mapped('quantity'))

    @api.constrains('order_type', 'price_limit')
    def _check_price_limit_required(self):
        for rec in self:
            if rec.order_type in ['limit', 'threshold'] and not rec.price_limit:
                raise ValidationError(
                    _("Le champ 'Cours limite' est obligatoire pour les ordres à cours limité ou à seuil."))

    # ---------------------------------------------------------------------
    # CALCUL PRÉNOTATION
    # ---------------------------------------------------------------------
    @api.depends('price_limit', 'quantity')
    def _compute_prenotation(self):
        for rec in self:
            rec.gross_amount = rec.execution_price * rec.executed_quantity
            rec.commission_sgi = rec.gross_amount * 0.005  # 0,5% exemple
            rec.commission_total = rec.commission_sgi

    # ---------------------------------------------------------------------
    # ACTIONS
    # ---------------------------------------------------------------------
    def action_validate(self):
        """Validation avec vérification d'état"""
        for order in self:
            if order.state != 'draft':
                raise UserError(_(
                    "Seuls les ordres en brouillon peuvent être validés. "
                    "État actuel : %s"
                ) % dict(self._fields['state'].selection).get(order.state))

            # Vérifications supplémentaires
            if not order.quantity > 0:
                raise ValidationError(_("La quantité doit être positive."))

            order.state = 'validated'

    def action_cancel(self):
        """Annulation avec vérification d'état"""
        for order in self:
            if order.state == 'partially_executed':
                raise UserError(_(
                    "Impossible d'annuler un ordre exécuté. "
                    "L'ordre %s a déjà été exécuté à %s%%."
                ) % (order.name, (order.executed_quantity / order.quantity) * 100))

            if order.state == 'cancelled':
                continue  # Déjà annulé

            order.state = 'cancelled'

    def action_send(self):
        for order in self:
            if order.state != 'draft':
                continue
            order.state = 'sent'

    def action_execute(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Exécution de l’ordre',
            'res_model': 'efund.bourse.order.execution.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_order_id': self.id,
                'default_remaining_quantity': self.quantity - self.executed_quantity,
            }
        }

    def action_finalize_execution(self, execution_vals):
        """
        Méthode centrale appelée par le wizard
        """
        self.ensure_one()

        if self.state not in ('sent', 'partially_executed'):
            raise UserError(_("L’ordre ne peut plus être exécuté."))

        qty = execution_vals.get('quantity')
        price = execution_vals.get('price')

        if qty <= 0 or price <= 0:
            raise ValidationError(_("Quantité et prix doivent être positifs."))

        remaining = self.quantity - self.executed_quantity
        if qty > remaining:
            raise ValidationError(_("Quantité exécutée supérieure au solde restant."))

        # 1️⃣ Créer ligne d’exécution
        exec_line = self.env['efund.bourse.order.execution.line'].create({
            'order_id': self.id,
            'execution_date': execution_vals.get('execution_date'),
            'quantity': qty,
            'price': price,
            'reference': execution_vals.get('reference'),
        })

        # 2️⃣ Recalcul quantités et prix moyen
        total_qty = sum(self.execution_line_ids.mapped('quantity'))
        total_amount = sum(
            l.quantity * l.price for l in self.execution_line_ids
        )

        self.executed_quantity = total_qty
        self.average_execution_price = (
            total_amount / total_qty if total_qty else 0
        )

        # 3️⃣ Mise à jour statut
        self.state = (
            'executed'
            if total_qty >= self.quantity
            else 'partially_executed'
        )

        # 4️⃣ Mise à jour position du fonds
        self._update_fund_position(exec_line)

        # 5️⃣ Comptabilité (hook)
        # self._create_accounting_entry(exec_line)

        # 6️⃣ NAV à recalculer
        # self.fund_id._mark_nav_to_recompute()

    # =========================

    def _create_accounting_entry(self, execution_line):
        self.ensure_one()

        journal = self.fund_id.operations_journal_id

        debit_account = self.fund_id.investment_account_id
        credit_account = self.fund_id.cash_account_id

        move = self.env['account.move'].create({
            'move_type': 'entry',
            'date': execution_line.execution_date,
            'journal_id': journal.id,
            'company_id': self.fund_id.company_id.id,
            'line_ids': [
                (0, 0, {
                    'account_id': debit_account.id,
                    'debit': execution_line.quantity * execution_line.price,
                    'credit': 0,
                    'name': self.instrument_id.name,
                }),
                (0, 0, {
                    'account_id': credit_account.id,
                    'debit': 0,
                    'credit': execution_line.quantity * execution_line.price,
                    'name': self.instrument_id.name,
                }),
            ]
        })

        move.action_post()
        execution_line.account_move_id = move.id

    def _update_fund_position(self, execution_line):
        """Création / mise à jour position du fonds"""
        position = self.env['efund.fund.position'].search([
            ('fund_id', '=', self.fund_id.id),
            ('instrument_id', '=', self.instrument_id.id),
        ], limit=1)

        qty = execution_line.quantity
        price = execution_line.price

        if self.order_type == 'sell':
            qty = -qty

        if position:
            new_qty = position.quantity + qty
            new_cost = (
                ((position.quantity * position.avg_cost) + (qty * price))
                / new_qty if new_qty else 0
            )
            position.write({
                'quantity': new_qty,
                'avg_cost': new_cost,
            })
        else:
            self.env['efund.fund.position'].create({
                'fund_id': self.fund_id.id,
                'instrument_id': self.instrument_id.id,
                'quantity': qty,
                'avg_cost': price,
            })

    def unlink(self):
        """Empêcher la suppression des ordres exécutés"""
        for order in self:
            if order.state == 'executed':
                raise UserError(_(
                    "Impossible de supprimer un ordre exécuté. "
                    "Vous pouvez uniquement l'annuler avant exécution."
                ))
        return super(EfundBourseOrder, self).unlink()

    def write(self, vals):
        """Protection basique - aucun changement après exécution"""
        for order in self:
            if order.state == 'executed':
                raise UserError(_(
                    "L'ordre %s est exécuté et ne peut plus être modifié."
                ) % order.name)

        return super(EfundBourseOrder, self).write(vals)
