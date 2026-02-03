from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class EfundVehiculeCashOperation(models.Model):
    _name = 'efund.vehicule.cash.operation'
    _description = 'Opérations diverses sur compte cash'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string="Référence", required=True, )
    vehicule_id = fields.Many2one('efund.vehicule', string="Fonds / Mandat", required=True)
    currency_id = fields.Many2one(related='vehicule_id.currency_id', store=True)

    # Types d'opérations bancaires
    operation_type = fields.Selection([
        ('bank_fee', 'Frais de virement'),
        ('agio', 'Agios / Intérêts débiteurs'),
        ('management_fee', 'Commission de gestion'),
        ('other', 'Autre opération')
    ], string="Type de frais", required=True)

    amount = fields.Monetary(string="Montant HT")
    vat_amount = fields.Monetary(string="TVA")
    total_amount = fields.Monetary(string="Montant TTC", compute="_compute_total")

    date_operation = fields.Date(string="Date", default=fields.Date.today)
    state = fields.Selection([
        ('draft', 'Brouillon'),
        ('validated', 'Validé'),
        ('cancelled', 'Annulé')
    ], string="Statut", default='draft')

    @api.depends('amount', 'vat_amount')
    def _compute_total(self):
        """ Calcule le montant total TTC de l'opération """
        for rec in self:
            # On additionne le montant HT et la TVA
            # L'utilisation de rec.amount or 0.0 évite les erreurs de type None
            rec.total_amount = (rec.amount or 0.0) + (rec.vat_amount or 0.0)

    def action_validate(self):
        self.ensure_one()

        # Débit du compte bancaire du fonds
        vehicule_cash = self.env['efund.vehicule.cash'].get_vehicule_cash_id_by_vehicule_id(self.vehicule_id)
        if not vehicule_cash:
            raise UserError(_("Le compte du fond n'existe pas"))

        vehicule_move_broker = self.env['efund.vehicule.cash.move']
        vehicule_move_broker.create({
            'name': self.env['ir.sequence'].next_by_code('efund.vehicule.cash.move'),
            'vehicule_cash_id': vehicule_cash,
            'amount': self.total_amount,
            'move_type': 'other_out',
            'liquidity_type': 'liquid',
            'state': 'reconciled',
            'label': self.name,
            'vehicule_id': self.vehicule_id.id,
        })
        mandate = self.env['efund.vehicule.mandate'].get_mandate_by_vehicule_id(self.vehicule_id)
        if mandate:
            mandate.message_post(
            body=_("Débit du compte du fond au montant de %s francs représentant les %s") % (
                self.total_amount, self.name),
            subject="Frais divers",
            message_type="comment",
            subtype_xmlid="mail.mt_comment"
        )

        # Crédit du compte des frais des opérations diverses
        self.write({'state': 'validated'})




    def action_cancel(self):
        pass
