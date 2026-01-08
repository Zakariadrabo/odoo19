import logging
from datetime import date
from email.policy import default

from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError, UserError

_logger = logging.getLogger(__name__)


class FundInstrument(models.Model):
    _name = "efund.fund.instrument"
    _description = "Instrument Financier (OPCVM)"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "name"

    # ----------------------------------------------------
    # IDENTIFICATION
    # ----------------------------------------------------
    name = fields.Char(string="Libellé", required=True)
    isin = fields.Char(string="Code ISIN", index=True)
    ticker = fields.Char(string="Ticker / Mnémo")

    instrument_type = fields.Selection([('equity', 'Action / Equity'),('bond', 'Obligation'),('tcn', 'TCN / Titre de Créance Négociable'),
        ('right', 'Droit / Warrant / Option'),('mmf', 'Monétaire / Cash'),('other', 'Autre'),
    ], default='other', required=True, string="Type d’instrument")
    currency_id = fields.Many2one('res.currency', string="Devise", required=True)
    state = fields.Selection([('draft', 'Brouillon'),('pending', 'Vérification'),('approved', 'Approuvé'),('archived', 'Archivé')
    ], default='draft')
    is_listed = fields.Boolean(string='Est Coté',default=True,tracking=True,help="Indique si l'instrument est coté")
    listing_date = fields.Date(string='Date 1ère Cotation', tracking=True, help="Indique la date de la 1ère cotation")
    last_validated_price = fields.Float(compute='_compute_last_validated_price', string="Dernier cours validé",digits=(16, 4))
    last_price_date = fields.Date(compute='_compute_last_validated_price', string="Date dernier cours")
    sector = fields.Selection([('agriculture', 'Agriculture'),('industrie', 'Industrie'),], string="Secteur d'activités")

    #--------------------------------------------------------
    #  RELATIONS
    #--------------------------------------------------------
    price_ids = fields.One2many('efund.fund.instrument.price', 'instrument_id', string="Prix")
    issuer_id = fields.Many2one("efund.instrument.issuer",string="Émetteur",help="Institution ou entreprise qui émet l'instrument financier.")
    market = fields.Selection([('brvm', 'BRVM'), ('bvmac', 'BVMAC'), ('other', 'Autre marché'), ],string="Marché Principal", default='bvmac')
    custodian = fields.Selection([('dcbr', 'DC/BR'), ('bceao', 'BCEAO'), ('autre', 'Autre'), ], default='dcbr',string="Dépositaire", )
    asset_class_id = fields.Many2one('efund.asset.class',string="Classe d'actif",required=True)

    market_price_source = fields.Selection([('brvm_api', 'BRVM – API officielle'),('manual', 'Saisie manuelle'),('datasource', 'Autre data provider'),
    ], string="Source du Prix")
    import_config_id = fields.Many2one('efund.fund.instrument.price.import', string="Configuration d'import")



    # ----------------------------------------------------
    # CARACTÉRISTIQUES SPÉCIFIQUES PAR TYPE
    # ----------------------------------------------------

    # --- ACTIONS ---
    equity_dividend_yield = fields.Float(string="Dividend Yield (%)")


    # --- OBLIGATIONS ---
    bond_type = fields.Selection([
        ('fixed_rate', 'Taux Fixe'),
        ('floating_rate', 'Floating Rate Note (FRN)'),
        ('zero_coupon', 'Zero Coupon Bond'),
        ('convertible', 'Convertible Bond'),
        ('perpetual', 'Perpetual Bond'),
        ('inflation_linked', 'Inflation-Linked Bond'),
    ], string='Type Obligation',
        # required=True,
        default='fixed_rate')
    bond_issuer_rating = fields.Selection([
        ('aaa', 'AAA'),
        ('aa', 'AA'),
        ('a', 'A'),
        ('bbb', 'BBB'),
        ('bb', 'BB'),
        ('b', 'B'),
        ('ccc', 'CCC'),
        ('cc', 'CC'),
        ('c', 'C'),
        ('d', 'D (Default)'),
    ], string='Credit Rating', tracking=True)
    rating_agency = fields.Char(string='Rating Agency')
    bond_amortization_ids = fields.One2many(
        'efund.bond.amortization',
        'instrument_id',
        string="Bond Amortization Schedule"
    )
    coupon_ids = fields.One2many(
        'efund.bond.coupon',
        'instrument_id',
        string="Bond Coupon Payment Schedule"
    )
    # 1. Montant d'émission
    issue_amount = fields.Monetary(
        string='Issue Amount',
        currency_field='currency_id',
        # required=True,
        tracking=True,
        help="Montant total émis par l'émetteur"
    )

    # 2. Valeur nominale
    face_value = fields.Monetary(
        string='Face Value (Nominal)',
        currency_field='currency_id',
        # required=True,
        default=100.0,
        tracking=True,
        help="Valeur nominale de chaque obligation (généralement 100)"
    )

    # 3. Taux d'intérêt
    coupon_rate = fields.Float(
        string='Coupon Rate (%)',
        digits=(16, 4),
        # required=True,
        tracking=True,
        help="Taux d'intérêt nominal annuel"
    )

    interest_rate_type = fields.Selection([
        ('fixed', 'Fixed'),
        ('floating', 'Floating'),
        ('variable', 'Variable'),
    ], string='Interest Rate Type', default='fixed'
        # , required=True
    )

    # 4. Périodicité
    coupon_frequency = fields.Selection([
        ('annual', 'Annuel'),
        ('semi_annual', 'Semestriel'),
        ('quarterly', 'Trimestriel'),
        ('monthly', 'Mensuel'),
        ('at_maturity', 'A Maturité'),
    ], string='Coupon Frequency', default='annual',
        # required=True
    )

    # 5. Dates clés
    issue_date = fields.Date(
        string='Date émission',
        # required=True,
        tracking=True,
        help="Date d'émission initiale"
    )

    value_date = fields.Date(
        string='Value Date (Date de Jouissance)',
        # required=True,
        tracking=True,
        help="Date à partir de laquelle les intérêts commencent à courir"
    )

    first_coupon_date = fields.Date(
        string='First Coupon Date',
        # required=True,
        tracking=True,
        compute='_compute_coupon_dates',
        store=True
    )

    maturity_date = fields.Date(
        string='Maturity Date',
        # required=True,
        tracking=True,
        help="Date de remboursement final"
    )

    # Calcul du prochain coupon
    coupon_calculation_date = fields.Date(
        string='Last Calculation Date',
        default=fields.Date.today,
        help="Date du dernier calcul des coupons"
    )
    next_coupon_date = fields.Date(
        string='Next Coupon Date',
        compute='_compute_coupon_schedule',
        store=True,
        help="Date du prochain paiement de coupon"
    )

    days_to_next_coupon = fields.Integer(
        string='Days to Next Coupon',
        compute='_compute_days_to_next_coupon',
        help="Nombre de jours jusqu'au prochain coupon",
        store=False
    )
    maturity_years = fields.Float(compute="_compute_maturity_years", store=True)

    accrued_interest = fields.Monetary(
        string='Accrued Interest',
        currency_field='currency_id',
        compute='_compute_accrued_interest'
    )

    # --- TCN ---
    tcn_maturity_date = fields.Date(string="Échéance TCN")
    tcn_rate = fields.Float(string="Taux du TCN (%)")

    # --- DROITS / OPTIONS / WARRANTS ---
    right_strike_price = fields.Float(string="Prix d’exercice")
    right_expiry_date = fields.Date(string="Date d’expiration")

    # ----------------------------------------------------
    # DONNÉES OPCVM INTERNES
    # ----------------------------------------------------
    is_active = fields.Boolean(default=True, string="Actif pour la valorisation")
    position_ids = fields.One2many('efund.fund.position', 'instrument_id', string="Positions détenues")

    # ----------------------------------------------------
    # ÉVÉNEMENTS
    # ----------------------------------------------------
    event_ids = fields.One2many(
        'efund.fund.instrument.event',
        'instrument_id',
        string="Événements",
        help="Événements sur cet instrument"
    )

    instrument_fee_ids = fields.One2many(
        'efund.fund.instrument.fee',
        'instrument_id',
        string="Frais",
        help="Frais sur cet instrument"
    )

    upcoming_event_count = fields.Integer(
        string="Événements à venir",
        compute='_compute_upcoming_event_count',
        store=False
    )

    recent_event_ids = fields.One2many(
        'efund.fund.instrument.event',
        'instrument_id',
        string="Événements récents",
        domain=[('event_date', '>=', fields.Date.today())]
    )



    def _compute_upcoming_event_count(self):
        for instrument in self:
            count = self.env['efund.fund.instrument.event'].search_count([
                ('instrument_id', '=', instrument.id),
                ('event_date', '>=', fields.Date.today()),
                ('state', 'in', ['draft', 'confirmed'])
            ])
            instrument.upcoming_event_count = count

    # Ajoutez aussi cette méthode dans les actions
    def action_view_events(self):
        """Affiche les événements de l'instrument"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Événements - {self.name}',
            'res_model': 'efund.fund.instrument.event',
            'view_mode': 'tree,form,calendar',
            'domain': [('instrument_id', '=', self.id)],
            'context': {'default_instrument_id': self.id},
        }

    def action_create_event(self):
        """Créer un nouvel événement pour cet instrument"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Créer un événement - {self.name}',
            'res_model': 'efund.fund.instrument.event',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_instrument_id': self.id,
                'default_currency_id': self.currency_id.id,
            },
        }

    # === MÉTHODES DE CALCUL ===
    # === MÉTHODE UNIFIÉE ===
    @api.depends('price_ids')
    def _compute_last_validated_price(self):
        for instrument in self:
            last_price = instrument.price_ids.filtered(
                lambda p: p.is_validated
            ).sorted('date', reverse=True)

            if last_price:
                instrument.last_validated_price = last_price[0].price
                instrument.last_price_date = last_price[0].date
            else:
                instrument.last_validated_price = 0.0
                instrument.last_price_date = False

    @api.depends('issue_date', 'maturity_date')
    def _compute_maturity_years(self):
        for rec in self:
            if rec.issue_date and rec.maturity_date:
                delta = rec.maturity_date - rec.issue_date
                rec.maturity_years = delta.days / 365
            else:
                rec.maturity_years = 0

    @api.depends('next_coupon_date')
    def _compute_days_to_next_coupon(self):
        today = date.today()
        for rec in self:
            if rec.next_coupon_date:
                rec.days_to_next_coupon = max(
                    (rec.next_coupon_date - today).days, 0
                )
            else:
                rec.days_to_next_coupon = 0

    @api.depends('first_coupon_date', 'coupon_frequency', 'coupon_calculation_date')
    def _compute_coupon_schedule(self):
        """Calcule toutes les informations de coupon en une passe"""
        today = fields.Date.today()

        for bond in self:
            # Réinitialisation
            bond.next_coupon_date = False

            # Vérification des prérequis
            if not bond.first_coupon_date:
                continue

            # Calcul de la prochaine date
            next_date = bond.first_coupon_date

            # Avancer jusqu'à dépasser la date actuelle
            while next_date <= today:
                next_date = bond._add_coupon_period(next_date)

            # Mise à jour des champs
            bond.next_coupon_date = next_date

            if next_date and next_date > today:
                bond.days_to_next_coupon = (next_date - today).days

    # === MÉTHODE POUR FORCER LE RECALCUL ===
    def recalculate_coupon_schedule(self):
        """Force le recalcul du calendrier des coupons"""
        self.write({'coupon_calculation_date': fields.Date.today()})
        self._compute_coupon_schedule()
        return True

    @api.depends('issue_date', 'coupon_frequency', 'value_date')
    def _compute_coupon_dates(self):
        # Calcule la date du premier coupon
        for bond in self:
            if bond.issue_date and bond.value_date and bond.coupon_frequency:
                # Le premier coupon est généralement à la première période après la date de valeur
                bond.first_coupon_date = bond._get_next_coupon_date(bond.value_date)
            else:
                bond.first_coupon_date = False

    """
    @api.depends('first_coupon_date', 'coupon_frequency')
    def _compute_next_coupon_date(self):
        #Calcule la date du prochain coupon
        today = fields.Date.today()
        for bond in self:
            if bond.first_coupon_date:
                next_date = bond.first_coupon_date
                while next_date <= today:
                    next_date = bond._add_coupon_period(next_date)
                bond.next_coupon_date = next_date
                bond.days_to_next_coupon = (next_date - today).days
            else:
                bond.next_coupon_date = False
                bond.days_to_next_coupon = 0
    """

    def _get_next_coupon_date(self, from_date):
        """Retourne la prochaine date de coupon après une date donnée"""
        self.ensure_one()

        if self.coupon_frequency == 'annual':
            return from_date + relativedelta(years=1)
        elif self.coupon_frequency == 'semi_annual':
            return from_date + relativedelta(months=6)
        elif self.coupon_frequency == 'quarterly':
            return from_date + relativedelta(months=3)
        elif self.coupon_frequency == 'monthly':
            return from_date + relativedelta(months=1)
        else:  # at_maturity
            return self.maturity_date

    def _add_coupon_period(self, date):
        """Ajoute une période de coupon à une date"""
        return self._get_next_coupon_date(date)

    @api.depends('coupon_rate', 'face_value', 'value_date')
    def _compute_accrued_interest(self):
        """Calcule les intérêts courus"""
        today = fields.Date.today()
        for bond in self:
            if bond.value_date and bond.value_date <= today:
                # Calcul simplifié : jours courus * taux journalier
                days_in_year = 360  # Convention Actual/360 souvent utilisée
                days_accrued = (today - bond.value_date).days

                daily_rate = bond.coupon_rate / 100 / days_in_year
                bond.accrued_interest = bond.face_value * daily_rate * days_accrued
            else:
                bond.accrued_interest = 0.0

    # ----------------------------------------------------
    # CONTRAINTES
    # ----------------------------------------------------
    @api.constrains('isin')
    def _check_isin_format(self):
        for record in self:
            if record.isin and len(record.isin) not in (12,):
                raise ValidationError(_("Le code ISIN doit contenir 12 caractères."))

    @api.constrains('coupon_rate', 'maturity_date')
    def _check_bond_fields(self):
        for record in self:
            if record.instrument_type == 'bond':
                if not record.maturity_date:
                    raise ValidationError(_("Une obligation doit avoir une date d'échéance."))
                if record.coupon_rate < 0:
                    raise ValidationError(_("Le coupon d’une obligation doit être positif."))

    @api.constrains('issuer_id')
    def _warn_missing_issuer(self):
        for rec in self:
            if rec.instrument_type != 'mmf' and not rec.issuer_id:
                raise ValidationError(_("L'émetteur est obligatoire pour cet instrument financier."))

    @api.constrains('issue_date', 'value_date', 'maturity_date')
    def _check_dates_consistency(self):
        """Valide la cohérence des dates"""
        for bond in self:
            if bond.value_date < bond.issue_date:
                raise ValidationError(_(
                    "Value date cannot be before issue date."
                ))

            if bond.maturity_date <= bond.value_date:
                raise ValidationError(_(
                    "Maturity date must be after value date."
                ))

    @api.constrains('coupon_rate')
    def _check_coupon_rate(self):
        """Valide le taux du coupon"""
        for bond in self:
            if bond.coupon_rate > 50.0:  # Limite raisonnable
                raise ValidationError(_(
                    "Coupon rate cannot exceed 50%."
                ))

    # === ACTIONS ===
    def action_view_coupon_schedule(self):
        """Affiche le calendrier des coupons"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Coupon Schedule - {self.name}',
            'res_model': 'efund.bond.coupon',
            'view_mode': 'list,form',
            'domain': [('instrument_id', '=', self.id)],
            'context': {'default_instrument_id': self.id},
        }

    def action_calculate_yield(self):
        """Calcule le yield (rendement) de l'obligation"""
        self.ensure_one()
        # Implémentation du calcul de yield
        return {
            'type': 'ir.actions.act_window',
            'name': f'Yield Calculation - {self.name}',
            'res_model': 'fund.bond.yield.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_instrument_id': self.id},
        }

    def action_generate_coupon_schedule(self):
        """Génère ou regénère le calendrier des coupons"""
        self.ensure_one()

        # Supprimer l'ancien calendrier si existant
        self.coupon_ids.unlink()
        _logger.info(f"****** je suis dans le coupon de calcul ")

        # Générer les nouvelles dates de coupon
        coupon_dates = self._generate_all_coupon_dates()

        _logger.info(f"****** affiche le calendrier des coupons: {coupon_dates} ")

        # Créer les enregistrements de coupon
        coupons = []
        for i, coupon_date in enumerate(coupon_dates, 1):
            coupon_vals = {
                'instrument_id': self.id,
                'coupon_number': i,
                'payment_date': coupon_date,
                'status': 'upcoming',
            }
            coupons.append(coupon_vals)

        # Créer en masse pour la performance
        _logger.info(f"****** affiche les coupons : {coupons} ")
        if coupons:
            self.env['efund.bond.coupon'].create(coupons)

        # Message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Coupon Schedule Generated'),
                'message': _('Successfully generated %s coupon payments.') % len(coupons),
                'type': 'success',
                'sticky': False,
            }
        }

    def action_view_coupon_schedule(self):
        """Affiche le calendrier des coupons"""
        self.ensure_one()
        _logger.info(f"************** je suis dans la procédure")

        # Générer automatiquement si vide
        if not self.coupon_ids:
            _logger.info(f"****** coupon_ids n'est pas vide : {self.coupon_ids}")
            self.action_generate_coupon_schedule()

        return {
            'type': 'ir.actions.act_window',
            'name': f'Coupon Schedule - {self.name}',
            'res_model': 'efund.bond.coupon',
            'view_mode': 'list,form',
            'domain': [('instrument_id', '=', self.id)],
            'context': {
                'default_instrument_id': self.id,
                'search_default_instrument_id': self.id,
            },
            'target': 'current',
        }

    def _generate_all_coupon_dates(self):
        """Génère toutes les dates de coupon jusqu'à maturité"""
        self.ensure_one()

        dates = []
        current_date = self.value_date

        while current_date < self.maturity_date:
            next_date = self._get_next_coupon_date(current_date)
            if next_date >= self.maturity_date:
                dates.append(self.maturity_date)
                break
            dates.append(next_date)
            current_date = next_date

        # S'assurer que la date de maturité est incluse
        if self.maturity_date not in dates:
            dates.append(self.maturity_date)

        return dates

    def action_update_coupon_status(self):
        """Met à jour le statut des coupons (automatique)"""
        self.ensure_one()

        today = fields.Date.today()
        for coupon in self.coupon_ids:
            if coupon.payment_date < today:
                coupon.status = 'paid'
            elif coupon.payment_date == today:
                coupon.status = 'accrued'
            else:
                coupon.status = 'upcoming'

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Coupon Status Updated'),
                'message': _('Coupon statuses have been updated to current date.'),
                'type': 'info',
                'sticky': False,
            }
        }

    # Appel wizard tableau d'amortissement
    def action_open_amortization_wizard(self):
        """Ouvre le wizard de génération du tableau d'amortissement"""
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': 'Générer le tableau d\'amortissement',
            'res_model': 'efund.bond.amortization.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'active_id': self.id,
                'active_ids': [self.id],
                'default_instrument_id': self.id,
                'default_currency_id': self.currency_id.id,
                'default_nominal_amount': self.face_value or 0,
                'default_coupon_rate': self.coupon_rate or 0,
                'default_maturity_years': self.maturity_years or 0,
                'default_frequency': self.coupon_frequency or 'annual',
                'default_start_date': self.issue_date or False,
            },
        }

    def action_import_price_today(self):
        """Importer le cours du jour pour cet instrument"""
        self.ensure_one()

        if not self.import_config_id:
            raise UserError(_("Aucune configuration d'import définie pour cet instrument"))

        # Utiliser la configuration pour importer
        return self.import_config_id.action_import_prices()

    def action_open_import_wizard(self):
        """Ouvrir le wizard d'import"""
        self.ensure_one()

        return {
            'name': _('Importer des cours'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.fund.import.price.simple.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_instrument_id': self.id,
            }
        }

    def action_import_price_today(self):
        """Importer le cours du jour pour cet instrument"""
        self.ensure_one()

        # Créer un wizard d'import simple pour cet instrument
        return {
            'name': _('Importer le cours'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.fund.import.price.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_instrument_id': self.id,
                'default_price_date': fields.Date.today(),
            }
        }

    def action_open_price_import_wizard(self):
        """Ouvrir le wizard d'import pour plusieurs instruments"""
        return {
            'name': _('Importer des cours'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.fund.import.price.wizard',
            'view_mode': 'form',
            'target': 'new',
        }

    def action_archived(self):
        for order in self:
            if order.state != 'approved':
                continue
            order.state = 'archived'

    def action_check(self):
        for order in self:
            if order.state != 'draft':
                continue
            order.state = 'pending'

    def action_approve(self):
        for order in self:
            if order.state != 'pending':
                continue
            order.state = 'approved'

