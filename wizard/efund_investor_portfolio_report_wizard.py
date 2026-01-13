from odoo import models, fields


class InvestorPortfolioReportWizard(models.TransientModel):
    _name = 'efund.investor.portfolio.report.wizard'
    _description = 'Wizard état du portefeuille investisseur'

    investor_id = fields.Many2one(
        'efund.investor',
        string="Investisseur",
        required=True
    )

    def action_print_report(self):
        return self.env.ref('efundOpc.action_efund_investor_portfolio_report').report_action(self)
