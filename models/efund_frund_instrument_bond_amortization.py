from odoo import models, fields, api
from datetime import timedelta
from dateutil.relativedelta import relativedelta

class BondAmortization(models.Model):
    _name = "efund.bond.amortization"
    _description = "Bond Amortization Schedule"
    _order = "installment_number asc"

    instrument_id = fields.Many2one('efund.fund.instrument',string="Instrument",required=True,ondelete="cascade")
    installment_number = fields.Integer(string="Echéance No.", required=True)
    due_date = fields.Date(string="Date de remboursement", required=True)
    opening_principal = fields.Monetary(string="Capital de départ", required=True)
    coupon_amount = fields.Monetary(string="Intérêt (Coupon)", required=True)
    principal_repayment = fields.Monetary(string="Remboursement principal", required=True)
    closing_principal = fields.Monetary(string="Principal final", required=True)
    currency_id = fields.Many2one(related="instrument_id.currency_id", store=True, readonly=True)
    total_payment = fields.Monetary( string="Paiement total",compute="_compute_total_payment",store=True)
    amortization_type = fields.Selection([('in_fine', "In Fine (Bullet)"), ('constant_annuity', "Annuités Constantes"),
                                          ('constant_principal', "Amortissement Constant"),
                                          ('american', "Américain (Balloon)"),
                                          ('custom_schedule', "Échéancier Personnalisé"),
                                          ], string="Type d'Amortissement", default="in_fine")
    @api.depends("coupon_amount", "principal_repayment")
    def _compute_total_payment(self):
        for line in self:
            line.total_payment = (line.coupon_amount or 0) + (line.principal_repayment or 0)
