import datetime
from dateutil.relativedelta import relativedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class EfundService(models.Model):
    _name = 'efund.service'
    _description = 'Service for Efund'

    def generate_amortization_table(self,montant, taux, frequence, date_valeur, date_maturite, base_calcul, type_amort='in_fine'):
        # Initialisation
        if isinstance(date_valeur, str):
            date_valeur = datetime.strptime(date_valeur, '%Y-%m-%d').date()
        if isinstance(date_maturite, str):
            date_maturite = datetime.strptime(date_maturite, '%Y-%m-%d').date()

        freq_months = {'mensuel': 1, 'trimestriel': 3, 'semestriel': 6, 'annuel': 12}
        step = freq_months.get(frequence, 12)

        # 1. Calcul du nombre total d'échéances
        nb_echeances = 0
        tmp_date = date_valeur
        while tmp_date < date_maturite:
            tmp_date += relativedelta(months=step)
            nb_echeances += 1

        schedule = []
        capital_restant = montant
        current_date = date_valeur
        taux_periodique = (taux / 100) / (12 / step)

        for i in range(1, nb_echeances + 1):
            next_date = current_date + relativedelta(months=step)
            if next_date > date_maturite: next_date = date_maturite

            jours = (next_date - current_date).days
            interet = capital_restant * (taux / 100) * (jours / base_calcul)

            principal = 0

            if type_amort == 'in_fine':
                # Capital remboursé seulement à la dernière échéance
                principal = montant if i == nb_echeances else 0

            elif type_amort == 'constant_principal':
                # Capital divisé équitablement
                principal = montant / nb_echeances

            elif type_amort == 'constant_annuity':
                # Formule de l'annuité : A = P * r / (1 - (1+r)^-n)
                annuite_constante = montant * taux_periodique / (1 - (1 + taux_periodique) ** -nb_echeances)
                principal = annuite_constante - interet

            # Ajustement pour la dernière échéance (arrondis)
            if i == nb_echeances:
                principal = capital_restant

            annuite = principal + interet
            capital_restant -= principal

            schedule.append({
                'rang': i,
                'date': next_date,
                'principal': round(principal, 2),
                'interet': round(interet, 2),
                'annuite': round(annuite, 2),
                'capital_restant_fin': round(max(0, capital_restant), 2)
            })
            current_date = next_date

        return schedule

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
                # On affiche 30 jours par mois ou le prorata théorique pour l'affichage
                'jours': step * 30,
                'montant': round(montant_fixe, 2),
            })

            current_date = next_date
            if next_date == date_maturite:
                break

        return schedule

    """
    def generate_coupon_schedule(self,montant, taux, frequence, date_valeur, date_maturite, base_calcul):
        
        :param base_calcul: 360 ou 365
        
        if isinstance(date_valeur, str):
            date_valeur = datetime.strptime(date_valeur, '%Y-%m-%d').date()
        if isinstance(date_maturite, str):
            date_maturite = datetime.strptime(date_maturite, '%Y-%m-%d').date()

        freq_months = {'mensuel': 1, 'trimestriel': 3, 'semestriel': 6, 'annuel': 12}
        step = freq_months.get(frequence.lower(), 12)

        schedule = []
        current_date = date_valeur

        while current_date < date_maturite:
            next_date = current_date + relativedelta(months=step)
            if next_date >= date_maturite:
                next_date = date_maturite

            jours_periode = (next_date - current_date).days
            # Utilisation de la base dynamique (360 ou 365)
            montant_reel = montant * (taux / 100) * (jours_periode / base_calcul)

            schedule.append({
                'date_debut': current_date,
                'date_fin': next_date,
                'jours': jours_periode,
                'montant': round(montant_reel, 2),
            })

            current_date = next_date
            if next_date == date_maturite:
                break

        return schedule

    """


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

    """
    def _compute_coupon_amount(self):
        Calcule le montant de chaque coupon
        for coupon in self:
            if coupon.bond_id.coupon_frequency == 'annual':
                periods = 1
            elif coupon.bond_id.coupon_frequency == 'semi_annual':
                periods = 2
            elif coupon.bond_id.coupon_frequency == 'quarterly':
                periods = 4
            elif coupon.bond_id.coupon_frequency == 'monthly':
                periods = 12
            else:
                periods = 1

            annual_coupon = coupon.bond_id.face_value * (coupon.bond_id.coupon_rate / 100)
            coupon.coupon_amount = annual_coupon / periods
            
            """

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

    """
    def _compute_coupon_amount(self):
        Calcule le montant de chaque coupon de manière constante
        for coupon in self:
            # 1. Définir le diviseur selon la fréquence
            # Peu importe l'année, on divise par un nombre de périodes fixe
            freq_map = {
                'annual': 1,
                'semi_annual': 2,
                'quarterly': 4,
                'monthly': 12
            }
            periods = freq_map.get(coupon.bond_id.coupon_frequency, 1)

            # 2. Calcul constant : (Nominal * Taux) / Nombre de périodes
            # Exemple : 10 000 000 * 6.5% / 2 (pour semestriel) = 325 000
            annual_rate = coupon.bond_id.coupon_rate / 100.0
            nominal = coupon.bond_id.face_value

            # Le montant est désormais identique chaque année
            coupon.amount = (nominal * annual_rate) / periods
    """