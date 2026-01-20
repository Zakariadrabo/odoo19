import logging

from odoo import models, api
_logger = logging.getLogger(__name__)

class InvestorPortfolioReport(models.AbstractModel):
    _name = 'report.efund_investor_portfolio_report'
    _description = 'Rapport portefeuille investisseur'

    @api.model
    def _get_report_values(self, docids, data=None):
        wizard = self.env['efund.investor.portfolio.report.wizard'].browse(docids)
        investor = wizard.investor_id

        part_accounts = self.env['efund.investor.part'].search([
            ('investor_id', '=', investor.id),
            ('state', '=', 'active'),
        ])

        lines = []
        for part in part_accounts:
            lines.append(part.get_fund_portfolio_data())

        return {
            'doc_ids': docids,
            'doc_model': 'efund.investor',
            'docs': wizard,
            'investor': investor,
            'lines': lines,
        }
