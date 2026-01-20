from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class Fund(models.Model):
    _name = 'efund.vehicule.fund'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _inherits = {'efund.vehicule': 'vehicule_id'}

    vehicule_id = fields.Many2one('efund.vehicule', required=True, ondelete='cascade')
    vehicle_type = fields.Selection([('fund', 'Fonds'), ('mandate', 'Mandat')],default='fund', required=True, string="Type")
    isin = fields.Char(string='Code Isin')
    nav_frequency = fields.Selection([('daily', 'Journalière'), ('weekly', 'Hebdomaire'), ('monthly', 'Mensuelle'), ], string="Périodicité calcul VL", default='daily')
    cutoff_time = fields.Float(string="Heure de cut-off", default=16.0, help="Heure limite de réception des ordres (format décimal).\nExemples : 14.0 = 14h00, 14.5 = 14h30, 16.75 = 16h45.")
    allow_fractional_parts = fields.Boolean(string="Autoriser les parts fractionnées", default=False, help="Si décoché, les souscriptions sont arrondies à l'entier inférieur.")
    origin_nav = fields.Char(string="VL d'origine")

    ##################################################
    ## RELATIONS
    ##################################################
    share_class_ids = fields.One2many('efund.fund.share.class', 'vehicule_fund_id', string='Share Classes')
    depositary_id = fields.Many2one("efund.depositaire", string="Dépositaire")
    fund_type_id = fields.Many2one('efund.fund.type', string="Classe de fonds", required=True)


    # ------------------------------------------------------------
    # ACTION METHODS
    # ------------------------------------------------------------
    def action_activate(self):
        for record in self:
            if not record.start_date:
                raise ValidationError(_("Merci de saisir la date d'opération."))
            record.state = 'active'
            record.message_post(body=_("Le fond a été activé."))

    def action_suspend(self):
        for record in self:
            if record.state != 'active':
                raise ValidationError(_("Seuls les fonds actifs peuvent être suspendus."))
            record.state = 'suspended'
            record.message_post(body=_("Le fond a été suspendu."))

    def action_liquidate(self):
        for record in self:
            if record.state not in ('active', 'suspended'):
                raise ValidationError(_("Seuls les fonds actifs ou suspendus peuvent être liquidés."))
            record.state = 'liquidated'
            record.message_post(body=_("Le fond a été liquidé."))

    def action_reset_to_draft(self):
        pass

    def action_show_timeline(self):
        pass

    def action_show_currency(self):
        pass


