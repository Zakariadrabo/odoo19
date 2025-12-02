# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime
import logging

_logger = logging.getLogger(__name__)

class FundValuation(models.Model):
    _name = "efund.fund.valuation"
    _description = "Fund Valuation"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _rec_name = "name"

    name = fields.Char(string="Reference", readonly=True, default="/")
    fund_id = fields.Many2one("efund.fund", string="Fund", required=True, ondelete="cascade")
    company_id = fields.Many2one(related="fund_id.company_id", store=True, readonly=True)
    valuation_date = fields.Date(string="Valuation Date", required=True, default=fields.Date.context_today)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('in_progress', 'In Progress'),
        ('validated', 'Validated'),
        ('cancelled', 'Cancelled'),
    ], string="Status", default='draft', tracking=True)

    valuation_type = fields.Selection([
        ('daily', 'Daily'),
        ('weekly', 'Weekly'),
        ('monthly', 'Monthly'),
    ], string="Valuation Frequency", default="daily")

    # Global NAV metrics
    total_assets = fields.Monetary(string="Total Assets", currency_field='currency_id')
    total_liabilities = fields.Monetary(string="Total Liabilities", currency_field='currency_id')
    net_assets = fields.Monetary(string="Net Assets", currency_field='currency_id', compute="_compute_net_assets", store=True)
    nav_per_share = fields.Monetary(string="NAV per Share", currency_field='currency_id', compute="_compute_nav_per_share", store=True)

    total_shares = fields.Float(string="Total Outstanding Shares", required=True, default=1.0)
    currency_id = fields.Many2one(related='fund_id.currency_id', store=True, readonly=True)

    valuation_line_ids = fields.One2many("efund.fund.valuation.line", "valuation_id", string="Valuation Lines")
    fee_line_ids = fields.One2many("efund.fund.valuation.fee", "valuation_id", string="Fees")
    log_ids = fields.One2many("efund.fund.valuation.log", "valuation_id", string="Valuation Logs")

    computed_by = fields.Many2one("res.users", string="Computed By")
    validated_by = fields.Many2one("res.users", string="Validated By")
    validation_date = fields.Datetime(string="Validation Date")

    notes = fields.Text(string="Comments / Observations")

    def _prepare_vals_sequence(self, vals):
        """Prépare les valeurs avec séquence automatique"""
        if vals.get("name", "/") == "/":
            vals["name"] = self.env["ir.sequence"].sudo().next_by_code("efund.fund.valuation") or "/"
        return vals

    @api.model
    def create(self, vals):
        if isinstance(vals, list):
            vals = [self._prepare_vals_sequence(v) for v in vals]
        else:
            vals = self._prepare_vals_sequence(vals)

        records = super().create(vals)
        for rec in records:
            rec._log_action("create", _("Valuation created."))
        return records

    def write(self, vals):
        res = super().write(vals)
        # log update
        for rec in self:
            rec._log_action("write", _("Valuation updated."))
        return res


    @api.depends('total_assets', 'total_liabilities')
    def _compute_net_assets(self):
        for rec in self:
            rec.net_assets = (rec.total_assets or 0) - (rec.total_liabilities or 0)

    @api.depends('net_assets', 'total_shares')
    def _compute_nav_per_share(self):
        for rec in self:
            rec.nav_per_share = rec.net_assets / rec.total_shares if rec.total_shares else 0.0

    def action_refresh_lines(self):
        """
        Refresh valuation lines from positions.
        Expected existing model: fund.position with fields: fund_id, instrument_id, quantity, currency_id.
        If fund.position doesn't exist, fallback is no-op.
        """
        Position = self.env.get("efund.fund.position")
        Instrument = self.env.get("efund.fund.instrument")
        for rec in self:
            # clear lines
            rec.valuation_line_ids.unlink()
            if not Position:
                _logger.debug("model fund.position not found, skipping refresh lines")
                rec._log_action("refresh_lines", "No fund.position model found - refresh skipped")
                continue
            positions = Position.search([("fund_id", "=", rec.fund_id.id)])
            lines = []
            for pos in positions:
                # attempt to get market price - prefer instrument last_price if available
                unit_price = 0.0
                if hasattr(pos, "market_price") and pos.market_price:
                    unit_price = pos.market_price
                elif Instrument and pos.instrument_id:
                    unit_price = Instrument.get_market_price(pos.instrument_id.id, rec.valuation_date) if hasattr(Instrument, "get_market_price") else getattr(pos, "unit_price", 0.0)
                else:
                    unit_price = getattr(pos, "unit_price", 0.0)
                lines.append((0, 0, {
                    "instrument_id": pos.instrument_id.id if pos.instrument_id else False,
                    "quantity": pos.quantity,
                    "unit_price": unit_price,
                    "currency_id": rec.currency_id.id,
                }))
            if lines:
                rec.valuation_line_ids = lines
                rec._log_action("refresh_lines", _("Refreshed %s valuation lines from positions.") % len(lines))
        return True

    def action_compute(self):
        """
        Compute totals from valuation_line_ids and fee_line_ids, fill total_assets, total_liabilities,
        compute net_assets and nav_per_share.
        This is synchronous and intended for moderate portfolio sizes. For large portfolios use batch jobs.
        """
        for rec in self:
            rec.write({"state": "in_progress", "computed_by": self.env.user.id})
            total_assets = 0.0
            for line in rec.valuation_line_ids:
                # ensure market_value is computed
                line._compute_market_value()
                total_assets += line.market_value or 0.0

            total_liabilities = 0.0
            for fee in rec.fee_line_ids:
                total_liabilities += fee.amount or 0.0

            rec.total_assets = total_assets
            rec.total_liabilities = total_liabilities
            # dependents will compute
            rec._compute_net_assets()
            rec._compute_nav_per_share()
            rec._log_action("compute", _("Computed valuation: Assets=%s Liabilities=%s NAV=%s") %
                            (rec.total_assets, rec.total_liabilities, rec.nav_per_share))
        return True

    def action_validate(self):
        """
        Lock the valuation. Optionally post accounting entries or export reports.
        """
        for rec in self:
            if rec.state == "validated":
                continue
            # business checks
            if not rec.valuation_line_ids:
                raise ValidationError(_("Valuation lines are empty. Cannot validate."))
            rec.state = "validated"
            rec.validated_by = self.env.user.id
            rec.validation_date = fields.Datetime.now()
            rec._log_action("validate", _("Valuation validated by %s") % (self.env.user.name))
        return True

    def action_cancel(self):
        for rec in self:
            rec.state = "cancelled"
            rec._log_action("cancel", _("Valuation cancelled."))
        return True

    # ------------------------------
    # Accounting helper (placeholder)
    # ------------------------------
    def action_accounting_entries(self):
        """
        Optional: generate accounting entries for the valuation (e.g. mark-to-market adjustments).
        This is highly dependent on your chart of accounts. Implement as needed.
        """
        AccountMove = self.env["account.move"]
        for rec in self:
            # Example: create a summarized move if there are adjustments
            journal = self.env["account.journal"].search([("company_id", "=", rec.company_id.id), ("type", "=", "general")], limit=1)
            if not journal:
                _logger.warning("No general journal for company %s", rec.company_id and rec.company_id.name)
                continue
            move_vals = {
                "journal_id": journal.id,
                "date": rec.valuation_date,
                "company_id": rec.company_id.id,
                "line_ids": [],
            }
            # This is placeholder logic: you must map to real accounts
            # e.g. debit P&L / credit asset revaluation etc.
            move = AccountMove.create(move_vals)
            try:
                move.post()
            except Exception:
                _logger.exception("Cannot post move for valuation %s", rec.id)
            rec._log_action("accounting", _("Accounting move created: %s") % (move.name or move.id))
        return True

    # ------------------------------
    # Logging helper
    # ------------------------------
    def _log_action(self, action, message):
        for rec in self:
            self.env["efund.fund.valuation.log"].create({
                "valuation_id": rec.id,
                "action": action,
                "message": message,
                "user_id": self.env.user.id,
            })
