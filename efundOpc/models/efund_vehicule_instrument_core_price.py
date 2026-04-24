# efund_vehicule_instrument_core_price.py
import calendar
import datetime
import logging
from math import ceil

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


def compute_linear_actuariat_value_at_date(valuation_date, buyed_price, buyed_date, nominal_price, maturity_date):
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

        #actuarial_value = buyed_price * ((1 + yield_rate) ** (days_elapsed / base))

        return linear_value #{'linear_value': linear_value,'actuarial_value': actuarial_value }


class FundInstrumentPrice(models.Model):
    _name = "efund.vehicule.instrument.core.price"
    _description = "Cours d'un instrument financier"
    _order = "date desc, instrument_id"
    _rec_name = "display_name"

    instrument_id = fields.Many2one('efund.vehicule.instrument.core', string="Instrument", required=True, index=True)
    vehicule_id = fields.Many2one('efund.vehicule', string="Véhicule",  index=True)
    date = fields.Date(string="Date du cours", required=True, default=fields.Date.today, index=True)
    price = fields.Float(string="Cours", digits=(16, 4), required=True)
    interest = fields.Float(string="Intérêt", digits=(16, 4), )
    currency_id = fields.Many2one(related="instrument_id.currency_id", string="Devise du cours")
    is_validated = fields.Boolean(string="Validé", default=False)
    validated_date = fields.Date(string="Date de validation")
    validated_by = fields.Many2one('res.users', string="Validé par")

    # Champs calculés
    display_name = fields.Char(string="Nom", compute='_compute_display_name', store=True)
    # Nouveaux champs pour l'auditabilité
    price_type = fields.Selection([('close', 'Clôture'), ('bid', 'Achat (Bid)'), ('ask', 'Vente (Ask)'), ('mid', 'Moyen (Mid)')],string="Type de cours", default='close',)
    source = fields.Selection([('brvm', 'BRVM'), ('internal', 'Estimation Interne'), ('third_party', 'Tiers (SGI/Banque)')],default='internal', string="Source du cours",)
    comment = fields.Text(string="Notes sur la valorisation")

    @api.model
    def cron_generate_daily_prices(self):
        """ Méthode appelée par l'action planifiée pour automatiser les cours """
        today = fields.Date.today()
        position = self.env['efund.vehicule.portfolio'].search([])

        for pos in position:
            # --- CAS 1 : LES DAT (Calcul par intérêts courus) ---
            if pos.instrument_id.instrument_type == 'dat':
                self.env["efund.service"].generate_dat_tcn_price(pos, today)
                #self._generate_dat_price(pos, today)

            elif pos.instrument_id.instrument_type == 'tcn':
                today = datetime.date.today()
                accrual = self.env['efund.service'].generate_tcn_price_new(pos, today)
                # get_tcn_interest(pos.rate, pos.value_date,pos.quantity * pos.first_price,360))
                self._update_or_create_price(pos.instrument_id,pos.vehicule_id,today,pos.first_price,accrual,'internal')


            # --- CAS 2 : LES BONDS LISTÉS (Mise à jour automatique) ---
            elif pos.instrument_id.instrument_type == 'bond': #and pos.instrument_id.valuation_method == 'listed':
                trans_details = self.env['efund.investment.transaction'].search([
                    ('instrument_id', '=', pos.instrument_id.id),
                    ('vehicule_id', '=', pos.vehicule_id.id)], limit=1)

                bond = self.env['efund.vehicule.instrument.core.bond'].search([ ('instrument_id', '=', pos.instrument_id.id),], limit=1)
                if trans_details:
                    self._generate_listed_bond_price(trans_details,bond,pos, today)

    def _generate_dat_price(self, position, target_date):
        """ Calcule le cours du DAT : Valeur nominale + intérêts linéarisés """
        # On récupère les détails du DAT (taux, date début)

        dat = self.env['efund.vehicule.instrument.core.dat'].search([('instrument_id', '=', position.instrument_id.id), ],
                                                                      limit=1)

        if target_date < position.value_date:
            raise ValidationError(f"La date de calcul {target_date} est antérieure à la date de début du DAT{position.value_date}")
        if target_date > position.maturity_date:
            raise ValidationError(f"La date de calcul {target_date} est postérieure à la date de maturité du DAT{position.maturity_date}")

        if dat.interest_type =='prepaid':
            interest_value = 0 #self.env["efund.service"].get_dat_precompte_interest(position.bond_dat_interest, position.rate, target_date, position.maturity_date, target_date)

        else:
            if position and position.value_date and position.rate:
                days = (target_date - position.value_date).days
                if days < 0: days = 0

                # Calcul du facteur de prix (Base 1)
                # Formule UMOA classique : 1 + (Taux * Jours / 360)
                computed_factor = (position.rate / 100.0 * days / 365)
                #price_value = computed_factor * position.last_price
                interest_value = computed_factor * position.last_price

            self._update_or_create_price(position.instrument_id,position.vehicule_id, target_date, position.last_price, interest_value,'internal')

    def _generate_listed_bond_price(self,trans_details, bond,pos, target_date):
        """ Pour les bonds listés, si pas de prix aujourd'hui, on reprend le dernier connu """
        # On vérifie si un prix existe déjà pour aujourd'hui

        # faire un condition sur la source

        existing = self.search([
            ('instrument_id', '=', bond.instrument_id.id),
            ('vehicule_id', '=', trans_details.vehicule_id.id),
            ('date', '=', target_date)
        ], limit=1)


        last_price = 0
        if not existing:
            # Instrument coté
            if bond.instrument_id.is_listed:
                # Le cours de l'instrument est listé
                if bond.instrument_id.valuation_method == 'listed':
                    position = self.env['efund.vehicule.portfolio'].search([ ('instrument_id', '=', bond.instrument_id.id),])
                    if position:
                        for pos in position:
                           last_price = compute_linear_actuariat_value_at_date(target_date, pos.first_price, pos.first_price_date, bond.face_value,bond.maturity_date)

                # Si le cours n'est pas listé alors il est fourni par le marché

            # l'instrument n'est pas coté alors on reprend le prix d'achat
            else:
                # On cherche le dernier prix validé
                last_price_obj = self.search([
                    ('instrument_id', '=', trans_details.instrument_id.id),
                    ('vehicule_id', '=', trans_details.vehicule_id.id),
                    ('is_validated', '=', True),
                    ('date', '<', target_date)
                ], order='date desc', limit=1)
                if last_price_obj:
                    last_price = last_price_obj.price
                else:
                    last_price = pos.face_value if pos.face_value else bond.face_value



        if last_price:

            res = self.env["efund.service"].compute_accrued_interest_precise(bond.face_value, bond.rate_net, target_date, bond.maturity_date,
                                             bond.coupon_frequency, tax_rate=0.0, add_day=0)

            interest = res.get('interest_net') * pos.quantity
            self._update_or_create_price(trans_details.instrument_id,trans_details.vehicule_id, target_date, last_price,interest, 'internal')

    def _update_or_create_price(self, instrument,vehicule, date, val,interest, source):
        """ Utilitaire pour créer ou mettre à jour un cours """
        price_rec = self.search([
            ('instrument_id', '=', instrument.id),
            ('vehicule_id','=', vehicule.id),
            ('date', '=', date)
        ], limit=1)

        vals = {
            'instrument_id': instrument.id,
            'vehicule_id': vehicule.id,
            'date': date,
            'price': val,
            'interest': ceil(interest),
            'source': source,
            'is_validated': True,
            'price_type': 'close'
        }

        if price_rec:
            price_rec.write(vals)
        else:
            self.create(vals)

    @api.depends('instrument_id', 'date', 'price')
    def _compute_display_name(self):
        for rec in self:
            rec.display_name = f"{rec.instrument_id.name} - {rec.date} - {rec.price:.4f}"

    def action_validate(self):
        """Valider un cours et mettre à jour les positions"""
        for price in self:
            if not price.is_validated:
                price.is_validated = True
                price.validated_date = fields.Date.today()
                price.validated_by = self.env.user

                # Mettre à jour les positions des fonds
                #self._update_fund_positions(price)

    def _update_fund_positions(self, price):
        """Mettre à jour le market_value des positions basé sur le nouveau cours"""
        # Récupérer toutes les positions pour cet instrument
        positions = self.env['efund.vehicule.portfolio'].search([
            ('instrument_id', '=', price.instrument_id.id),
        ])

        # Mettre à jour le dernier cours dans l'instrument
        price.instrument_id.write({
            'last_validated_price': price.price,
            'last_price_date': price.date,
        })

        # Recalculer la valeur de marché pour toutes les positions
        for position in positions:
            position.compute_market_value()

    def action_validate_batch(self):
        """Valider plusieurs cours en une fois"""
        unvalidated = self.filtered(lambda p: not p.is_validated)
        for price in unvalidated:
            price.action_validate()

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Validation terminée'),
                'message': _('%s cours ont été validés.') % len(unvalidated),
                'type': 'success',
                'sticky': False,
            }
        }

