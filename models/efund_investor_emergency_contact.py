from odoo import models, fields


class EFundInvestorEmergencyContact(models.Model):
    _name = "efund.investor.emergency.contact"
    _description = "Contact d’urgence"

    investor_id = fields.Many2one("efund.investor",required=True,ondelete="cascade")

