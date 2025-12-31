from datetime import timedelta
from math import floor

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundRedemption(models.Model):
    _name = 'efund.fund.redemption'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin']
    _description = 'Opération de retrait de fonds'

    cash_account_id = fields.Many2one('efund.account.cash', required=True)
    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    part_account_id = fields.Many2one('efund.account.part', required=True)
    total_parts_available = fields.Float(string="Nombre de parts", related="part_account_id.total_parts", readonly=True)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')
    amount = fields.Monetary(string="montant", currency_field="currency_id")
    redemption_type = fields.Selection([('partial', 'Rachat partiel'), ('total', 'Rachat total'), ],
                                       string="Type de rachat", default='partial', required=True)
    parts_to_redeem = fields.Float(string="Nombre de parts à racheter")
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")

    # info VL (prévisionnelle)
    nav_date = fields.Date(string="Date VL appliquée", default=fields.Date.context_today, required=True)
    estimated_nav = fields.Monetary(string="VL estimée", help="VL indicative (à confirmer)", )
    estimated_amount = fields.Monetary(string="Montant estimé du rachat", compute="_compute_estimated_amount",
                                       store=False)
    parts_used = fields.Float(string="Nombre de parts utilisées")
    parts_refund = fields.Float(string="Nombre de parts à rembourser")
    cash_return = fields.Monetary(string="Montant à rembourser")

    @api.onchange('redemption_type')
    def _onchange_redemption_type(self):
        for rec in self:
            if rec.redemption_type == 'total' and rec.part_account_id:
                rec.parts_to_redeem = rec.part_account_id.total_parts
            elif rec.redemption_type == 'partial':
                rec.parts_to_redeem = 0.0

    @api.depends('redemption_type', 'parts_to_redeem', 'total_parts_available', 'estimated_nav')
    def _compute_estimated_amount(self):
        for rec in self:
            parts = rec.total_parts_available if rec.redemption_type == 'total' else rec.parts_to_redeem or 0.0
            rec.estimated_amount = parts * (rec.estimated_nav or 0.0)

    def action_account(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("Le rachat doit être validée avant exécution."))

            fund = rec.cash_account_id.fund_id

            # 🔒 Récupération de la VL validée (Juste pour les test et recuperer dans le modèle VL
            vl = fund.current_vl
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if self.total_parts_available < self.parts_to_redeem:
                raise UserError(_("Nombre de parts insuffisant."))

            # 🔢 Calcul théorique

            if fund.allow_fractional_parts:
                self.parts_used = self.parts_to_redeem
                self.parts_refund = 0.0
            else:
                self.parts_used = floor(self.parts_to_redeem)
                self.cash_return = self.parts_used * vl
                self.parts_refund = rec.parts_to_redeem - self.parts_used

            # 🧾 Mise à jour de l’ordre
            rec.write({
                'date_valeur': fields.Datetime.now(),
                'state': 'accounted',
            })

            # 💸 MOUVEMENTS COMPTABLES
            # 1️⃣ Sortie espèces (montant utilisé)
            self.env['efund.account.cash.move'].create({
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'redemption',
                'amount': self.cash_return,
            })

            # 2️⃣ Sortie de parts
            self.env['efund.account.part.move'].create({
                'part_account_id': rec.part_account_id.id,
                'move_type': 'redemption',
                'parts': self.parts_used,
            })

            # 3️⃣ Remboursement du reliquat (si nécessaire)
            if self.parts_refund > 0:
                self.env['efund.account.cash.move'].create({
                    'cash_account_id': rec.cash_account_id.id,
                    'move_type': 'refund',
                    'amount': self.parts_refund,
                })

            # 🧠 Traçabilité
            rec.message_post(
                body=_(
                    "Rachat exécuté.<br/>"
                    "VL : %s<br/>"
                    "Parts demandée : %s<br/>"
                    "part utilisée : %s<br/>"
                    "Montant générée : %s<br/>"
                    "Part restituée : %s"
                ) % (vl, self.parts_to_redeem, self.parts_used, self.cash_return, self.parts_refund)
            )

    def action_validate_subscription(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Le rachat doit être soumis avant la validation."))

            rec.write({'state': 'validated', })

    def action_cancel_subscription(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("Le rachat ne peut plus être annulée."))

            rec.write({'state': 'cancelled', })

    def action_submit_subscription(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Le rachat doit être en brouillon avant sa soumission."))

            fund = rec.cash_account_id.fund_id

            # 🔒 Récupération de la VL validée (Juste pour les test et recuperer dans le modèle VL
            vl = fund.current_vl
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if self.total_parts_available < self.parts_to_redeem:
                raise UserError(_("Nombre de parts insuffisant."))

            # 🔢 Calcul théorique

            if fund.allow_fractional_parts:
                self.parts_used = self.parts_to_redeem
                self.parts_refund = 0.0
            else:
                self.parts_used = floor(self.parts_to_redeem)
                self.cash_return = self.parts_used * vl
                self.parts_refund = rec.parts_to_redeem - self.parts_used

                # 🧾 Mise à jour de l’ordre
            rec.write({
                'state': 'submitted',
            })



