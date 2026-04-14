from odoo import models, fields, api, _
from odoo.exceptions import UserError,ValidationError
from datetime import timedelta, datetime
from dateutil.relativedelta import relativedelta

class BondAmortization(models.Model):
    _name = "efund.bond.amortization"
    _description = "Bond Amortization Schedule"
    _inherit = ['mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _order = "installment_number asc"

    bond_id = fields.Many2one('efund.vehicule.instrument.core.bond',string="Instrument",required=True,ondelete="cascade")

    installment_number = fields.Integer(string="N°.", )
    due_date = fields.Date(string="Date",)
    opening_principal = fields.Monetary(string="Capital", )
    coupon_amount = fields.Monetary(string="Intérêt", )
    principal_repayment = fields.Monetary(string="Remboursement", )
    annuite = fields.Monetary(string="Annuité", )
    closing_principal = fields.Monetary(string="Restant",)
    currency_id = fields.Many2one(related="bond_id.currency_id", store=True, readonly=True)
    total_payment = fields.Monetary( string="Paiement total",compute="_compute_total_payment",store=True)
    amortization_type = fields.Selection([('in_fine', "In Fine"), ('constant_annuity', "Annuités Constantes"),
                                          ('constant_principal', "Amortissement Constant"),
                                          ('custom_schedule', "Échéancier Personnalisé"),
                                          ], string="Type d'Amortissement", default="in_fine")
    state = fields.Selection([('draft', 'Prévu'), ('paid', 'Payé'), ('cancelled', 'Annulé'), ], default='draft')

    @api.depends("coupon_amount", "principal_repayment")
    def _compute_total_payment(self):
        for line in self:
            line.total_payment = (line.coupon_amount or 0) + (line.principal_repayment or 0)


    @api.model
    def action_pay(self):
        """Paiement effectif du coupon"""
        for rec in self:
            if rec.state != 'draft':
                continue

            instrument = self.env['efund.vehicule.portfolio'].get_vehicles_by_instrument(rec.bond_id.instrument_id.id)
            if instrument:
                for inst in instrument:
                    coupon_value = rec.coupon_amount * inst.get('quantity') * rec.bond_id.face_value / rec.bond_id.issue_amount
                    principal_value = rec.principal_repayment * inst.get('quantity') * rec.bond_id.face_value / rec.bond_id.issue_amount
                    vehicule_cash = self.env['efund.vehicule.cash'].search([('vehicule_id', '=', inst.get('vehicule_id'))], limit=1)

                    if not vehicule_cash:
                        raise ValidationError("Compte cash non trouvé pour l'investisseur spécifié.")

                    vehicule_move_trans = self.env['efund.vehicule.cash.move'].create({
                        'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                        'vehicule_cash_id': vehicule_cash.id,
                        'amount': coupon_value,
                        'move_type': 'coupon_in' ,
                        'liquidity_type': 'liquid',
                        'label': f" Versement du coupon N° {rec.installment_number} de l'instrument {rec.bond_id.instrument_id.name}",
                        'state': 'reconciled',
                        'date': rec.due_date,
                        'value_date': rec.due_date,
                        'instrument_id': rec.bond_id.instrument_id.id,
                    })

                    rec.bond_id.message_post(
                        body=_("Crédit du compte du véhicule au montant de %s francs pour verement de coupon") % (coupon_value),
                        subject="comptabilisation de la transaction",
                        message_type="comment",
                        subtype_xmlid="mail.mt_comment"
                    )

                    if principal_value and principal_value > 0:
                        vehicule_move_principal = self.env['efund.vehicule.cash.move'].create({
                            'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                            'vehicule_cash_id': vehicule_cash.id,
                            'amount': principal_value,
                            'move_type': 'coupon_in',
                            'liquidity_type': 'liquid',
                            'label': f" Remboursement du principal N° {rec.installment_number} de l'instrument {rec.bond_id.instrument_id.name}",
                            'state': 'reconciled',
                            'date': rec.due_date,
                            'value_date': rec.due_date,
                            'instrument_id': rec.bond_id.instrument_id.id,
                        })

                        rec.bond_id.message_post(
                            body=_("Crédit du compte du véhicule au montant de %s francs pour verement de coupon") % (
                                principal_value),
                            subject="comptabilisation de Coupon / principal",
                            message_type="comment",
                            subtype_xmlid="mail.mt_comment"
                        )

            rec.write({
                'state': 'paid',
            })

    def update_coupon_state(self):
        self.ensure_one()
        return self._open_confirmation_wizard(
            message="Confimez-vous le paiement du coupon ?",
            method_name='action_execute_confirmed'
        )

    def action_execute_confirmed(self):
        self.ensure_one()
        self.action_pay()




