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
            'capital': fund.origin_nav,
            'non_distributable_sum': 0,
            'previous_fiscal_year_result': 0,
            'closed_fiscal_year_result': 0,
            'current_fiscal_year_result': 0,
            'state': 'validated'
        }
        res = self.env['efund.nav.session'].create(vals)
        if res:
            share_class = self.env['efund.fund.share.class'].search([('vehicule_fund_id', '=', res.fund_id.id)], limit=1)
            if share_class:
                share_class.write({
                    'current_nav': res.unit_nav,
                    'vl_capital_init': res.capital,
                    'vl_non_distribuable': res.non_distributable_sum,
                    'vl_res_anterieurs': res.previous_fiscal_year_result,
                    'vl_res_clos': res.closed_fiscal_year_result,
                    'vl_res_en_cours': res.current_fiscal_year_result,
                    'valuation_date': res.valuation_date,
                })
            else:
                share_class.create({
                    'name': 'Classe par défaut',
                    'vehicule_fund_id': fund.id,
                    'current_nav': fund.origin_nav,
                    'vl_capital_init': fund.origin_nav,
                    'is_default': True,
                    'vl_non_distribuable': res.non_distributable_sum,
                    'vl_res_anterieurs': res.previous_fiscal_year_result,
                    'vl_res_clos': res.closed_fiscal_year_result,
                    'vl_res_en_cours': res.current_fiscal_year_result,
                    'valuation_date': fund.start_date,
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

    # Tableau d'amortissemnt à partir de la date de maturité
    def generate_amortization_schedule_from_maturity(self, montant, taux_annuel, frequence, date_maturite,
                                                     date_acquisition, base_calcul=365, type_amortissement='in_fine'):

        freq_map = {'monthly': 12, 'quarterly': 4, 'semi_annual': 2, 'annual': 1}
        months_step = int(12 / freq_map[frequence])
        taux_periodique = taux_annuel / 100 / freq_map[frequence]

        # --- ÉTAPE 1 : RETROUVER LES DATES ---
        # On remonte depuis la maturité pour trouver les dates de coupon
        coupon_dates = [date_maturite]
        current_back_date = date_maturite

        # On remonte jusqu'à trouver une date antérieure à la date d'acquisition
        while current_back_date > date_acquisition:
            current_back_date -= relativedelta(months=months_step)
            coupon_dates.insert(0, current_back_date)

        # La date de début de notre tableau est le coupon juste avant l'acquisition
        # (C'est la date de départ pour le calcul du coupon couru)
        date_depart_tableau = coupon_dates[0]

        # --- ÉTAPE 2 : CALCUL DES PÉRIODES ---
        # Le nombre de périodes restantes est la taille de la liste moins 1
        total_periods_restantes = len(coupon_dates) - 1

        capital_restant = montant
        schedule = []

        # Calcul de l'annuité si besoin (basé sur le restant)
        annuite = 0
        if type_amortissement == 'annuite_constante':
            annuite = (montant * taux_periodique / (1 - (1 + taux_periodique) ** -total_periods_restantes))

        capital_constant = montant / total_periods_restantes if type_amortissement == 'capital_constant' else 0

        # --- ÉTAPE 3 : GÉNÉRATION DU TABLEAU ---
        for i in range(total_periods_restantes):
            date_debut = coupon_dates[i]
            date_fin = coupon_dates[i + 1]

            interet = capital_restant * taux_periodique

            if type_amortissement == 'in_fine':
                amortissement = montant if (i == total_periods_restantes - 1) else 0
                annuite_period = interet + amortissement
            elif type_amortissement == 'annuite_constante':
                amortissement = annuite - interet
                annuite_period = annuite
            elif type_amortissement == 'capital_constant':
                amortissement = capital_constant
                annuite_period = interet + amortissement

            cap_initial = capital_restant
            capital_restant -= amortissement

            schedule.append({
                'periode': i + 1,
                'date_debut': date_debut,
                'date_fin': date_fin,
                'capital_initial': round(cap_initial, 2),
                'interet': round(interet, 2),
                'amortissement': round(amortissement, 2),
                'annuite': round(annuite_period, 2),
                'capital_restant': round(max(capital_restant, 0), 2),
                'is_accrued_period': date_debut < date_acquisition < date_fin  # Marqueur pour le coupon couru
            })

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

        event_type_id = self.env['efund.event.type.new'].search([('sigle', '=', event)], limit=1)
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
                        last_price_rec = self.generate_dat_tcn_price(pos, date_target)
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

    def get_portfolio_asset_value(self, vehicule, date_target):
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
            ('first_price_date', '<=', date_target),
            ('quantity', '>', 0)
        ])

        portfolio_at_date = []

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
                        if pos.first_price_date <= date_target and date_target <= pos.maturity_date:
                            last_price_rec = self.generate_bond_price(pos, date_target)
                        else:
                            raise ValidationError(f"Une erreur est survenue lors de la recherche du prix du bond : {pos.instrument_id.name}")
                    elif pos.instrument_id.instrument_type == 'tcn':
                        last_price_rec = self.generate_tcn_price(pos, date_target)
                    elif pos.instrument_id.instrument_type == 'dat':
                        last_price_rec = self.generate_dat_tcn_price(pos, date_target)
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

                portfolio_at_date.append({
                    'instrument': pos.instrument_id,
                    'date': date_target,
                    'quantity': qty_at_date,
                    'price': last_price_rec.price,
                    'interest': last_price_rec.interest if last_price_rec else 0,
                    'total_amount': qty_at_date * price + last_price_rec.interest if last_price_rec else 0,
                })
                #_logger.info(f"Portfolio at date {date_target}: {portfolio_at_date} : {}")


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

        portfolio_at_date.append({
            'intrument': False,
            'date': date_target,
            'quantity': 1,
            'price': total_cash_balance,
            'interest': 0,
            'total_amount': total_cash_balance,
        })

        return portfolio_at_date

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

        if price_rec:
            price_rec.write(vals)
        else:
            price_rec = self.env['efund.vehicule.instrument.core.price'].create(vals)
        return price_rec

    def generate_dat_tcn_price(self, position, target_date):
        if target_date < position.value_date:
            raise ValidationError(
                f"La date de calcul {target_date} est antérieure à la date de début du DAT{position.value_date}")
        if target_date > position.maturity_date:
            raise ValidationError(
                f"La date de calcul {target_date} est postérieure à la date de maturité du DAT{position.maturity_date}")


        interest_value = self.generate_lenear_amount_value(position.bond_dat_interest, position.value_date, position.maturity_date, target_date)
        result = self.update_or_create_price(position.instrument_id, position.vehicule_id, target_date,
                                                 position.face_value, interest_value, 'internal')
        return result



    def generate_bond_price(self, position, target_date):
        bond = self.env['efund.vehicule.instrument.core.bond'].search([
            ('instrument_id', '=', position.instrument_id.id)
        ], limit=1)
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
                last_price = position.face_value if position.face_value else bond.face_value

        res = self.compute_accrued_interest_precise(bond.face_value, bond.rate_net, target_date, bond.maturity_date, bond.coupon_frequency, tax_rate=0.0, add_day=0)
        interest = res.get('interest_net') * position.quantity
        result = self.update_or_create_price(position.instrument_id, position.vehicule_id, target_date, last_price, interest, 'internal')
        return result

    def generate_opcvm_price (self, position, target_date):
        raise ValidationError(f"Merci de saisir manuellement le cours")

    def get_interest_valuation_json(self, amount, rate, tax_rate, date_start, date_maturity, target_date, base_year, interest_type):
        """
        Calcule l'intérêt lissé et retourne le détail au format JSON.
        :param amount: Montant nominal ou d'investissement
        :param rate: Taux annuel (ex: 0.05 pour 5%)
        :param date_start: Date de début (valeur)
        :param date_maturity: Date d'échéance
        :param target_date: Date de calcul (Date de VL)
        :param interest_type: 'pre' pour précompté, 'post' pour postcompté
        :return: JSON string avec le détail du calcul
        """
        if not (date_start and date_maturity and target_date):
            raise ValidationError('Merci de vérifier les dates')

        # 1. Calcul des durées
        total_duration = (date_maturity - date_start).days
        days_elapsed = (target_date - date_start).days
        days_elapsed = max(0, min(days_elapsed, total_duration))

        if total_duration <= 0:
            raise ValidationError('Merci de vérifier les dates')

        total_interest = 0.0
        accrued_interest = 0.0
        valuation_at_date = 0.0
        base_year = int(base_year)
        rate = rate / 100
        day_rate = rate / base_year

        # --- LOGIQUE POSTCOMPTÉ ---
        # L'intérêt s'ajoute au montant initial
        if interest_type == 'postpaid':
            total_interest = amount * rate * (total_duration / base_year)
            accrued_interest = (total_interest / total_duration) * days_elapsed
            valuation_at_date = amount + accrued_interest
            _logger.info(f"************total_interest : {total_interest} accrued_interest : {accrued_interest} valuation_at_date : {valuation_at_date} ")
        elif interest_type == 'prepaid':
            total_interest = amount * rate * (total_duration / base_year)
            #interet = (total_interest / total_duration) * days_elapsed
            total_interest = total_interest * ((1 + day_rate) ** -total_duration)
            valuation_at_date = amount - accrued_interest

        tax_en_decimal = tax_rate/100
        interet_total_net = 0.0
        interet_total_net = total_interest * (1 - tax_en_decimal)

        return {'interet_brut': total_interest, 'interet_total_net': interet_total_net, 'accrued_interest': accrued_interest, 'total_valuation': valuation_at_date}

    def get_instrument_avg_price(self, intrument, vehicule):
        pos = self.env['efund.vehicule.portfolio'].search([
            ('instrument_id', '=', intrument.id),
            ('vehicule_id', '=', vehicule.id),
        ])
        return pos.avg_cost if pos else 0

    def generate_lenear_amount_value(self, amount, start_date, end_date, target_date):
        """
        Valorisation TCN ou dat par lissage de l'intérêt précompté (Amortissement linéaire)
        """

        date_achat = start_date
        date_echeance = end_date


        if not date_echeance or not date_achat:
            return False

        # 3. Calcul de la période
        total_days = (date_echeance - date_achat).days
        days_elapsed = (target_date - date_achat).days

        # Sécurité : si on est avant la date d'achat ou après l'échéance
        days_elapsed = max(0, min(days_elapsed, total_days))

        if total_days > 0:

            accrued_interest = (amount / total_days) * days_elapsed
        else:
            accrued_interest = 0

        # 6. Mise à jour du prix
        # Le prix reste le prix d'achat (flat), c'est l'accrued_interest qui porte la valorisation
        """
        result = self.update_or_create_price(
            instrument,
            position.vehicule_id,
            target_date,
            position.first_price,
            accrued_interest,
            'internal'
        )
        """
        return accrued_interest

    def compute_and_update_price(self,pos, date_target):
        # On récupère le cours à la date cible (ou le plus proche avant)
        last_price_rec = self.env['efund.vehicule.instrument.core.price'].search([
            ('instrument_id', '=', pos.instrument_id.id),
            ('vehicule_id', '=', pos.vehicule_id.id),
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
                if pos.first_price_date <= date_target and date_target <= pos.maturity_date:
                    last_price_rec = self.generate_bond_price(pos, date_target)
                else:
                    raise ValidationError(
                        f"Une erreur est survenue lors de la recherche du prix du bond : {pos.instrument_id.name}")
            elif pos.instrument_id.instrument_type in ('tcn','dat'):
                self.generate_dat_tcn_price(pos, date_target)
            elif pos.instrument_id.instrument_type == 'opcvm':
                if pos.first_price_date < date_target and pos.quantity > 0:
                    self.generate_opcvm_price(pos, date_target)
                else:
                    last_price_rec.price = 0
            elif pos.instrument_id.instrument_type == 'equity':
                raise UserError(_("Merci de saisir le cours à date"))
            else:
                raise UserError(_("Le type d'instrument n'est pas pris en charge"))





