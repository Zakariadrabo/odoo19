import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundService(models.Model):
    _name = 'efund.service'
    _description = 'Service for Efund'


    # Obtenir le dernier coupon
    def get_coupon_period(self, order_date, maturity_date, frequency=1):
        """
        Calcule les dates de coupon entourant la commande.
        :param frequency: Nombre de coupons par an (1=Annuel, 2=Semestriel, 4=Trimestriel)
        """
        if not order_date or not maturity_date:
            return False

        # Déterminer le pas de recul en mois selon la fréquence
        # Annuel = 12 mois, Semestriel = 6 mois, Trimestriel = 3 mois
        months_step = 12 // frequency

        # On part de la maturité (le dernier coupon possible)
        next_coupon = maturity_date

        # On recule par saut de fréquence jusqu'à ce que next_coupon
        # soit le premier coupon JUSTE APRÈS ou ÉGAL à la date de commande
        while next_coupon > order_date:
            potential_last = next_coupon - relativedelta(months=months_step)
            if potential_last < order_date:
                # On a trouvé notre encadrement :
                # potential_last < order_date <= next_coupon
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

    #Générer le tableau d'amortissement
    def generate_amortization_schedule(self,montant,taux_annuel, frequence, date_valeur,date_maturite, base_calcul=365,type_amortissement='in_fine'):

        freq_map = {'monthly': 12,'quarterly': 4,'semi_annual': 2,'annual': 1,}

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
        #self.ensure_one()

        #Taux réel annuel
        net_rate = (1 - (tax_rate / 100.0)) * annual_rate
        nb_periods_map = {'annual': 1, 'semi_annual': 2, 'quarterly': 4, 'monthly': 12}
        periods_per_year = nb_periods_map.get(frequency, 1)

        #Obtenir les dates de coupon et le nombre de jours couru
        res = self.get_coupon_period(compute_date, maturity_date, periods_per_year)
        if not res:
            return {'interest_gross': 0.0, 'interest_net': 0.0}

        details = self.get_settlement_details(compute_date, add_day)
        day_to_add = details.get('calendar_days',0)

        nb_jour = res.get('days_accrued',0) + day_to_add
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
        """
        #Obtenir le nombre jour en tenant compte de la date de dénouement
        days = 0 if (self.instrument_id.instrument_type in ('dat','opcvm') or self.instrument_id.settlement_mode == 'direct') else 3
        details = self.get_settlement_details(settlement_date, days)
        final_settlement_date = details['settlement_date']       
        Calcule l'intérêt couru avec une base dynamique (Dernier Coupon - Prochain Coupon)
        
        # 1. Détermination du prochain coupon pour calculer la base de la période
        freq_map = {
            'annual': relativedelta(years=1),
            'semi_annual': relativedelta(months=6),
            'quarterly': relativedelta(months=3),
            'monthly': relativedelta(months=1),
        }
        nb_periods_map = {'annual': 1, 'semi_annual': 2, 'quarterly': 4, 'monthly': 12}

        delta = freq_map.get(frequency, relativedelta(years=1))
        next_coupon_date = last_coupon_date + delta
        periods_per_year = nb_periods_map.get(frequency, 1)

        # 2. Calcul des jours courus avec dénouement (J+3 ouvré)
        # Note: On part de la date de l'ordre, settlement_details nous donne la date de valeur
        days = 0 if (self.instrument_id.instrument_type in ('dat', 'opcvm') or self.instrument_id.settlement_mode == 'direct') else 3
        details = self.get_settlement_details(settlement_date, days)
        final_settlement_date = details['settlement_date']

        # Nombre de jours entre le dernier coupon et la date de valeur réelle
        days_accrued = (settlement_date - last_coupon_date).days

        # 3. Calcul de la base de la période (Le dénominateur précis)
        days_in_period = 0
        if day_count == 'act/act':
            # Nombre de jours réels dans la période de coupon actuelle
            days_in_period = (next_coupon_date - last_coupon_date).days
            # La base annuelle devient : Jours de la période * Nombre de périodes par an
            year_base = days_in_period  # * periods_per_year
        elif day_count == '30/360':
            year_base = 360
            # (Logique 30/360 simplifiée pour l'exemple)
        else:
            year_base = 365 if day_count == 'act/365' else 360

        # 4. Calcul de l'intérêt BRUT
        # Formule : Nominal * Taux Annuel * (Jours Courus / Base Dynamique)
        nbjour_denouement = self.get_settlement_details(settlement_date,0 if self.instrument_id.instrument_type in ('dat','opcvm') or self.instrument_id.settlement_mode !='direct' else 3)
        nb_days_to_add = nbjour_denouement['calendar_days']

        taux_reel = (1 - (tax_rate / 100.0)) * annual_rate
        nb_jour = days_accrued + nb_days_to_add

        interet_period = taux_reel / periods_per_year

        interest_gross = nb_jour / year_base * (annual_rate / periods_per_year) * nominal / 100

        # 5. Application de la fiscalité (IRVM/IRCM)
        interest_net = nb_jour / year_base * interet_period * nominal / 100

        return {
            'interet_period': interet_period,
            'last_coupon_date': last_coupon_date,
            'next_coupon_date': next_coupon_date,
            'settlement_date_final': final_settlement_date,
            'days_accrued': days_accrued,
            'days_in_period': days_in_period if day_count == 'act/act' else year_base,
            'interest_gross': round(interest_gross, 8),
            'interest_net': round(interest_net, 8),
        }
        """


    def build_event_payload_opcvm(self, event, vehicule_id, name, date_operation, playload):

        event_type_id = self.env['efund.event.type'].search([('sigle', '=', event)], limit=1)
        if not event_type_id:
            raise ValidationError(f" Le type d'évènement {event} n'est pas définir. Merci de contacter votre Administrateur")

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

