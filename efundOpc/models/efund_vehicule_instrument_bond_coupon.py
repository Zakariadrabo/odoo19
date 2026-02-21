from odoo import models, fields, api, _
from odoo.exceptions import ValidationError

class FundBondCoupon(models.Model):
    _name = 'efund.bond.coupon'
    _description = 'Bond Coupon Payment Schedule'
    _order = 'payment_date asc'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']

    bond_id = fields.Many2one('efund.vehicule.instrument.core.bond', required=True)
    date_debut = fields.Date("Début ")
    date_fin = fields.Date("Fin ")
    date_paiement = fields.Date("Paiement")
    nb_jours = fields.Integer("NB jours")
    montant = fields.Monetary("Coupon")
    currency_id = fields.Many2one(related='bond_id.currency_id')
    state = fields.Selection([('draft', 'Prévu'), ('paid', 'Payé'), ('cancelled', 'Annulé'), ], default='draft')
    coupon_number = fields.Integer("N°")
    payment_date = fields.Date()

    @api.model
    def action_pay(self):
        """Paiement effectif du coupon"""
        for rec in self:
            if rec.state != 'draft':
                continue
            """
            cash_account_id = self.env[
                'efund.investor.cash_account'].get_cash_account_id_investor_by_vehicule_and_investor_id(
                self.mandate_id.vehicule_id.id, self.mandate_id.investor_id.id)
            if not cash_account_id:
                raise ValidationError("Compte cash non trouvé pour l'investisseur spécifié.")

            mvt_cash = self.env['efund.investor.cash_account.move'].create({
                'vehicule_id': rec.mandate_id.vehicule_id.id,
                'cash_account_id': cash_account_id,
                'label': f"Paiement du coupon N°' {rec.coupon_number}",
                'move_type': 'coupon',
                'amount': rec.montant,
                'state': 'reconciled',
            })
            if mvt_cash:
                rec.mandate_id.message_post(
                    body=_(f"Paiement du coupon N° %s de %s .") % (rec.coupon_number, rec.montant))
            else:
                raise ValidationError(
                    f"Erreur rencontrée lors du paiement du coupon {rec.coupon_number} pour le mandat {rec.mandate_id.name}")
            """
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


