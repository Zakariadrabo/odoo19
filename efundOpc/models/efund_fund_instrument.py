import calendar
import logging
from datetime import date, timedelta

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

    instrument_type = fields.Selection([('equity', 'Action'),
                                        ('bond', 'Obligation / Créance'),
                                        ('money_market', 'Marché monétaire'),
                                        ('opcvm', 'Part OPCVM'),
                                        ('dat', 'DAT'),
                                        ], default='equity', required=True, string="Type d’instrument")

    currency_id = fields.Many2one('res.currency', string="Devise")
    state = fields.Selection(
        [('draft', 'Brouillon'), ('pending', 'Vérification'), ('approved', 'Approuvé'), ('archived', 'Archivé')],
        default='draft')
    is_listed = fields.Boolean(string='Est Coté', default=False, tracking=True, help="Indique si l'instrument est coté")
    listing_date = fields.Date(string='Date 1ère Cotation', tracking=True, help="Indique la date de la 1ère cotation")
    last_validated_price = fields.Float(compute='_compute_last_validated_price', string="Dernier cours validé",
                                        digits=(16, 4))
    last_price_date = fields.Date(compute='_compute_last_validated_price', string="Date dernier cours")
    sector = fields.Selection([('agriculture', 'Agriculture'), ('industrie', 'Industrie'), ],
                              string="Secteur d'activités")
    state_issuer = fields.Boolean(string="Émis ou garanti par un État CEMAC")
    issuer_id = fields.Many2one("efund.instrument.issuer", string="Émetteur",
                                help="Institution ou entreprise qui émet l'instrument financier.")
    market = fields.Selection([('brvm', 'BRVM'), ('bvmac', 'BVMAC'), ('other', 'Autre marché'), ],
                              string="Marché Principal", default='bvmac')

    # DAT
    # --- DAT ---
    dat_principal = fields.Monetary(string="Montant du DAT", )
    dat_interest_rate = fields.Float(string="Taux DAT (%)", digits=(16, 4))
    dat_start_date = fields.Date(string="Date de début DAT")
    dat_maturity_date = fields.Date(string="Date d’échéance DAT")
    dat_day_count = fields.Selection([('act360', 'ACT/360'), ('act365', 'ACT/365'), ], default='act360')
    dat_amortized_value = fields.Monetary(string="Valeur amortie DAT", compute='_compute_dat_amortized_value')

    # --------------------------------------------------------
    #  RELATIONS
    # --------------------------------------------------------
    price_ids = fields.One2many('efund.fund.instrument.price', 'instrument_id', string="Prix")
    custodian = fields.Selection([('dcbr', 'DC/BR'), ('bceao', 'BCEAO'), ('autre', 'Autre'), ], default='dcbr',
                                 string="Dépositaire", )
    asset_class_id = fields.Many2one('efund.asset.class', string="Classe d'actif",
                                     domain="[('state', '=', 'validated')]", required=True)
    market_price_source = fields.Selection(
        [('brvm_api', 'BRVM – API officielle'), ('manual', 'Saisie manuelle'), ('datasource', 'Autre data provider'), ],
        string="Source du Prix")
    import_config_id = fields.Many2one('efund.fund.instrument.price.import', string="Configuration d'import")
    custodian_id = fields.Many2one('efund.depositaire', string="Dépositaire")

    # ----------------------------------------------------
    # CARACTÉRISTIQUES SPÉCIFIQUES PAR TYPE
    # ----------------------------------------------------
    # --- ACTIONS ---
    equity_dividend_yield = fields.Float(string="Dividende")

    # --- OBLIGATIONS ---
    bond_type = fields.Selection(
        [('ota', 'OTA (Obligations du Trésor Assimilables)'), ('bta', 'BTA (Bons du Trésor Assimilables)'),
         ('op', 'Obligation Privée')
         ], string='Type Obligation', default='ota')
    bond_issuer_rating = fields.Selection([('aaa', 'AAA'), ('aa', 'AA'), ('a', 'A'), ('bbb', 'BBB'), ('bb', 'BB'),
                                           ('b', 'B'), ('ccc', 'CCC'), ('cc', 'CC'), ('c', 'C'),
                                           ('d', 'D (Default)'), ], string='Notation', tracking=True)
    rating_agency = fields.Char(string='Agence Notation')
    bond_amortization_ids = fields.One2many('efund.bond.amortization', 'instrument_id',
                                            string="calendrier des amortissements")
    coupon_ids = fields.One2many('efund.bond.coupon', 'instrument_id', string="Calendrier des coupons")
    issue_amount = fields.Monetary(string='Montant Emission', currency_field='currency_id', tracking=True,
                                   help="Montant total émis par l'émetteur")
    face_value = fields.Monetary(string='Valeur nominale', currency_field='currency_id', tracking=True,
                                 help="Valeur nominale de chaque obligation (généralement 100)", default=100.0)
    coupon_rate = fields.Float(string='Taux du Coupon (%)', digits=(16, 4), tracking=True,
                               help="Taux d'intérêt nominal annuel")
    coupon_frequency = fields.Selection(
        [('annual', 'Annuel'), ('semi_annual', 'Semestriel'), ('quarterly', 'Trimestriel'),
         ('monthly', 'Mensuel'), ('at_maturity', 'A Maturité'), ], string='Fréquence des Coupons', default='annual', )
    issue_date = fields.Date(string='Date émission', tracking=True, help="Date d'émission initiale")
    value_date = fields.Date(string='Date de Jouissance', tracking=True,
                             help="Date à partir de laquelle les intérêts commencent à courir")
    first_coupon_date = fields.Date(string='Date 1er Coupon', tracking=True, compute='_compute_coupon_dates',
                                    store=True)
    maturity_date = fields.Date(string='Date de Maturité', tracking=True, help="Date de remboursement final")
    coupon_calculation_date = fields.Date(string='Date dernier calcul des coupons', default=fields.Date.today,
                                          help="Date du dernier calcul des coupons")
    next_coupon_date = fields.Date(string='Date prochain Coupon', compute='_compute_coupon_schedule', store=True,
                                   help="Date du prochain paiement de coupon")
    days_to_next_coupon = fields.Integer(string='Jours jusqu\'au prochain Coupon',
                                         compute='_compute_days_to_next_coupon',
                                         help="Nombre de jours jusqu'au prochain coupon", store=True)
    days_to_next_coupon_string = fields.Char(string='Date prochain Coupon', compute='_compute_days_to_next_coupon',
                                     help="Nombre de jours jusqu'au prochain coupon", store=True)
    remaining_date = fields.Char(string='Jours restants', compute='_compute_days_to_next_coupon', store=True)
    maturity_years = fields.Float(compute="_compute_maturity_years", store=True)
    accrued_interest = fields.Monetary(string='Intérêts courus', currency_field='currency_id',
                                       compute='_compute_accrued_interest')
    # amortization_type = fields.Selection([('infine', 'in fine'), ('annuite', 'Annuités constantes')], string='Remboursement', default='infine', )
    technical_trick = fields.Selection([('exact365', 'Exact/Exact'), ('exact360', 'Exact/Exact'), ],
                                       string='Base de calcul')
    amortization_type = fields.Selection([('in_fine', "In Fine (Bullet)"), ('constant_annuity', "Annuités Constantes"),
                                          ('constant_principal', "Amortissement Constant"),
                                          ('american', "Américain (Balloon)"),
                                          ('custom_schedule', "Échéancier Personnalisé"),
                                          ], string="Type d'Amortissement", default="in_fine")
    grace_period = fields.Integer(string="Période de grâce (années)", default=0)
    balloon_percentage = fields.Float(string="Pourcentage Balloon", default=100.0)

    valuation_method = fields.Selection(
        [('actuarial', 'Actuarielle (Taux effectif)'), ('linear', 'Linéaire (Accrétion simple)'),
         ], default='actuarial', string="Méthode de valorisation")
    linear_daily_accretion = fields.Monetary(string="Accrétion journalière", compute='_compute_linear_daily_accretion',
                                             store=True)
    purchase_price = fields.Monetary(string="Prix à Emission", help="Prix réellement payé pour l'obligation")
    yield_rate = fields.Float(string="Rendement actuariel (%)", store=True, digits=(16, 8))
    amortized_value = fields.Monetary(string="Valeur amortie (actuarielle)", compute='_compute_amortized_value',
                                      store=False)
    linear_amortized_value = fields.Monetary(string="Valeur amortie (linéaire)",
                                             compute='_compute_linear_amortized_value', store=False)
    effective_value = fields.Monetary(string="Valeur retenue", compute='_compute_effective_value', store=False)


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
    event_ids = fields.One2many('efund.fund.instrument.event', 'instrument_id', string="Événements",
                                help="Événements sur cet instrument")
    instrument_fee_ids = fields.One2many('efund.fund.instrument.fee.rule', 'instrument_id', string="Frais",
                                         help="Frais sur cet instrument")
    upcoming_event_count = fields.Integer(string="Événements à venir", compute='_compute_upcoming_event_count',
                                          store=False)
    recent_event_ids = fields.One2many('efund.fund.instrument.event', 'instrument_id', string="Événements récents",
                                       domain=[('event_date', '>=', fields.Date.today())])

    #----------------------------------------------------
    # Données de la simulation
    #----------------------------------------------------
    valuation_date = fields.Date(string="Date de valorisation",required=True,default=fields.Date.today)
    actuarial_value = fields.Monetary(string="Valeur actuarielle",)
    linear_value = fields.Monetary(string="Valeur linéaire",)


    def simulate(self):
        for rec in self:
            #valuation_date, buyed_price, buyed_date, nominal_price,maturity_date)
            result = rec.compute_linear_actuariat_value_at_date(rec.valuation_date,rec.purchase_price,rec.value_date,rec.face_value,rec.maturity_date)
            rec.linear_value = result.get("linear_value")
            rec.actuarial_value = result.get("actuarial_value")



    # =================================================
    # CALCUL DU TIR (MÉTHODE ACTUARIELLE)
    # =================================================
    @api.depends('purchase_price', 'face_value', 'value_date', 'maturity_date')
    def _compute_yield_rate(self):
        for rec in self:
            if (
                    rec.instrument_type != 'bond' or not rec.purchase_price or not rec.face_value or not rec.value_date or not rec.maturity_date or rec.purchase_price <= 0):
                rec.yield_rate = 0.0
                continue

            total_days = (rec.maturity_date - rec.value_date).days
            if total_days <= 0:
                rec.yield_rate = 0.0
                continue

            try:
                rec.yield_rate = (
                                         (rec.face_value / rec.purchase_price)
                                         ** (365 / total_days) - 1
                                 ) * 100
            except Exception:
                rec.yield_rate = 0.0

    # =================================================
    # VALEUR ACTUARIELLE QUOTIDIENNE
    # =================================================
    @api.depends(
        'purchase_price',
        'yield_rate',
        'value_date',
        'maturity_date',
        'instrument_type'
    )
    def _compute_amortized_value(self):
        today = fields.Date.context_today(self)

        for rec in self:
            if rec.instrument_type != 'bond':
                rec.amortized_value = 0.0
                continue

            if not rec.purchase_price or not rec.value_date:
                rec.amortized_value = 0.0
                continue

            if today <= rec.value_date:
                rec.amortized_value = rec.purchase_price
                continue

            if rec.maturity_date and today >= rec.maturity_date:
                rec.amortized_value = rec.face_value
                continue

            days_elapsed = (today - rec.value_date).days
            r = rec.yield_rate / 100
            base = 365  # ACT/365 (Trésor)

            rec.amortized_value = rec.purchase_price * (
                    (1 + r) ** (days_elapsed / base)
            )

    # =================================================
    # ACCRÉTION LINÉAIRE JOURNALIÈRE
    # =================================================
    @api.depends('purchase_price', 'face_value', 'value_date', 'maturity_date')
    def _compute_linear_daily_accretion(self):
        for rec in self:
            if (
                    rec.instrument_type != 'bond'
                    or not rec.purchase_price
                    or not rec.face_value
                    or not rec.value_date
                    or not rec.maturity_date
            ):
                rec.linear_daily_accretion = 0.0
                continue

            total_days = (rec.maturity_date - rec.value_date).days
            if total_days <= 0:
                rec.linear_daily_accretion = 0.0
                continue

            rec.linear_daily_accretion = (
                                                 rec.face_value - rec.purchase_price
                                         ) / total_days

    # =================================================
    # VALEUR LINÉAIRE QUOTIDIENNE
    # =================================================
    @api.depends(
        'linear_daily_accretion',
        'purchase_price',
        'value_date',
        'maturity_date'
    )
    def _compute_linear_amortized_value(self):
        today = fields.Date.context_today(self)

        for rec in self:
            if rec.instrument_type != 'bond':
                rec.linear_amortized_value = 0.0
                continue

            if not rec.purchase_price or not rec.value_date:
                rec.linear_amortized_value = 0.0
                continue

            if today <= rec.value_date:
                rec.linear_amortized_value = rec.purchase_price
                continue

            if today >= rec.maturity_date:
                rec.linear_amortized_value = rec.face_value
                continue

            days_elapsed = (today - rec.value_date).days

            rec.linear_amortized_value = (
                    rec.purchase_price
                    + rec.linear_daily_accretion * days_elapsed
            )

    # =================================================
    # VALEUR FINALE À UTILISER
    # =================================================
    @api.depends(
        'valuation_method',
        'amortized_value',
        'linear_amortized_value'
    )
    def _compute_effective_value(self):
        for rec in self:
            if rec.valuation_method == 'linear':
                rec.effective_value = rec.linear_amortized_value
            else:
                rec.effective_value = rec.amortized_value

    # =================================================
    # CONTRÔLE & TRAÇABILITÉ
    # =================================================
    @api.constrains('instrument_type', 'valuation_method')
    def _warn_linear_valuation(self):
        for rec in self:
            if (
                    rec.instrument_type == 'bond'
                    and rec.valuation_method == 'linear'
            ):
                # Warning volontairement non bloquant
                rec.message_post(
                    body=_(
                        "⚠️ La méthode linéaire est une approximation. "
                        "La méthode actuarielle est recommandée pour la VL officielle."
                    )
                )

    @api.depends('instrument_type', 'dat_principal',
                 'dat_interest_rate', 'dat_start_date')
    def _compute_dat_amortized_value(self):
        today = fields.Date.today()
        for rec in self:
            if rec.instrument_type != 'dat':
                rec.dat_amortized_value = 0.0
                continue

            if not rec.dat_start_date or today < rec.dat_start_date:
                rec.dat_amortized_value = rec.dat_principal or 0.0
                continue

            days = (today - rec.dat_start_date).days
            base = 360 if rec.dat_day_count == 'act360' else 365
            r = rec.dat_interest_rate / 100

            rec.dat_amortized_value = rec.dat_principal * (1 + r * days / base)

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

    def date_diff_ymd(self, start_date, end_date):
        """
        Calcule la différence calendaire exacte entre deux dates
        en années, mois et jours (bissextile inclus).
        """

        if end_date < start_date:
            raise ValueError("end_date doit être postérieure à start_date")

        years = end_date.year - start_date.year
        months = end_date.month - start_date.month
        days = end_date.day - start_date.day

        # Ajustement des jours négatifs
        if days < 0:
            months -= 1
            # dernier jour du mois précédent end_date
            last_day_prev_month = (end_date.replace(day=1) - timedelta(days=1)).day
            days += last_day_prev_month

        # Ajustement des mois négatifs
        if months < 0:
            years -= 1
            months += 12

        return {
            'years': years,
            'months': months,
            'days': days,
        }


    @api.depends('next_coupon_date')
    def _compute_days_to_next_coupon(self):
        today = date.today()
        for rec in self:
            if rec.next_coupon_date:
                rec.days_to_next_coupon = max((rec.next_coupon_date - today).days, 0)

                result = rec.date_diff_ymd(today,rec.next_coupon_date)
                result1 = rec.date_diff_ymd(today, rec.maturity_date)

                rec.days_to_next_coupon_string = f"{result.get('years')} ans {result.get('months')} mois {result.get('days')} jours"
                rec.remaining_date = f"{result1.get('years')} ans {result1.get('months')} mois {result1.get('days')} jours"
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
    """
    @api.constrains('isin')
    def _check_isin_format(self):
        for record in self:
            if record.isin and len(record.isin) not in (12,):
                raise ValidationError(_("Le code ISIN doit contenir 12 caractères."))
    """

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

        # Générer les nouvelles dates de coupon
        coupon_dates = self._generate_all_coupon_dates()

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

    #"""""""""""""""""""""""""""""""""""""""""""""""""""""
    # Valorisation du cours des obligations
    #"""""""""""""""""""""""""""""""""""""""""""""""""""""

    #Méthode Actuariale
    def compute_actuarial_value_at_date(self, valuation_date):
        self.ensure_one()

        if (
                self.instrument_type != 'bond'
                or not self.purchase_price
                or not self.value_date
                or not self.maturity_date
        ):
            return 0.0

        if valuation_date <= self.value_date:
            return self.purchase_price

        if valuation_date >= self.maturity_date:
            return self.face_value

        days_elapsed = (self.maturity_date - self.value_date).days
        nbjour_depuis_achat = (valuation_date - self.value_date).days
        yield_rate =  ((self.face_value / self.purchase_price)** (365 / days_elapsed) - 1)

        base = 366 if calendar.isleap(valuation_date.year) else 365  # ACT/365

        return self.purchase_price * ((1 + yield_rate) ** (nbjour_depuis_achat / base))

    # Méthode Linéaire
    # Générique Méthode
    def compute_linear_actuariat_value_at_date(self, valuation_date, buyed_price, buyed_date, nominal_price,maturity_date):
        self.ensure_one()
        if not valuation_date or not buyed_price or not nominal_price or not maturity_date:
            raise UserError(_("Veuillez renseigner tous les champs obligatoires."))
        else:
            if valuation_date <= buyed_date:
                return buyed_price

            if valuation_date >= maturity_date:
                return nominal_price

            total_days = (maturity_date - buyed_date).days
            if total_days <= 0:
                return buyed_price

            # Linéaire
            daily_accretion = (nominal_price - buyed_price) / total_days
            days_elapsed = (valuation_date - buyed_date).days

            linear_value = buyed_price + daily_accretion * days_elapsed

            # Actuariat
            yield_rate = ((nominal_price / buyed_price) ** (365 / total_days) - 1)
            base = 366 if calendar.isleap(valuation_date.year) else 365

            actuarial_value = buyed_price * ((1 + yield_rate) ** (days_elapsed / base))

            return {
                'linear_value': linear_value,
                'actuarial_value': actuarial_value
            }


    def compute_linear_value_at_date(self, valuation_date):
        self.ensure_one()

        if (
                self.instrument_type != 'bond'
                or not self.purchase_price
                or not self.value_date
                or not self.maturity_date
        ):
            return 0.0

        if valuation_date <= self.value_date:
            return self.purchase_price

        if valuation_date >= self.maturity_date:
            return self.face_value

        total_days = (self.maturity_date - self.value_date).days
        if total_days <= 0:
            return self.purchase_price

        daily_accretion = (
                                  self.face_value - self.purchase_price
                          ) / total_days

        days_elapsed = (valuation_date - self.value_date).days

        return self.purchase_price + daily_accretion * days_elapsed

    # Valeur par rapport à une date
    def compute_effective_value_at_date(self, valuation_date):
        self.ensure_one()

        if self.valuation_method == 'linear':
            return self.compute_linear_value_at_date(valuation_date)

        return self.compute_actuarial_value_at_date(valuation_date)


