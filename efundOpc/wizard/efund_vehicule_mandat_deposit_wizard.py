import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class EfundVehiculeMandatDepositWizard(models.TransientModel):
    _name = 'efund.vehicule.mandat.deposit.wizard'
    _description = 'Wizard pour faire le déposit du mandat'


    mandate_id = fields.Many2one('efund.vehicule.mandate', string='Mandat', required=True)
    deposit_amount = fields.Monetary(string='Montant du déposit', required=True)
    deposit_date = fields.Date(string='Date du déposit', required=True)
    currency_id = fields.Many2one('res.currency', related='mandate_id.currency_id', string='Devise', readonly=True)

    def action_confirm_deposit(self):
        self.ensure_one()
        cash_account = self.env['efund.investor.cash_account'].search([('vehicule_id', '=', self.mandate_id.vehicule_id.id)])
        if not cash_account:
            self.env['efund.investor.cash_account'].create({
                'name': f"Compte Espèces - {self.mandate_id.investor_id.full_name or self.mandate_id.investor_id.name or self.mandate_id.investor_id.company_name or 'Investor'}",
                'investor_id': self.mandate_id.investor_id.id,
                'account_number': self.mandate_id.investor_id._generate_account_number('cash'), #self._get_investor_account(self.mandate_id.investor_id),
                'vehicule_id': self.mandate_id.vehicule_id.id,
                'balance': 0,
                'state': 'active',
            })



        investor_cash_account_id = self.env['efund.investor.cash_account'].get_cash_account_id_investor_by_vehicule_and_investor_id(
            self.mandate_id.vehicule_id.id, self.mandate_id.investor_id.id)

        investor_cash_move = self.env['efund.investor.cash_account.move'].create({
            'name': self.env['ir.sequence'].next_by_code('efund.investor.cash_account.move'),
            'cash_account_id': investor_cash_account_id,
            'move_type': 'deposit',
            'amount': self.deposit_amount,
            'date': self.deposit_date,
            'state': 'reconciled'
        })



        mandat = self.env['efund.vehicule.mandate'].search([('id', '=', self.mandate_id.id)])
        if mandat:
            mandat.message_post(
                body=_("Crédit du compte cash investisseur au montant de %s.") % (self.deposit_amount),
                subject="comptabilisation du déposit",
                message_type="comment",
                subtype_xmlid="mail.mt_comment")

            mandat.write({'is_fund_released': True})



