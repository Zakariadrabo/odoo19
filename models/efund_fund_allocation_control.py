from odoo import models, fields, api


class EfundFundAllocationControl(models.Model):
    _name = 'efund.fund.allocation.control'
    _description = 'Contrôle de conformité d’allocation'
    _order = 'date desc'

    fund_id = fields.Many2one('efund.fund',required=True)
    snapshot_id = fields.Many2one('efund.fund.allocation.snapshot',required=True)
    fund_type_id = fields.Many2one(related='fund_id.fund_type_id',store=True)
    date = fields.Date(related='snapshot_id.date',store=True)
    state = fields.Selection([
        ('compliant', 'Conforme'),
        ('warning', 'Alerte'),
        ('breach', 'Dépassement'),
    ], default='compliant')
    message = fields.Text()

    def action_check_compliance(self):
        self.ensure_one()
        ft = self.fund_type_id
        s = self.snapshot_id

        breaches = []

        if not (ft.min_equity_pct <= s.equity_pct <= ft.max_equity_pct):
            breaches.append("Actions hors limites")
        if not (ft.min_bond_pct <= s.bond_pct <= ft.max_bond_pct):
            breaches.append("Obligations hors limites")
        if not (ft.min_cash_pct <= s.cash_pct <= ft.max_cash_pct):
            breaches.append("Liquidités hors limites")
        if breaches:
            self.state = 'breach'
            self.message = "\n".join(breaches)
        else:
            self.state = 'compliant'
            self.message = "Allocation conforme à la réglementation"
