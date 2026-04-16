import calendar
import datetime
import logging
from math import ceil

from dateutil.relativedelta import relativedelta

_logger = logging.getLogger(__name__)

from odoo import models, _
from odoo.exceptions import UserError, ValidationError


class EfundService(models.Model):
    _name = 'efund.service'
    _description = 'Service for Efund'

    # récupération de la dernière VL
    # Dans votre modèle efund.service

    def get_account_root(self, instrument_type):
        """ Définit la racine SYSCOHADA selon le type d'instrument """
        mapping = {
            'bond': '211',
            'tcn': '212',
            'equity': '213',
            'opcvm': '214',
            'dat': '215',

        }
        return mapping.get(instrument_type, '218')

    def get_or_create_accounting_mapping(self, instrument, vehicule):
        """
        Retourne le compte comptable associé.
        Le crée s'il n'existe pas encore pour cette société.
        """

        # Le véhicule définit la société (le fonds a sa propre company,
        # les mandats partagent la company de gestion)
        # 1. Récupérer la compagnie 'MANDATS'

        if vehicule.company_id:
            company = vehicule.company_id
        else:
            company = self.env['res.company'].search([('company_code', '=', 'MANDATS')], limit=1)

        mapping_obj = self.env['efund.instrument.account']
        mapping = mapping_obj.search([
            ('instrument_id', '=', instrument.id),
            ('company_id', '=', company.id)
        ], limit=1)

        if not mapping:
            # Appel de la création chronologique
            new_account = self.create_chronological_account(company, instrument)
            mapping = mapping_obj.create({
                'instrument_id': instrument.id,
                'company_id': company.id,
                'account_id': new_account.id
            })

        return mapping.account_id

    def create_chronological_account(self, company, instrument):
        """
        Génère un compte comptable chronologique compatible Odoo 19+.
        Format : Racine + Séquence 5 chiffres (ex: 21100001).
        """

        target_company = self.env['res.company'].browse(company.id)
        AccountObj = self.env['account.account'].sudo().with_company(target_company)
        root = self.get_account_root(instrument.instrument_type)
        company_id = str(company.id)

        last_account = AccountObj.search([
            ('code', '=like', f"{root}%")
        ], order='code desc', limit=1)

        if last_account:
            last_code = last_account.code
            _logger.info(f"Dernier code trouvé : {last_code}")

            # 3. Logique d'incrémentation
            # On tente de transformer le code en entier pour ajouter 1
            try:
                # On transforme en int, on ajoute 1, puis on repasse en string
                new_code_int = int(last_code) + 1
                new_code = str(new_code_int)
            except ValueError:
                # Sécurité au cas où le code contient des lettres (ex: 211000A)
                raise UserError(
                    _("Le format du compte %s n'est pas purement numérique et ne peut pas être incrémenté automatiquement.") % last_code)
        else:
            # 4. Premier compte de la série (si aucun n'existe)
            # On définit un format standard, par exemple Racine + 5 chiffres
            new_code = f"{root}001"
            _logger.info(f"Création du premier compte de la série : {new_code}")

        # 5. Création effective du compte
        return AccountObj.create({
            'name': f"Titres {instrument.name}",
            'code': new_code,
            'account_type': 'asset_fixed',
            'code_store': f'"{company_id}": "{new_code}"',
        })

        # 4. Création du compte
        # Utiliser with_company(company) est crucial pour que Odoo
        # injecte le code dans la bonne clé du dictionnaire JSON 'code_store'
        return AccountObj.create({
            'name': f"Titres {self.name}",
            'code': new_code,
            'account_type': 'asset_fixed',
            'code_store': f'"{company_id}": "{new_code}"',
        })

    def get_tcn_interest(self, rate, start_date, amount, base):
        today = datetime.date.today()
        duration = (today - start_date).days
        return amount * rate * duration / (base * 100)

    def get_last_nav_value(self, fund_id, date_limit=None):
        """
        Récupère la dernière VL validée pour un fonds donné.
        :param fund_id: ID ou recordset du fonds
        :param date_limit: Optionnel, date maximum à ne pas dépasser (ex: VL à une date T)
        :return: float (VL Unitaire) ou 0.0
        """
        if not fund_id:
            return 0.0

        # Conversion de l'ID en entier si c'est un recordset
        f_id = fund_id.id if hasattr(fund_id, 'id') else fund_id

        domain = [
            ('fund_id', '=', f_id),
            ('state', '=', 'validated')  # On ne prend que les VL officielles
        ]

        # Si on cherche la VL précédant une date spécifique
        if date_limit:
            domain.append(('valuation_date', '<', date_limit))

        # Recherche de la VL la plus récente
        last_nav = self.env['efund.nav.session'].search(
            domain,
            limit=1,
            order='valuation_date desc'
        )

        return last_nav.unit_nav if last_nav else 0.0

    # Obtenir le dernier coupon
    def get_coupon_period(self, order_date, maturity_date, frequency=1):
        """
        Calcule les dates de coupon entourant la commande.
        :param frequency: Nombre de coupons par an (1=Annuel, 2=Semestriel, 4=Trimestriel)
        """
        if not order_date or not maturity_date:
            return False
        # Si on est après ou pile à la maturité
        if order_date >= maturity_date:
            return {
                'last_coupon': maturity_date,
                'next_coupon': maturity_date,
                'days_accrued': 0,
                'days_in_period': 0
            }

        # Déterminer le pas de recul en mois selon la fréquence
        # Annuel = 12 mois, Semestriel = 6 mois, Trimestriel = 3 mois
        months_step = 12 // frequency

        # On part de la maturité (le dernier coupon possible)
        next_coupon = maturity_date
        last_coupon = next_coupon - relativedelta(months=months_step)

        # 3. On recule par saut de fréquence
        # On cherche l'intervalle tel que : last_coupon <= order_date < next_coupon
        while last_coupon > order_date:
            next_coupon = last_coupon
            last_coupon = next_coupon - relativedelta(months=months_step)

        # 4. Calcul final
        # Si order_date == last_coupon, days_accrued sera exactement 0
        days_accrued = (order_date - last_coupon).days
        days_in_period = (next_coupon - last_coupon).days

        return {
            'last_coupon': last_coupon,
            'next_coupon': next_coupon,
            'days_accrued': days_accrued,
            'days_in_period': days_in_period
        }
        """

        # On recule par saut de fréquence jusqu'à ce que next_coupon
        # soit le premier coupon JUSTE APRÈS ou ÉGAL à la date de commande
        while next_coupon > order_date:
            potential_last = next_coupon - relativedelta(months=months_step)
            if potential_last <= order_date:
                # On a trouvé notre encadrement
                last_coupon = potential_last
                # next_coupon reste la valeur actuelle
                break
            next_coupon = potential_last

        last_coupon = next_coupon - relativedelta(months=months_step)

        # Calcul des deltas
        days_accrued = (order_date - last_coupon).days
        days_in_period = (next_coupon - last_coupon).days

        return {
            'last_coupon': last_coupon,
            'next_coupon': next_coupon,
            'days_accrued': days_accrued,
            'days_in_period': days_in_period
        }
    """

    def create_first_nav(self, fund):
        """
        Crée la première NAV pour un fond donné.
        """
        vals = {
            'name': 'VL du ' + fund.start_date.strftime('%d/%m/%Y'),
            'fund_id': fund.id,
            'valuation_date': fund.start_date,
            'unit_nav': fund.origin_nav,
            'nb_parts': 0,
            'Capital': fund.origin_nav,
            'non_distributable_sum': 0,
            'previous_fiscal_year_result': 0,
            'closed_fiscal_year_result': 0,
            'current_fiscal_year_result': 0,
            'state': 'validated'
        }
        res = self.env['efund.nav.session'].create(vals)
        if res:
            share_class = self.env['efund.nav.share'].search([('vehicule_fund_id', '=', res.get('fund_id'))], limit=1)
            if share_class:
                share_class.write({
                    'current_nav': res.get('fund_id'),
                    'vl_capital_init': res.get('Capital'),
                    'vl_non_distribuable': res.get('non_distributable_sum'),
                    'vl_res_anterieurs': res.get('previous_fiscal_year_result'),
                    'vl_res_clos': res.get('closed_fiscal_year_result'),
                    'vl_res_en_cours': res.get('current_fiscal_year_result'),
                    'valuation_date': res.get('valuation_date'),
                })
        return res

    # Obtenir le nombre de jour ou la date du dénouement d'une opération
    def get_settlement_details(self, operation_date, days_to_add):
        """
        Calcule la date de dénouement et le nombre de jours calendaires.
        Purchase_date: Date d'achat (J)
        days_to_add: 3 jours ouvrés
        """
        current_date = operation_date
        if days_to_add == 0:
            while True:
                # 1. Test Weekend (5=Samedi, 6=Dimanche)
                if current_date.weekday() >= 5:
                    current_date += datetime.timedelta(days=1)
                    continue

                # 2. Test Jours Fériés
                is_holiday = self.env['efund.public.holiday'].search_count([
                    ('holiday_date', '=', current_date),
                ])
                if is_holiday:
                    current_date += datetime.timedelta(days=1)
                    continue

                # Si on arrive ici, c'est un jour ouvré valide
                break

            # Cas standard : dénouement différé (ex: T+3)
        else:
            working_days_counted = 0
            while working_days_counted < days_to_add:
                current_date += datetime.timedelta(days=1)

                # Test Weekend
                if current_date.weekday() >= 5:
                    continue

                # Test Jours Fériés
                is_holiday = self.env['efund.public.holiday'].search_count([
                    ('holiday_date', '=', current_date),
                ])
                if is_holiday:
                    continue

                working_days_counted += 1

        settlement_date = current_date
        calendar_days = (settlement_date - operation_date).days

        return {
            'settlement_date': settlement_date,
            'calendar_days': calendar_days
        }

    # Générer le tableau des coupons
    def generate_coupon_schedule(self, montant, taux, frequence, date_valeur, date_maturite, base_calcul):
        """
        Génère un échéancier avec des montants de coupons constants.
        """
        if isinstance(date_valeur, str):
            date_valeur = datetime.strptime(date_valeur, '%Y-%m-%d').date()
        if isinstance(date_maturite, str):
            date_maturite = datetime.strptime(date_maturite, '%Y-%m-%d').date()

        freq_months = {'mensuel': 1, 'trimestriel': 3, 'semestriel': 6, 'annuel': 12}
        # On définit le nombre de périodes par an (Ex: 2 pour semestriel)
        periods_per_year = 12 / freq_months.get(frequence.lower(), 12)
        step = freq_months.get(frequence.lower(), 12)

        schedule = []
        current_date = date_valeur

        while current_date < date_maturite:
            next_date = current_date + relativedelta(months=step)
            if next_date >= date_maturite:
                next_date = date_maturite

            # --- CORRECTION ICI ---
            # Au lieu de calculer les jours réels, on divise le taux annuel
            # par le nombre de périodes dans l'année.
            # Exemple pour 6% annuel en semestriel : 6 / 2 = 3% fixe par coupon.

            montant_fixe = montant * (taux / 100) / periods_per_year

            schedule.append({
                'date_debut': current_date,
                'date_fin': next_date,
                'jours': step * 30,
                'montant': round(montant_fixe, 2),
            })

            current_date = next_date
            if next_date == date_maturite:
                break

        return schedule

    # Générer le tableau d'amortissement
    def generate_amortization_schedule(self, montant, taux_annuel, frequence, date_valeur, date_maturite,
                                       base_calcul=365, type_amortissement='in_fine'):

        freq_map = {'monthly': 12, 'quarterly': 4, 'semi_annual': 2, 'annual': 1, }

        if frequence not in freq_map:
            raise ValueError("Fréquence invalide")

        periods_per_year = freq_map[frequence]
        taux_periodique = taux_annuel / 100 / periods_per_year

        # Calcul du nombre total de périodes
        total_periods = int(
            (date_maturite.year - date_valeur.year) * periods_per_year +
            (date_maturite.month - date_valeur.month) / (12 / periods_per_year)
        )

        capital_restant = montant
        schedule = []
        annuite = 0

        # Annuité constante
        if type_amortissement == 'annuite_constante':
            annuite = (
                    montant * taux_periodique /
                    (1 - (1 + taux_periodique) ** -total_periods)
            )

        capital_constant = (
            montant / total_periods
            if type_amortissement == 'capital_constant'
            else 0
        )

        current_date = date_valeur

        for period in range(1, total_periods + 1):
            next_date = current_date + relativedelta(
                months=int(12 / periods_per_year)
            )

            days = (next_date - current_date).days

            interet = (
                    capital_restant * taux_periodique  # taux_annuel / 100 * days / base_calcul
            )

            if type_amortissement == 'in_fine':
                amortissement = montant if period == total_periods else 0
                annuite_period = interet + amortissement

            elif type_amortissement == 'annuite_constante':
                amortissement = annuite - interet
                annuite_period = annuite

            elif type_amortissement == 'capital_constant':
                amortissement = capital_constant
                annuite_period = interet + amortissement

            else:
                raise ValueError("Type d'amortissement invalide")

            capital_restant -= amortissement

            schedule.append({
                'periode': period,
                'date_debut': current_date,
                'date_fin': next_date,
                'next_date': next_date,
                'capital_initial': round(capital_restant + amortissement, 2),
                'interet': round(interet, 2),
                'amortissement': round(amortissement, 2),
                'annuite': round(annuite_period, 2),
                'capital_restant': round(max(capital_restant, 0), 2),
            })

            current_date = next_date

        return schedule

    def get_taux_by_frequency(self, annual_rate, frequency):
        if frequency == 'annual':
            return annual_rate
        elif frequency == 'semi_annual':
            return annual_rate / 2
        elif frequency == 'quarterly':
            return annual_rate / 4
        elif frequency == 'monthly':
            return annual_rate / 12
        else:
            raise ValueError(f"Unsupported frequency: {frequency}")

    def compute_accrued_interest_precise(self, nominal, annual_rate, compute_date, maturity_date,
                                         frequency='annual', tax_rate=0.0, add_day=0):
        # Taux réel annuel

        net_rate = (1 - (tax_rate / 100.0)) * annual_rate
        nb_periods_map = {'annual': 1, 'semi_annual': 2, 'quarterly': 4, 'monthly': 12}
        periods_per_year = nb_periods_map.get(frequency, 1)

        # Obtenir les dates de coupon et le nombre de jours couru
        res = self.get_coupon_period(compute_date, maturity_date, periods_per_year)
        if not res:
            return {'interest_gross': 0.0, 'interest_net': 0.0}

        details = self.get_settlement_details(compute_date, add_day)
        day_to_add = details.get('calendar_days', 0)

        nb_jour = res.get('days_accrued', 0) + day_to_add
        year_base = res.get('days_in_period')

        if not year_base or year_base == 0:
            return {'interest_gross': 0.0, 'interest_net': 0.0}

        interet_period_net = self.get_taux_by_frequency(net_rate, frequency)
        interet_period_brut = self.get_taux_by_frequency(annual_rate, frequency)

        interest_gross = nb_jour / year_base * interet_period_brut * nominal / 100
        interest_net = nb_jour / year_base * interet_period_net * nominal / 100
        return {
            'interest_gross': interest_gross,
            'interest_net': interest_net,
        }

    def build_event_payload(self, event, vehicule_id, name, date_operation, playload):

        event_type_id = self.env['efund.event.type'].search([('sigle', '=', event)], limit=1)
        if not event_type_id:
            raise ValidationError(
                f" Le type d'évènement {event} n'est pas définir. Merci de contacter votre Administrateur")

        return {
            'event_type_id': event_type_id.id,
            'vehicule_id': vehicule_id,
            'reference': name,
            'event_date': date_operation,
            'state': 'draft',
            'payload': playload,
        }

    def generate_all_coupon_dates(self, value_date, maturity_date, coupon_frequency):
        dates = []
        current_date = value_date

        while current_date < maturity_date:
            next_date = self._get_next_coupon_date(current_date, maturity_date, coupon_frequency)
            if next_date >= maturity_date:
                dates.append(maturity_date)
                break
            dates.append(next_date)
            current_date = next_date

        # S'assurer que la date de maturité est incluse
        if maturity_date not in dates:
            dates.append(maturity_date)

        return dates

    def _get_next_coupon_date(self, from_date, maturity_date, coupon_frequency):

        if coupon_frequency == 'annual':
            return from_date + relativedelta(years=1)
        elif coupon_frequency == 'semi_annual':
            return from_date + relativedelta(months=6)
        elif coupon_frequency == 'quarterly':
            return from_date + relativedelta(months=3)
        elif coupon_frequency == 'monthly':
            from_date + relativedelta(months=1)
        else:
            return maturity_date

    def _compute_coupon_amount(self):
        """Calcule le montant de chaque coupon de manière constante"""
        for coupon in self:
            # 1. On définit un diviseur fixe par fréquence
            # (Indépendant du calendrier réel)
            freq_map = {
                'annuel': 1,
                'semestriel': 2,
                'trimestriel': 4,
                'mensuel': 12
            }

            # On récupère la fréquence depuis le bond ou le mandat
            frequence = coupon.bond_id.coupon_frequency  # ex: 'semestriel'
            periods = freq_map.get(frequence, 1)

            # 2. Calcul standardisé
            # Formule : (Nominal * Taux) / Nombre de périodes par an
            nominal = coupon.bond_id.face_value
            taux_annuel = coupon.bond_id.coupon_rate / 100.0

            # Le montant sera exactement le même en 2027, 2028, etc.
            coupon.amount = (nominal * taux_annuel) / periods

    def get_net_asset_value(self, vehicule, date_target):
        """
        Calcule l'Actif Net du véhicule à une date précise.
        NAV = Somme(Positions Titres à date) + Somme(Soldes Espèces à date)
        """

        total_portfolio_value = 0.0
        total_cash_balance = 0.0

        # 1. Valorisation du Portefeuille (Titres)
        # On récupère les positions du véhicule
        positions = self.env['efund.vehicule.portfolio'].search([
            ('vehicule_id', '=', vehicule.id),
            ('first_price_date', '<=', date_target)
        ])

        if positions:
            for pos in positions:
                # On récupère la quantité à date (via les ordres exécutés avant date_target)
                # Note : Vous devrez peut-être adapter selon votre modèle d'ordres
                orders = self.env['efund.investment.transaction'].search([
                    ('vehicule_id', '=', vehicule.id),
                    ('instrument_id', '=', pos.instrument_id.id),
                    ('date_transaction', '<=', date_target),
                    ('state', '=', 'settled')
                ])



                qty_at_date = sum(o.quantity if o.move_type == 'in' else -o.quantity for o in orders)

                # On récupère le cours à la date cible (ou le plus proche avant)
                last_price_rec = self.env['efund.vehicule.instrument.core.price'].search([
                    ('instrument_id', '=', pos.instrument_id.id),
                    ('vehicule_id', '=', vehicule.id),
                    ('is_validated', '=', True),
                    ('date', '=', date_target)
                ], order='date desc', limit=1)

                # 2. Repli (Fallback) : Cours global (ex: Action BRVM)
                if not last_price_rec:
                    last_price_rec = self.env['efund.vehicule.instrument.core.price'].search([
                        ('instrument_id', '=', pos.instrument_id.id),
                        ('vehicule_id', '=', False),
                        ('is_validated', '=', True),
                        ('date', '=', date_target),
                    ], order='date desc', limit=1)


                if not last_price_rec:
                    if pos.instrument_id.instrument_type == 'bond':
                        _logger.info(f" les conditions date achat: {pos.first_price_date} date de recherche: {date_target} date maturité : {pos.maturity_date} ")
                        if pos.first_price_date < date_target and date_target < pos.maturity_date:
                            last_price_rec = self.generate_bond_price(pos, date_target)
                            _logger.info(f" j'ai trouvé le prix : {last_price_rec.price} ")
                        else:
                            last_price_rec.price = 0
                    elif pos.instrument_id.instrument_type == 'tcn':
                        last_price_rec = self.generate_tcn_price(pos, date_target)
                    elif pos.instrument_id.instrument_type == 'dat':
                        last_price_rec = self.generate_dat_price(pos, date_target)
                    elif pos.instrument_id.instrument_type == 'opcvm':
                        if pos.first_price_date < date_target and pos.quantity > 0:
                            last_price_rec = self.generate_opcvm_price(pos, date_target)
                        else:
                            last_price_rec.price = 0
                    elif pos.instrument_id.instrument_type == 'equity':
                        raise UserError(_("Merci de saisir le cours à date"))
                    else:
                        raise UserError(_("Le type d'instrument n'est pas pris en charge"))

                if last_price_rec:
                    price = last_price_rec.price
                else:  # Appel du calcul de prix
                    pass

                total_portfolio_value += (qty_at_date * price) + last_price_rec.interest if last_price_rec else 0

        # 2. Valorisation du Cash (Soldes Espèces)
        # On récupère tous les comptes espèces du véhicule
        cash_accounts = self.env['efund.vehicule.cash'].search([
            ('vehicule_id', '=', vehicule.id)
        ])

        for cash in cash_accounts:
            # On calcule le solde roulant SQL à la date cible
            # C'est ici qu'on applique votre logique balance_running
            moves = self.env['efund.vehicule.cash.move'].search([
                ('vehicule_cash_id', '=', cash.id),
                ('date', '<=', date_target)
            ])

            balance_at_date = sum(m.amount if '_in' in m.move_type else -m.amount for m in moves)
            total_cash_balance += balance_at_date

        # 3. Résultat Final
        net_asset_value = total_portfolio_value + total_cash_balance

        return {
            'date': date_target,
            'portfolio_value': total_portfolio_value,
            'cash_value': total_cash_balance,
            'total_nav': net_asset_value,
        }

    # Cours lissé
    def compute_linear_actuariat_value_at_date(self, compute_date, buyed_price, buyed_date, nominal_price,
                                               maturity_date):

        if not compute_date or not buyed_price or not nominal_price or not maturity_date:
            raise UserError(_("Veuillez renseigner tous les champs obligatoires."))
        else:
            if compute_date <= buyed_date:
                return buyed_price

            if compute_date >= maturity_date:
                return nominal_price

            total_days = (maturity_date - buyed_date).days
            if total_days <= 0:
                return buyed_price

            # Linéaire
            daily_accretion = (nominal_price - buyed_price) / total_days
            days_elapsed = (compute_date - buyed_date).days

            linear_value = buyed_price + daily_accretion * days_elapsed

            # Actuariat
            yield_rate = ((nominal_price / buyed_price) ** (365 / total_days) - 1)
            base = 366 if calendar.isleap(compute_date.year) else 365

            return linear_value

    def update_or_create_price(self, instrument, vehicule, date, val, interest, source):

        price_rec = self.env["efund.vehicule.instrument.core.price"].search([
            ('instrument_id', '=', instrument.id),
            ('vehicule_id', '=', vehicule.id),
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
        _logger.info(f"************update_or_create_price : {vals}")

        if price_rec:
            price_rec.write(vals)
        else:
            price_rec = self.env['efund.vehicule.instrument.core.price'].create(vals)
        return price_rec

    def generate_dat_price(self, position, target_date):
        """ Calcule le cours du DAT : Valeur nominale + intérêts linéarisés """
        # On récupère les détails du DAT (taux, date début)

        if target_date < position.value_date:
            raise ValidationError(
                f"La date de calcul {target_date} est antérieure à la date de début du DAT{position.value_date}")
        if target_date > position.maturity_date:
            raise ValidationError(
                f"La date de calcul {target_date} est postérieure à la date de maturité du DAT{position.maturity_date}")

        if position and position.value_date and position.rate:
            days = (target_date - position.value_date).days
            if days < 0: days = 0

            computed_factor = (position.rate / 100.0 * days / 365)
            interest_value = computed_factor * position.last_price if position.last_price else position.first_price
            result = self.update_or_create_price(position.instrument, position.vehicule, target_date,
                                                 position.first_price, interest_value, 'internal')

            return result

    def generate_tcn_price(self, position, target_date):
        accrual = self.env['efund.service'].get_tcn_interest(position.rate, position.value_date,
                                                             position.quantity * position.first_price, 360)
        result = self.update_or_create_price(position.instrument_id, position.vehicule_id, target_date,
                                             position.first_price, accrual, 'internal')
        return result

    def generate_bond_price(self, position, target_date):
        bond = self.env['efund.vehicule.instrument.core.bond'].search([
            ('instrument_id', '=', position.instrument_id.id)
        ], limit=1)
        _logger.info(f"************ generate_bond_price : {bond}")
        if bond.instrument_id.is_listed:
            _logger.info(f"***************** le titre est coté")
            if bond.instrument_id.valuation_method == 'listed':
               _logger.info(f"***************** le titre est lissé")
               last_price = self.compute_linear_actuariat_value_at_date(target_date, position.first_price,position.first_price_date, bond.face_value, bond.maturity_date)
            else:
                raise ValidationError(f"Merci de saisir manuellement le cours")

            # l'instrument n'est pas coté alors on reprend le prix d'achat
        else:
            # On cherche le dernier prix validé
            last_price_obj = self.env["efund.vehicule.instrument.core.price"].search([
                ('instrument_id', '=', position.instrument_id.id),
                ('vehicule_id', '=', position.vehicule_id.id),
                ('is_validated', '=', True),
                ('date', '<', target_date)
            ], order='date desc', limit=1)
            if last_price_obj:
                last_price = last_price_obj.price
            else:
                last_price = position.first_price

        res = self.compute_accrued_interest_precise(bond.face_value, bond.rate_net, target_date, bond.maturity_date, bond.coupon_frequency, tax_rate=0.0, add_day=0)
        interest = res.get('interest_net') * position.quantity
        result = self.update_or_create_price(position.instrument_id, position.vehicule_id, target_date, last_price, interest, 'internal')
        return result

    def generate_opcvm_price (self, position, target_date):
        raise ValidationError(f"Merci de saisir manuellement le cours")

    def get_instrument_avg_price(self, intrument, vehicule):
        pos = self.env['efund.vehicule.portfolio'].search([
            ('instrument_id', '=', intrument.id),
            ('vehicule_id', '=', vehicule.id),
        ])
        return pos.avg_cost if pos else 0



    """ Revnir terminer la procédure
    def get_valuation_price_at_date(self, position, valuation_date):
        
        Calcule le prix théorique ou récupère le prix de marché d'un instrument
        à une date donnée selon sa nature.
       

        # 1. Cas des Titres de Créances / Bons / DAT (Valorisation par amortissement/intérêts)
        # 1. Aller chercher le dernier prix VALIDÉ pour cet instrument
        last_price_rec = self.env['efund.vehicule.instrument.core.price'].search([
            ('instrument_id', '=', position.instrument_id.id),
            ('vehicule_id', '=', position.vehicule_id.id),
            ('is_validated', '=', True),
            ('date', '=', valuation_date)
        ], order='date desc', limit=1)

        # 2. Repli (Fallback) : Cours global (ex: Action BRVM)
        if not last_price_rec:
            last_price_rec = self.env['efund.vehicule.instrument.core.price'].search([
                ('instrument_id', '=', position.instrument_id.id),
                ('vehicule_id', '=', False),
                ('is_validated', '=', True),
                ('date', '=', valuation_date)
            ], order='date desc', limit=1)

        if not last_price_rec:
            if position.instrument_id.instrument_type == 'bond':
                # On récupère les infos d'émission (Nominal, Date émission, Maturité)
                # Selon votre modèle, ces infos sont dans le modèle spécifique lié
                bond_data = self.env['efund.vehicule.instrument.core.bond'].search([
                    ('instrument_id', '=', position.instrument_id.id)
                ], limit=1)

                if bond_data:
                    # Si l'instrument utilise une valorisation linéaire (Lissage)
                    # On utilise votre fonction 'compute_linear_actuariat_value_at_date'
                    if bond_data.instrument_id.is_listed:
                        if bond_data.instrument_id.valuation_method == 'listed':
                            return self.compute_linear_actuariat_value_at_date(
                                valuation_date=valuation_date,
                                buyed_price=position.first_price,
                                buyed_date=position.first_price_date,
                                nominal_price=bond_data.face_value,
                                maturity_date=bond_data.maturity_date
                            )

                        # Si c'est un calcul d'intérêts courus (DAT / TCN)
                        elif instrument.valuation_method == 'accrued_interest':
                            # Formule simplifiée : Nominal * Taux * (Jours courus / Base)
                            days_accrued = (valuation_date - bond_data.issue_date).days
                            # On assume une base 360 pour les TCN/DAT (à adapter selon vos conventions)
                            interest = bond_data.face_value * (bond_data.coupon_rate / 100) * (days_accrued / 360.0)
                            return bond_data.face_value + interest

            # 2. Cas des Actions / OPCVM (Valorisation par le dernier cours de marché)
            # On cherche le prix validé le plus proche (inférieur ou égal) à la date cible
            market_price = self.env['efund.vehicule.instrument.core.price'].search([
                ('instrument_id', '=', instrument.id),
                ('date', '<=', valuation_date),
                ('is_validated', '=', True)
            ], order='date desc', limit=1)

            if market_price:
                return market_price.price

            # 3. Fallback : Si aucun prix n'est trouvé, on retourne le coût moyen ou le prix d'émission
            return instrument.last_validated_price or 0.0
            
        """
