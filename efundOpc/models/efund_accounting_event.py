from odoo import api, fields, models, _

class AccountingEvent(models.Model):
    _name = "efund.accounting.event"
    _description = "Financial Events"
    _order = "id desc"

    event_type_id = fields.Many2one('efund.event.type.new', string="Type d'Événement", required=True)
    vehicule_id = fields.Many2one('efund.vehicule', string="Véhicule")
    reference = fields.Char(string="Reference", required=True)
    event_date = fields.Datetime(string="Date de l'évènement")
    payload = fields.Json(required=True)
    state = fields.Selection([('draft', 'Brouillon'), ('processed', 'Traité')], default='draft')
    move_id = fields.Many2one('account.move', string="Pièce Comptable")
