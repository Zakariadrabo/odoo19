from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
class EfundAccountPartMove(models.Model):
    _name = 'efund.investor.part.move'
    _description = 'Mouvements compte titres'

    name = fields.Char(string="Référence", required=True,
                       default=lambda self: self.env['ir.sequence'].next_by_code('efund.investor.part.move'))
    part_account_id = fields.Many2one('efund.investor.part', required=True)
    fund_id = fields.Many2one(related='part_account_id.fund_id',store=True)
    company_id = fields.Many2one(related='fund_id.company_id', store=True)
    currency_id = fields.Many2one(related='fund_id.currency_id', store=True)
    investor_id = fields.Many2one(related='part_account_id.investor_id',store=True)
    move_type = fields.Selection([('subscription','Souscription'),('redemption','Rachat'),('deposit','Déposit'),('withdraw', 'Retrait')], required=True)
    shares = fields.Float(required=True)
    date_move = fields.Datetime(default=fields.Datetime.now)
    value_date = fields.Datetime(string="Date comptable")
    state = fields.Selection(
        [('draft', 'Brouillon'), ('pending', 'En Attente'), ('posted', 'Validé'), ('cancelled', 'Annulé'),
         ], string="Statut", default='draft')
    # Références aux transactions investisseurs
    investor_cash_move_id = fields.Many2one('efund.investor.cash.move', string="Mouvement Investisseur")
    subscription_id = fields.Many2one('efund.investor.subscription', string="Ordre de Souscription")
    redemption_id = fields.Many2one('efund.investor.redemption', string="Ordre de Rachat")

    # Informations complémentaires
    journal_id = fields.Many2one('account.journal', string="Journal Comptable")
    account_move_id = fields.Many2one('account.move', string="Écriture Comptable")



