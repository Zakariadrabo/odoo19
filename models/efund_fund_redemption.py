# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import models, fields, api, _
from odoo.exceptions import UserError


class FundRedemption(models.Model):
    _name = 'efund.fund.redemption'
    _description = 'Ordre de rachat de parts OPCVM'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'request_date desc, id desc'

    # -------------------------
    # IDENTITÉ / CONTEXTE
    # -------------------------

    name = fields.Char(
        string="Référence",
        readonly=True,
        copy=False,
        default=lambda self: _('New')
    )

    investor_id = fields.Many2one(
        'efund.investor',
        string="Investisseur",
        required=True,
        index=True,
        tracking=True
    )

    account_part_id = fields.Many2one(
        'efund.account.part',
        string="Compte titres",
        required=True,
        index=True
    )

    fund_id = fields.Many2one(
        'efund.fund',
        string="Fonds",
        required=True,
        index=True
    )

    company_id = fields.Many2one(
        'res.company',
        string="Société (Fonds)",
        related='fund_id.company_id',
        store=True,
        index=True,
        readonly=True
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='company_id.currency_id',
        store=True,
        readonly=True
    )

    # -------------------------
    # DONNÉES RACHAT
    # -------------------------

    redemption_type = fields.Selection(
        [
            ('partial', 'Rachat partiel'),
            ('total', 'Rachat total'),
        ],
        string="Type de rachat",
        required=True,
        tracking=True
    )

    parts = fields.Float(
        string="Nombre de parts",
        required=True,
        tracking=True
    )

    nav_date = fields.Date(
        string="Date VL appliquée",
        required=True,
        tracking=True
    )

    nav_value = fields.Monetary(
        string="VL appliquée",
        tracking=True
    )

    amount = fields.Monetary(
        string="Montant du rachat",
        compute='_compute_amount',
        store=True,
        tracking=True
    )

    request_date = fields.Datetime(
        string="Date de demande",
        default=fields.Datetime.now,
        readonly=True
    )

    execution_date = fields.Datetime(
        string="Date d’exécution",
        readonly=True
    )

    # -------------------------
    # STATUT / WORKFLOW
    # -------------------------

    state = fields.Selection(
        [
            ('draft', 'Brouillon'),
            ('submitted', 'Soumis'),
            ('validated', 'Validé'),
            ('executed', 'Exécuté'),
            ('rejected', 'Rejeté'),
            ('cancelled', 'Annulé'),
        ],
        string="Statut",
        default='draft',
        tracking=True
    )

    rejection_reason = fields.Text(string="Motif du rejet")

    nav_id = fields.Many2one('efund.fund.nav',string="VL appliquée",readonly=True)

    # -------------------------
    # CONTRAINTES & COMPUTE
    # -------------------------

    @api.depends('parts', 'nav_value')
    def _compute_amount(self):
        for rec in self:
            rec.amount = (rec.parts or 0.0) * (rec.nav_value or 0.0)

    @api.constrains('parts')
    def _check_parts_positive(self):
        for rec in self:
            if rec.parts <= 0:
                raise UserError(_("Le nombre de parts doit être strictement positif."))

    # -------------------------
    # CREATE / SEQUENCE
    # -------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('name', _('New')) == _('New'):
                vals['name'] = self.env['ir.sequence'].next_by_code(
                    'efund.fund.redemption'
                ) or _('New')
        return super().create(vals_list)

    # -------------------------
    # ACTIONS METIER
    # -------------------------

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.state = 'submitted'

    def action_validate(self):
        for rec in self:
            if rec.state != 'submitted':
                continue
            rec.state = 'validated'

    def action_reject(self, reason=None):
        for rec in self:
            rec.state = 'rejected'
            if reason:
                rec.rejection_reason = reason

    def action_execute(self):
        """
        Exécution effective du rachat :
        - décrémentation des parts
        - génération écriture comptable (plus tard)
        """
        for rec in self:
            if rec.state != 'validated':
                raise UserError(_("Le rachat doit être validé avant exécution."))

            account = rec.account_part_id

            if rec.parts > account.total_parts:
                raise UserError(_("Parts insuffisantes pour exécuter le rachat."))

            # décrémentation des parts
            account.sudo().write({
                'total_parts': account.total_parts - rec.parts
            })

            rec.write({
                'state': 'executed',
                'execution_date': fields.Datetime.now(),
            })

    def action_cancel(self):
        for rec in self:
            if rec.state in ('executed',):
                raise UserError(_("Un rachat exécuté ne peut pas être annulé."))
            rec.state = 'cancelled'

    def _get_validated_nav(self, nav_date):
        self.ensure_one()

        nav = self.env['efund.fund.nav'].search([
            ('fund_id', '=', self.fund_id.id),
            ('nav_date', '=', nav_date),
            ('state', 'in', ('validated', 'published')),
        ], limit=1)

        if not nav:
            raise UserError(
                _("Aucune VL validée disponible pour la date %s.") % nav_date
            )

        return nav

    def action_validate(self):
        for rec in self:
            if rec.state != 'submitted':
                continue

            nav = rec._get_validated_nav(rec.nav_date)

            rec.write({
                'nav_id': nav.id,
                'nav_value': nav.nav_value,
                'state': 'validated',
            })

    def _compute_effective_nav_date(self):
        self.ensure_one()
        delay_map = {'J': 'J','J1': 'J+1','J2': 'J+2',}
        delay = delay_map.get(self.fund_id.redemption_delay, 'J2')
        return self.request_date.date() + timedelta(days=delay)

    def action_submit(self):
        for rec in self:
            if rec.state != 'draft':
                effective_date = rec._compute_effective_nav_date()
                rec.write({
                    'nav_date': effective_date,
                    'state': 'submitted',
                })

