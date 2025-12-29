from datetime import timedelta
from math import floor

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundSubscription(models.Model):
    _name = 'efund.fund.subscription'
    _inherit = 'efund.operation.base'

    cash_account_id = fields.Many2one('efund.account.cash', required=True)
    part_account_id = fields.Many2one('efund.account.part', required=True)
    investor_id = fields.Many2one(related='cash_account_id.investor_id',store=True)
    fund_id = fields.Many2one(related='cash_account_id.fund_id',store=True)
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées", related='cash_account_id.fund_id.allow_fractional_parts',help="Si décoché, les souscriptions sont arrondies à l'entier inférieur.")
    is_initial = fields.Boolean(string='Initial Subscription', default=False)
    currency_id = fields.Many2one(related='cash_account_id.fund_id.currency_id')
    date_operation=fields.Datetime(string="Date de l'opération",default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    balance = fields.Float(string="Cash disponible",currency_field="currency_id",related="cash_account_id.balance", readonly=True,)
    amount = fields.Monetary(string="montant",currency_field="currency_id")
    parts = fields.Float(string="Nombre de parts")
    unit_value = fields.Monetary(string="VL appliquée",readonly=True,currency_field="currency_id")
    cash_used = fields.Monetary(string="Montant utilisé",readonly=True,currency_field="currency_id")
    cash_refund = fields.Monetary(string="Montant restitué",readonly=True,currency_field="currency_id")

    def action_account(self):
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("La souscription doit être validée avant exécution."))

            fund = rec.cash_account_id.fund_id

            # 🔒 Récupération de la VL validée (Juste pour les test et recuperer dans le modèle VL
            vl = fund.current_vl
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

            # Solde disponible suffisant
            if self.cash_account_id.balance < self.amount:
                raise UserError(_("Solde espèces insuffisant."))

            # 🔢 Calcul théorique
            theoretical_parts = rec.amount / vl

            if fund.allow_fractional_parts:
                parts = theoretical_parts
                cash_used = rec.amount
                cash_refund = 0.0
            else:
                parts = floor(theoretical_parts)
                cash_used = parts * vl
                cash_refund = rec.amount - cash_used

            if parts <= 0:
                raise UserError(
                    _("Le montant est insuffisant pour souscrire au moins une part.")
                )

            # 🧾 Mise à jour de l’ordre
            rec.write({
                'unit_value': vl,
                'parts': parts,
                'cash_used': cash_used,
                'cash_refund': cash_refund,
                'date_valeur': fields.Datetime.now(),
                'state': 'accounted',
            })

            # 💸 MOUVEMENTS COMPTABLES
            # 1️⃣ Sortie espèces (montant utilisé)
            self.env['efund.account.cash.move'].create({
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'subscription',
                'amount': cash_used,
            })

            # 2️⃣ Entrée parts
            self.env['efund.account.part.move'].create({
                'part_account_id': rec.part_account_id.id,
                'move_type': 'subscription',
                'parts': parts,
            })

            # 3️⃣ Remboursement du reliquat (si nécessaire)
            if cash_refund > 0:
                self.env['efund.account.cash.move'].create({
                    'cash_account_id': rec.cash_account_id.id,
                    'move_type': 'refund',
                    'amount': cash_refund,
                })

            # 🧠 Traçabilité
            rec.message_post(
                body=_(
                    "Souscription exécutée.<br/>"
                    "VL : %s<br/>"
                    "Parts créées : %s<br/>"
                    "Montant utilisé : %s<br/>"
                    "Montant restitué : %s"
                ) % (vl, parts, cash_used, cash_refund)
            )

    def action_validate_subscription(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("La souscription doit être soumise avant la validation."))

            rec.write({ 'state': 'validated',})

    def action_cancel_subscription(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("La souscription ne peut plus être annulée."))

            rec.write({ 'state': 'cancelled',})

    def action_submit_subscription(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("La souscription doit être en brouillon avant sa soumission."))

            fund = rec.cash_account_id.fund_id

            # 🔒 Récupération de la VL validée (Juste pour les test et recuperer dans le modèle VL
            vl = fund.current_vl
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

            # 🔢 Calcul théorique
            theoretical_parts = rec.amount / vl

            if fund.allow_fractional_parts:
                parts = theoretical_parts
                cash_used = rec.amount
                cash_refund = 0.0
            else:
                parts = floor(theoretical_parts)
                cash_used = parts * vl
                cash_refund = rec.amount - cash_used

            if parts <= 0:
                raise UserError(
                    _("Le montant est insuffisant pour souscrire au moins une part.")
                )

            # 🧾 Mise à jour de l’ordre
            rec.write({
                'unit_value': vl,
                'parts': parts,
                'cash_used': cash_used,
                'cash_refund': cash_refund,
                'state': 'submitted',
            })

