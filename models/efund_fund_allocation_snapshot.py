from odoo import models, fields, api


class EfundFundAllocationSnapshot(models.Model):
    _name = 'efund.fund.allocation.snapshot'
    _description = 'Snapshot de composition du fonds'
    _order = 'date desc'

    fund_id = fields.Many2one('efund.fund',required=True)
    date = fields.Date(default=fields.Date.today,required=True)
    total_nav = fields.Monetary(string="Actif net total",required=True)
    currency_id = fields.Many2one(related='fund_id.currency_id',store=True)
    line_ids = fields.One2many('efund.fund.allocation.snapshot.line','snapshot_id',string="Détail par classe d’actifs")
