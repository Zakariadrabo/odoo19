import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.models import Constraint
_logger = logging.getLogger(__name__)


class EfundMandate(models.Model):
    _name = 'efund.mandate'
    _description = 'Mandat de gestion'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(required=True)
    code = fields.Char(string="Code du fond", required=True)
    management_company_id = fields.Many2one('efund.management.company', string='Gestionnaire',
                                            domain="[('company_id', '!=', company_id)]")
    investor_id = fields.Many2one('efund.investor', string="Investisseur", required=True, index=True,
                                  ondelete='cascade')

    # partner_id = fields.Many2one('res.partner',string="Client (personne morale)",required=True)
    company_id = fields.Many2one('res.company', string='Company', ondelete='cascade')
    start_date = fields.Date(required=True)
    end_date = fields.Date(required=True)
    duration_years = fields.Integer(compute='_compute_duration', store=True)
    capital_committed = fields.Monetary(string="Capital confié", required=True)
    coupon_rate = fields.Float(string="Taux de coupon annuel (%)", required=True)
    currency_id = fields.Many2one(related='management_company_id.company_id.currency_id', store=True)
    capital_remaining = fields.Monetary(compute='_compute_financial_summary',currency_field='currency_id',)
    coupons_paid = fields.Monetary(compute='_compute_financial_summary',currency_field='currency_id',)
    cash_balance = fields.Monetary(compute='_compute_financial_summary',currency_field='currency_id',)
    state = fields.Selection([('draft', 'Brouillon'), ('active', 'Actif'), ('terminated', 'Terminé')], default='draft', tracking=True)

    # relations
    coupon_ids = fields.One2many('efund.mandate.coupon', 'mandate_id', string="Coupons")
    cash_move_ids = fields.One2many('efund.account.cash.move', 'mandate_id', string="Flux financiers")


    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for rec in self:
            if rec.start_date and rec.end_date:
                rec.duration_years = (
                        rec.end_date.year - rec.start_date.year
                )

    def action_generate_coupons(self):
        for mandate in self:
            if mandate.state != 'active':
                raise UserError(
                    _("Les coupons ne peuvent être générés que pour un mandat actif.")
                )

            if not mandate.start_date or not mandate.end_date:
                raise UserError(
                    _("Les dates de début et de fin doivent être renseignées.")
                )

            if mandate.coupon_rate <= 0:
                raise UserError(
                    _("Le taux de coupon doit être strictement positif.")
                )

            Coupon = self.env['efund.mandate.coupon']

            start_year = mandate.start_date.year
            end_year = mandate.end_date.year

            created = 0

            for year in range(start_year, end_year + 1):

                # Vérifier l’existence du coupon
                exists = Coupon.search([
                    ('mandate_id', '=', mandate.id),
                    ('year', '=', year),
                ], limit=1)

                if exists:
                    continue

                amount = (
                        mandate.capital_committed * mandate.coupon_rate / 100
                )

                Coupon.create({
                    'mandate_id': mandate.id,
                    #'cash_account_id': mandate.cash_account_id.id,
                    'year': year,
                    'amount': amount,
                })

                created += 1

            mandate.message_post(
                body=_(
                    "%s coupon(s) généré(s) automatiquement."
                ) % created
            )



    def _compute_financial_summary(self):
        CashMove = self.env['efund.account.cash.move']

        for mandate in self:
            if not mandate.id:
                mandate.capital_remaining = 0.0
                mandate.coupons_paid = 0.0
                mandate.cash_balance = 0.0
                continue

            moves = CashMove.search([
                ('mandate_id', '=', mandate.id),
            ])

            # Dépôt initial / versements
            total_deposit = sum(
                m.amount for m in moves
                if m.move_type == 'deposit'
            )

            # Coupons payés
            total_coupon = sum(
                m.amount for m in moves
                if m.move_type == 'coupon'
            )

            # Capital remboursé
            total_capital_return = sum(
                m.amount for m in moves
                if m.move_type == 'capital_return'
            )

            # Solde espèces réel
            mandate.cash_balance = sum(
                m.amount_signed for m in moves
            )

            # Capital restant à rembourser
            mandate.capital_remaining = (
                    mandate.capital_committed - total_capital_return
            )

            mandate.coupons_paid = total_coupon

    # -------------------------------------------------
    # ACTIVATION DU MANDAT
    # -------------------------------------------------
    def action_activate(self):
        for rec in self:
            if rec.state != 'draft':
                raise UserError(_("Seul un mandat en brouillon peut être activé."))

            # Sécurités métier minimales
            """
            if not rec.cash_account_id:
                raise UserError(
                    _("Le mandat doit disposer d’un compte espèces avant activation.")
                )
                """

            if rec.start_date > fields.Date.today():
                raise UserError(
                    _("La date de début du mandat n’est pas encore atteinte.")
                )

            rec.write({'state': 'active'})

            rec.message_post(
                body=_(
                    "Mandat activé par %s."
                ) % self.env.user.name
            )

    def action_open_termination_wizard(self):
        self.ensure_one()

        if self.state != 'active':
            raise UserError(_("Seul un mandat actif peut être clôturé."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Clôture du mandat'),
            'res_model': 'efund.mandate.termination',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_mandate_id': self.id,
                'default_amount': self.capital_remaining,
                'force_company': self.company_id.id,
            }
        }
