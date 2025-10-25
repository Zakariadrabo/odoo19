from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, date, timedelta
import json
import logging

_logger = logging.getLogger(__name__)


class FundInvestor(models.Model):
    _name = "efund.investor"
    _description = "Investor / Porteur - KYC record"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "id desc"

    partner_id = fields.Many2one('res.partner', string="Partner", required=True, ondelete='cascade',
                                 domain="[('is_investor', '=', True)]", context="{'default_is_investor': True}" )
    company_id = fields.Many2one('res.company', string="Context Company (Fund)", required=True, index=True)
    name = fields.Char(related="partner_id.name", store=True, readonly=True)
    status = fields.Selection([
        ('draft', 'Draft'),
        ('kyc_pending', 'KYC Pending'),
        ('kyc_approved', 'KYC Approved'),
        ('kyc_rejected', 'KYC Rejected'),
        ('archived', 'Archived')
    ], default='draft')
    kyc_level = fields.Selection([('low', 'Low'), ('medium', 'Medium'), ('high', 'High')], default='low')
    kyc_score = fields.Integer(default=0)
    kyc_last_update = fields.Datetime()
    kyc_operator_id = fields.Many2one('res.users', string="KYC Operator")
    pep_flag = fields.Boolean(default=False)
    sanctions_flag = fields.Boolean(default=False)
    risk_category = fields.Char()
    whitelisted = fields.Boolean(default=False)
    notes = fields.Text()
    document_ids = fields.One2many('efund.kyc.document', 'investor_id', string="KYC Documents")
    kyc_check_ids = fields.One2many('efund.kyc.check', 'investor_id', string="KYC Checks")
    aml_alert_ids = fields.One2many('efund.aml.alert', 'investor_id', string="AML Alerts")
    active = fields.Boolean(default=True)

    # Relations vers comptes
    account_part_ids = fields.One2many('efund.account.part', 'investor_id', string='Comptes Parts / Actions')
    account_cash_ids = fields.One2many('efund.account.cash', 'investor_id', string='Comptes Espèces')

    def action_create_aml_alert(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('New AML Alert'),
            'res_model': 'efund.aml.alert',
            'view_mode': 'form',
            'context': {
                'default_investor_id': self.id,
                'default_fund_id': self.company_id.id,
            },
            'target': 'current',
        }

    @api.model
    def create(self, vals):
        # If partner has active investor flags, could copy some data
        inv = super().create(vals)
        # Run initial screening asynchronously if desired
        try:
            inv._schedule_initial_screening()
        except Exception:
            _logger.exception("Initial screening scheduling failed for investor %s", inv.id)
        return inv

    def _schedule_initial_screening(self):
        """Schedule screening - simple immediate call or use queue_job/cron in production"""
        for rec in self:
            # Call synchronous for now (or use delay)
            rec._run_screening()

    def _run_screening(self):
        """Run screening: PEP and sanctions checks + compute kyc_score via engine"""
        for rec in self:
            # Reset flags
            rec.sudo().write({'pep_flag': False, 'sanctions_flag': False})
            # Placeholder for external check: replace with real connector
            try:
                # Mocked checks (in production call external API)
                # Example: call self.env['kyc.provider'].check_person(name, dob, ...) -> result dict
                result = self._mocked_external_checks()
                rec.sudo().write({
                    'pep_flag': result.get('pep', False),
                    'sanctions_flag': result.get('sanctions', False),
                })
            except Exception:
                _logger.exception("Screening failed for investor %s", rec.id)
            # Compute score
            score = self.env['fund.aml.engine'].compute_score_for_investor(rec.id)
            rec.sudo().write({'kyc_score': score, 'kyc_last_update': fields.Datetime.now()})
            # Set status according to thresholds (configurable rules can override)
            if rec.kyc_score >= 80 or rec.sanctions_flag:
                rec.sudo().write({'status': 'kyc_pending', 'kyc_level': 'high'})
                # Create an AML alert if sanctions found
                if rec.sanctions_flag:
                    self.env['fund.aml.alert'].create({
                        'investor_id': rec.id,
                        'fund_id': rec.company_id.id,
                        'trigger': 'sanctions_match',
                        'severity': 'critical',
                        'status': 'new',
                        'notes': _('Sanctions match detected during initial screening.')
                    })
            elif rec.kyc_score >= 40:
                rec.sudo().write({'status': 'kyc_pending', 'kyc_level': 'medium'})
            else:
                rec.sudo().write({'status': 'kyc_approved', 'kyc_level': 'low'})

    def _mocked_external_checks(self):
        """
        Replace this method by a connector call to a sanctions/pep provider.
        Returns a dict: {'pep': bool, 'sanctions': bool}
        """
        # Very simple heuristic: mark PEP if name contains 'Prez' (demo only)
        name = (self.partner_id.name or "").lower()
        return {'pep': 'prez' in name, 'sanctions': 'blocked' in name}

    def action_request_more_info(self):
        for rec in self:
            rec.message_post(body=_("Request more documents / clarification for KYC"), subject=_("KYC: Request info"))
            rec.status = 'kyc_pending'
            # create activity
            self.env['mail.activity'].create({
                'res_id': rec.id,
                'res_model_id': self.env['ir.model']._get('fund.investor').id,
                'activity_type_id': self.env.ref('mail.mail_activity_data_todo').id,
                'summary': _('Request KYC documents'),
                'user_id': rec.kyc_operator_id.id or self.env.uid,
            })

    def action_approve_kyc(self):
        for rec in self:
            rec.status = 'kyc_approved'
            rec.kyc_level = 'low' if rec.kyc_score < 40 else rec.kyc_level
            rec.message_post(body=_("KYC Approved"), subject=_("KYC"))

    def action_reject_kyc(self, reason=False):
        for rec in self:
            rec.status = 'kyc_rejected'
            body = _("KYC Rejected")
            if reason:
                body = "%s: %s" % (body, reason)
            rec.message_post(body=body, subject=_("KYC"))
            # Optionally create an AML alert record
            self.env['fund.aml.alert'].create({
                'investor_id': rec.id,
                'fund_id': rec.company_id.id,
                'trigger': 'kyc_rejection',
                'severity': 'critical',
                'status': 'new',
                'notes': reason or _('KYC rejected by operator.')
            })



