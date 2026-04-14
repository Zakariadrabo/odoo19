import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError,ValidationError


_logger = logging.getLogger(__name__)

class EfundMandateCoupon(models.Model):
    _name = 'efund.mandate.coupon'
    _description = 'Coupon annuel de mandat'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'efund.confirmable.mixin']
    _order = "date_paiement asc"

    mandate_id = fields.Many2one('efund.vehicule.mandate', string="Mandat", ondelete='cascade')
    date_debut = fields.Date("Début ")
    date_fin = fields.Date("Fin ")
    date_paiement = fields.Date("Paiement")
    nb_jours = fields.Integer("NB jours")
    montant = fields.Monetary("Coupon", currency_field='currency_id')
    currency_id = fields.Many2one(related='mandate_id.currency_id')
    state = fields.Selection([('draft', 'Prévu'), ('paid', 'Payé'), ('cancelled', 'Annulé'), ], default='draft')
    coupon_number = fields.Integer("N°")

    payment_date = fields.Date()

    @api.model
    def action_pay(self ):
        """Paiement effectif du coupon"""
        for rec in self:
            if rec.state != 'draft':
                continue
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

            # Débiter le compte cash du véhicule

            # récupérer ID du compte cash du fond
            vehicule_cash_id = self.env['efund.vehicule.cash'].get_vehicule_cash_id_by_vehicule_id(rec.mandate_id.vehicule_id.id)
            if vehicule_cash_id > 0:
                # mouvement du compte investisseur vers le compte mandat
                fund_move = self.env['efund.vehicule.cash.move'].create({
                    'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
                    'vehicule_cash_id': vehicule_cash_id,
                    'amount': rec.montant,
                    'label': f"Paiement de {rec.montant} francs CFA au compte du coupon du mandant",
                    'move_type': 'coupon_out',
                    'liquidity_type': 'liquid',
                    'date': rec.date_paiement,
                    'value_date': rec.date_paiement,
                    'state': 'reconciled',
                    'investor_id': rec.mandate_id.investor_id.id,
                    'vehicule_id': rec.mandate_id.vehicule_id.id,
                })



            if mvt_cash:
                rec.mandate_id.message_post(body=_(f"Paiement du coupon N° %s de %s .") % (rec.coupon_number, rec.montant))
            else:
                raise ValidationError(f"Erreur rencontrée lors du paiement du coupon {rec.coupon_number} pour le mandat {rec.mandate_id.name}")

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
        """
        if investor_cash_account_id:
            retour = 
            if retour:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Coupon mise à jour'),
                        'message': _("Le statut du coupon a passé à 'Payé'."),
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Coupon mise à jour'),
                        'message': _("Erreur rencontrée lors du paiement du coupon."),
                        'type': 'danger',
                        'sticky': False,
                    }
                }

        else:
            _logger.info(f"Cash account id {investor_cash_account_id}")
            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Coupon mise à jour'),
                    'message': _("Compte cash non trouvé pour l'investisseur spécifié."),
                    'type': 'success',
                    'sticky': False,
                }
            }
            """
