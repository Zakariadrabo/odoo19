import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FundInstrumentDAT(models.Model):
    _name = "efund.vehicule.instrument.core.dat"
    _description = "Dépôt à Terme (DAT)"
    _inherits = {'efund.vehicule.instrument.core': 'instrument_id'}
    _inherit = ['mail.thread', 'mail.activity.mixin']

    @api.model
    def _get_default_currency(self):
        return self.env.company.currency_id

    instrument_id = fields.Many2one('efund.vehicule.instrument.core', required=True, ondelete='cascade')
    currency_id = fields.Many2one('res.currency',string='Devise', default=_get_default_currency)

    # Détails du contrat
    bank_id = fields.Many2one('efund.bank', string="Banque de dépôt", required=True)
    account_number = fields.Char(string="Numéro de compte DAT")
    amount_deposit = fields.Monetary(string="Montant placé", required=True)
    interest_rate = fields.Float(string="Taux d'intérêt (%)", digits=(16, 4))
    start_date = fields.Date(string="Date de mise en place", default=fields.Date.today)
    end_date = fields.Date(string="Date d'échéance", required=True)

    # Calcul des intérêts
    interest_calculation_type = fields.Selection([('360', '360 jours (Standard)'), ('365', '365 jours')], default='360', string="Base de calcul")
    duration_days = fields.Integer(string="Durée (jours)", compute="_compute_duration", store=True)
    accrued_interest = fields.Monetary(string="Intérêts courus", compute="_compute_dat_interests")
    #tax_rate = fields.Float(string="Taux de IRCM/IRVM (%)", digits=(16, 4))
    rate_vat = fields.Float(string="Taux Net (%)", digits=(16, 4), compute="_compute_rate_vat", store=True)
    interest_type = fields.Selection([('postpaid', 'Post-compté'), ('prepaid', 'Précompté')], default='postpaid', string="Type d'intérêt")

    # champs ajoutés
    # Champs calculés
    remaining_days = fields.Integer(string="Jours restants", compute="_compute_remaining_days")
    daily_interest_rate = fields.Float(string="Taux journalier", compute="_compute_daily_rate", digits=(16, 6))
    days_elapsed = fields.Integer(string="Jours écoulés", compute="_compute_days_elapsed")
    estimated_value = fields.Monetary(string="Valeur estimée", compute="_compute_estimated_value")

    # Gestion d'état
    state = fields.Selection([('draft', 'Brouillon'), ('active', 'Actif'), ('matured', 'Échu'), ('cancelled', 'Annulé')], string="État", default='draft', tracking=True)

    # Suivi
    last_calculation_date = fields.Date(string="Dernier calcul", readonly=True)
    transaction_count = fields.Integer(string="Transactions", compute="_compute_transaction_count")


    capitalization_frequency = fields.Selection(
        [
            ('monthly', 'Mensuelle'),
            ('quarterly', 'Trimestrielle'),
            ('at_maturity', 'À échéance'),
        ],
        default='at_maturity'
    )

    # ---------------------------------------------------------
    # LIQUIDITÉ & PÉNALITÉS
    # ---------------------------------------------------------
    early_withdrawal_allowed = fields.Boolean(string='Sortie anticipée autorisée',default=False)
    early_withdrawal_penalty_rate = fields.Float(string='Pénalité sortie anticipée (%)')
    liquidity_level = fields.Selection([('high', 'Haute'),('medium', 'Moyenne'),('low', 'Faible'),], default='medium')

    @api.depends('interest_rate', 'tax_rate')
    def _compute_rate_vat(self):
        for rec in self:
            rec.rate_vat = rec.interest_rate * (1 - rec.tax_rate / 100)

    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for dat in self:
            if dat.start_date and dat.end_date:
                dat.duration_days = (dat.end_date - dat.start_date).days

    """
    def _compute_dat_interests(self):
        
        today = fields.Date.today()
        for dat in self:
            if dat.start_date and today > dat.start_date:
                # On ne calcule des intérêts que jusqu'à l'échéance
                calculation_date = min(today, dat.end_date)
                days_elapsed = (calculation_date - dat.start_date).days
                base = int(dat.interest_calculation_type)
                dat.accrued_interest = (dat.amount_deposit * (dat.interest_rate / 100) * days_elapsed) / base
            else:
                dat.accrued_interest = 0.0
    """


    def action_view_interest_details(self):
        pass

    @api.depends('start_date', 'end_date')
    def _compute_duration(self):
        for dat in self:
            if dat.start_date and dat.end_date:
                dat.duration_days = (dat.end_date - dat.start_date).days
            else:
                dat.duration_days = 0

    @api.depends('start_date', 'end_date', 'state')
    def _compute_remaining_days(self):
        today = fields.Date.today()
        for dat in self:
            if dat.state == 'active' and dat.end_date:
                dat.remaining_days = max(0, (dat.end_date - today).days)
            else:
                dat.remaining_days = 0

    @api.depends('interest_rate', 'interest_calculation_type')
    def _compute_daily_rate(self):
        for dat in self:
            base = int(dat.interest_calculation_type) if dat.interest_calculation_type else 360
            dat.daily_interest_rate = (dat.interest_rate / 100) / base

    @api.depends('start_date')
    def _compute_days_elapsed(self):
        today = fields.Date.today()
        for dat in self:
            if dat.start_date and dat.start_date <= today:
                dat.days_elapsed = (today - dat.start_date).days
            else:
                dat.days_elapsed = 0

    @api.depends('amount_deposit', 'accrued_interest')
    def _compute_estimated_value(self):
        for dat in self:
            dat.estimated_value = dat.amount_deposit + dat.accrued_interest

    @api.depends('interest_calculation_type','start_date', 'end_date','amount_deposit','interest_rate')
    def _compute_dat_interests(self):
        """Calcul quotidien des intérêts courus pour la VL"""
        today = fields.Date.today()
        for dat in self:
            if dat.start_date and today > dat.start_date:
                # On ne calcule des intérêts que jusqu'à l'échéance

                calculation_date = min(today, dat.end_date) if dat.end_date else today
                days_elapsed = (calculation_date - dat.start_date).days
                base = int(dat.interest_calculation_type) if dat.interest_calculation_type else 360
                dat.accrued_interest = (dat.amount_deposit * (dat.interest_rate / 100) * days_elapsed) / base
                dat.last_calculation_date = today
            else:
                dat.accrued_interest = 0.0



    # Méthodes d'action
    def action_compute_interests(self):
        self._compute_dat_interests()
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Intérêts recalculés',
                'message': f'Les intérêts ont été recalculés pour {len(self)} DAT(s)',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_close_dat(self):
        self.write({'state': 'matured'})


    @api.model
    def _update_state_cron(self):
        """Cron pour mettre à jour l'état des DAT"""
        today = fields.Date.today()
        active_dats = self.search([('state', '=', 'active')])
        for dat in active_dats:
            if dat.end_date and dat.end_date < today:
                dat.state = 'matured'

    def action_activate(self):
        for record in self:
            if not record.start_date:
                raise ValidationError(_("Merci de saisir la date d'opération."))
            record.state = 'active'
            record.message_post(body=_("Le fond a été activé."))

    def action_suspend(self):
        for record in self:
            if record.state != 'active':
                raise ValidationError(_("Seuls les fonds actifs peuvent être suspendus."))
            record.state = 'suspended'
            record.message_post(body=_("Le fond a été suspendu."))

    def action_liquidate(self):
        for record in self:
            if record.state not in ('active', 'suspended'):
                raise ValidationError(_("Seuls les fonds actifs ou suspendus peuvent être liquidés."))
            record.state = 'liquidated'
            record.message_post(body=_("Le fond a été liquidé."))

    def action_reset_to_draft(self):
        pass
