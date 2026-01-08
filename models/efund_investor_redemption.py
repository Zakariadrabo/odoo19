import logging
import math
from datetime import timedelta
from math import floor

from odoo import models, fields, api, _
from odoo.exceptions import UserError
_logger = logging.getLogger(__name__)

class FundRedemption(models.Model):
    _name = 'efund.investor.redemption'
    _inherit = ['efund.operation.base', 'mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _description = 'Opération de retrait de fonds'

    balance = fields.Float(string="Solde", related="cash_account_id.balance", readonly=True)
    date_operation = fields.Datetime(string="Date de l'opération", default=fields.Datetime.now)
    date_valeur = fields.Datetime(string="Date de valeur")
    allow_fractional_parts = fields.Boolean(string="Parts fractionnées",
                                            related='part_account_id.fund_id.allow_fractional_parts', )
    total_parts_available = fields.Float(string=" Nombre total de parts", related="part_account_id.total_parts", readonly=True)
    redemption_type = fields.Selection([('partial', 'Rachat partiel'), ('total', 'Rachat total'), ],
                                       string="Type de rachat", default='partial', required=True)
    parts_to_redeem = fields.Float(string="Nombre de parts", digits=(16, 4))
    nav_date = fields.Date(string="Date VL appliquée", default=fields.Date.context_today, required=True)
    estimated_nav = fields.Float(string="VL estimée", help="VL indicative (à confirmer)", readonly=True)
    estimated_amount = fields.Monetary(string="Montant à percevoir", compute="_compute_estimated_amount", store=True, )
    redemption_fee_amount = fields.Monetary(string="Frais de rachat", compute="_compute_redemption_fee_amount", readonly=True, store=True,)
    redemption_fee_rate = fields.Float(string=" % Frais de rachat", related="share_class_id.redemption_fee_rate",
                                       readonly=True, store=True,)
    amount = fields.Float(string="Montant + frais", )
    cash_refund = fields.Float(string="Montant souhaité")

    # -----------------------------------------------------------------
    # RELATIONS
    # -----------------------------------------------------------------
    part_account_id = fields.Many2one('efund.investor.part', required=True, readonly=True)
    cash_account_id = fields.Many2one('efund.investor.cash', required=True, readonly=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id', store=True)
    share_class_id = fields.Many2one('efund.fund.share.class', string="Classe de part", #required=True,
                                     domain="[('fund_id', '=', fund_id)]")
    investor_id = fields.Many2one(related='part_account_id.investor_id', store=True)
    company_id = fields.Many2one(related='fund_id.company_id', store=True)
    currency_id = fields.Many2one(related='company_id.currency_id', store=True)

    # -----------------------------------------------------------------
    # LES METHODES
    # -----------------------------------------------------------------
    @api.depends('parts_to_redeem')
    def _compute_redemption_fee_amount(self):
        for sub in self:
            if not sub.allow_fractional_parts and sub.parts_to_redeem % 1 != 0:
                raise UserError(_("Ce fond n'accepte que des rachats de parts entières."))

            sub.amount = sub.estimated_nav * sub.parts_to_redeem
            sub.redemption_fee_amount = sub.amount * sub.redemption_fee_rate / 100
            sub.estimated_amount = sub.amount - sub.redemption_fee_amount

    @api.onchange('cash_refund')
    def _onchange_cash_refund(self):
        for sub in self:
            sub.amount = sub.cash_refund * (1 + sub.redemption_fee_rate / 100)
            sub.parts_to_redeem = sub.cash_refund / sub.estimated_nav
            if sub.allow_fractional_parts:
                sub.parts_to_redeem = round(sub.parts_to_redeem, 4)
            else:
                sub.parts_to_redeem = math.floor(sub.parts_to_redeem)

            sub.redemption_fee_amount = sub.cash_refund * sub.redemption_fee_rate / 100
            sub.estimated_amount = sub.amount - sub.redemption_fee_amount

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

    def action_account_redemption(self):
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


            # 🧾 Mise à jour de l’ordre
            rec.write({
                'date_valeur': fields.Datetime.now(),
                'state': 'accounted',
            })

            # 💸 MOUVEMENTS COMPTABLES
            # 1️⃣ Sortie espèces (montant reçu)
            self.env['efund.investor.cash.move'].create({
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'redemption_net',
                'amount': self.estimated_amount,
            })
            # 1️⃣ Sortie espèces (montant frais rachat)
            self.env['efund.investor.cash.move'].create({
                'cash_account_id': rec.cash_account_id.id,
                'move_type': 'redemption_fee',
                'amount': self.redemption_fee_amount,
            })

            # 2️⃣ Sortie de parts
            self.env['efund.investor.part.move'].create({
                'part_account_id': rec.part_account_id.id,
                'move_type': 'redemption',
                'parts': self.parts_to_redeem,
            })

            # 🧠 Traçabilité
            rec.message_post(
                body=_(
                    "Rachat exécuté: %s<br/>"
                    "VL : %s<br/>"                   
                    "Montant générée : %s<br/>"
                    "Monant reçu : %s"
                    "Frais rachat : %s"
                ) % (rec.parts_to_redeem,rec.estimated_nav,rec.amount,rec.estimated_amount, rec.redemption_fee_amount)
            )

    def action_validate_redemption(self):
        for rec in self:
            if rec.state != 'submitted':
                raise UserError(_("Le rachat doit être soumis avant la validation."))

            fund = rec.cash_account_id.fund_id
            vl = fund.current_vl
            if not vl or vl <= 0:
                raise UserError(_("Aucune VL valide disponible."))

                # Parts suffisantes
            if self.total_parts_available < self.parts_to_redeem:
                raise UserError(_("Nombre de parts insuffisant."))

            if self.estimated_nav != vl:
                return self._open_confirmation_wizard(
                    message="la VL a changé depuis la soumission du rachat. La nouvelle VL sera appliquée, Voulez-vous continuer?",
                    method_name='action_execute_confirmed'
                )
            else:
                rec.write({'state': 'validated', })

    def action_execute_confirmed(self):
        for rec in self:
            fund = rec.cash_account_id.fund_id
            rec.estimated_nav = fund.current_vl

            rec.write({'state': 'validated', })

    def action_cancel_redemption(self):
        for rec in self:
            if rec.state == 'accounted':
                raise UserError(_("Le rachat ne peut plus être annulée."))

            rec.write({'state': 'cancelled', })

    def action_submit_redemption(self):
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
                # 🧾 Mise à jour de l’ordre
            rec.write({
                'state': 'submitted',
            })



