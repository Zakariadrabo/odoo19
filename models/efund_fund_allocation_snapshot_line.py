from odoo import models, fields, api

class EfundFundAllocationSnapshotLine(models.Model):
    _name = 'efund.fund.allocation.snapshot.line'
    _description = 'Détail snapshot par classe d’actifs'

    snapshot_id = fields.Many2one('efund.fund.allocation.snapshot',required=True,ondelete='cascade')
    asset_class_id = fields.Many2one('efund.asset.class',required=True)
    amount = fields.Monetary(string="Valeur de marché",required=True)
    percentage = fields.Float(string="Pourcentage",compute='_compute_percentage',store=True)
    currency_id = fields.Many2one(related='snapshot_id.currency_id',store=True)

    @api.depends('amount', 'snapshot_id.total_nav')
    def _compute_percentage(self):
        for rec in self:
            if rec.snapshot_id.total_nav:
                rec.percentage = (rec.amount / rec.snapshot_id.total_nav) * 100
            else:
                rec.percentage = 0.0
