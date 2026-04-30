import csv
import logging

from odoo import models, api, _
from odoo.exceptions import UserError
from odoo.tools import misc
_logger = logging.getLogger(__name__)

class EfundMandatHandler(models.AbstractModel):
    _name = 'efund.event.handler'

    @api.model
    def get_chart_account_data(self, company_id):
        file_path = 'efundOpc/data/fcp_plan_comptable.csv'
        accounts_to_create = []
        # On récupère l'objet société
        target_company = self.env['res.company'].browse(company_id)

        # On bascule l'environnement sur la société cible
        # Toutes les opérations à l'intérieur du "with" verront target_company comme active
        AccountObj = self.env['account.account'].with_company(target_company).sudo()

        try:
            # 1. Lecture complète et stockage en mémoire
            with (misc.file_open(file_path, mode='r') as f):
                reader = csv.DictReader(f, delimiter=';')

                for row in reader:
                    # Préparation des valeurs pour Odoo
                    # On s'assure que les colonnes existent dans le CSV
                    reconcile_raw = str(row.get('reconcile', '')).upper()
                    reconcile_bool = True if reconcile_raw == 'VRAI' else False
                    vals = {
                        'code': row.get('code'),
                        'name': row.get('name'),
                        'account_type': row.get('account_type'),
                        'code_store': f'"{company_id}": "{row.get('code')}"',
                        'reconcile': reconcile_bool,
                    }

                    # Validation simple : on n'ajoute que si le code et le nom sont là
                    if vals['code'] and vals['name']:
                        accounts_to_create.append(vals)

            # 2. Création massive dans la base de données

            if accounts_to_create:
                _logger.info("Début de la création de %s comptes pour le fonds.", len(accounts_to_create))

                # Option A : Création un par un (plus sûr pour isoler les erreurs)
                for acc_vals in accounts_to_create:
                    # Vérifier si le compte existe déjà pour éviter les crashs
                    # Correction de la recherche sur champ JSON
                    company_key = str(company_id)  # La clé JSON est souvent une chaîne de caractères
                    existing = self.env['account.account'].with_company(target_company).search([
                        ('code_store', 'like', f'"{company_key}": "{acc_vals["code"]}"')
                    ], limit=1)

                    if not existing:
                        # Création du plan comptable
                        AccountObj.create(acc_vals)
                        # self.env['account.account'].sudo().create(acc_vals)

                        # Création des journaux comptables
                        journals = [
                            ('Souscriptions investisseurs', 'SUB', 'general'),
                            ('Rachats investisseurs', 'RED', 'general'),
                            ('Banque', 'BNK', 'bank'),
                            ('Opérations sur titres', 'SEC', 'general'),
                            ('Valorisation / Valeur liquidative', 'NAV', 'general'),
                            ('Frais', 'EXP', 'general'),
                        ]

                        journal_data = []
                        for name, code, jtype in journals:
                            vals = {
                                'name': name,
                                'code': code,
                                'type': jtype,
                                'company_id': company_id
                            }
                            journal_data.append(vals)

                        JournalObj = self.env['account.journal'].with_company(target_company).sudo()
                        for j_vals in journal_data:
                            existing_journal = self.env['account.journal'].with_company(target_company).search([
                                ('code', '=', j_vals['code']),
                                ('company_id', '=', j_vals['company_id'])
                            ], limit=1)

                            if not existing_journal:
                                JournalObj.create(j_vals)
                            else:
                                _logger.warning("Le journal comptable %s existe déjà, passage au suivant.",
                                                j_vals['code'])

                        # Création des groupes de comptes
                        # self.create_account_groups(company_id)




                    else:
                        _logger.warning("Le compte %s existe déjà, passage au suivant.", acc_vals['code'])

                _logger.info("Importation terminée avec succès.")
            else:
                _logger.warning("Le fichier CSV est vide ou mal formaté.")

        except Exception as e:
            # On log l'erreur et on informe l'utilisateur
            _logger.error("Erreur critique lors de l'import : %s", str(e))
            raise UserError(f"Impossible d'importer le plan comptable : {str(e)}")

    @api.model
    def on_vehicule_created(self, vehicule):
        """
        Déclenché à la création/validation du mandat.
        Crée le compte analytique sous la compagnie 'MANDATS'.
        """
        # 1. Récupérer la compagnie 'MANDATS'
        if vehicule.company_id:
            company_mandats = vehicule.company_id
        else:
            company_mandats = self.env['res.company'].search([('company_code', '=', 'MANDATS')], limit=1)

        if not company_mandats:
            raise UserError(_("La compagnie 'MANDATS' n'a pas été trouvée. Veuillez la créer."))

        # 2. Récupérer ou créer le Plan Analytique parent
        if vehicule.company_id:
            plan = self.env['account.analytic.plan'].sudo().with_company(company_mandats).search(
                [('name', '=', 'Gestion Fond')], limit=1)
            if not plan:
                plan = self.env['account.analytic.plan'].sudo().with_company(company_mandats).create({
                    'name': 'Gestion Fond',
                })
        else:
            plan = self.env['account.analytic.plan'].sudo().with_company(company_mandats).search([('name', '=', 'Gestion sous Mandat')], limit=1)
            if not plan:
                plan = self.env['account.analytic.plan'].sudo().with_company(company_mandats).create({
                    'name': 'Gestion sous Mandat',
                })


        # 4. Création du Compte Analytique
        analytic_account = self.env['account.analytic.account'].sudo().with_company(company_mandats).search([
            ('code', '=', f"{vehicule.vehicule_code}"),
            ('company_id', '=', company_mandats.id)
        ], order='code desc', limit=1)

        if not analytic_account:
            analytic_account = self.env['account.analytic.account'].sudo().with_company(company_mandats).create({
            'name': f"Fond - {vehicule.name}" if vehicule.company_id else f"Mandat - {vehicule.name}",
            'code': vehicule.vehicule_code,
            'plan_id': plan.id,
            'company_id': company_mandats.id, })

        # 5. Lier le compte au record du mandat pour les futures écritures
        vehicule.write({'analytic_account_id': analytic_account.id})

    def generate_unique_bond_account(self, instrument_id, vehicule_id):
        """ Trouve le dernier compte 211xxx et crée le suivant """
        radical = "211"
        # 1. Rechercher le dernier compte créé commençant par 211
        company = vehicule_id.company_id
        last_account = self.env['account.account'].sudo().with_company(company).search([
            ('code', '=like', radical + '%')
        ], order='code desc', limit=1)

        # 2. Déterminer le nouveau numéro
        if last_account:
            # On extrait la partie numérique et on ajoute 1
            # Exemple: '211001' -> 211001 + 1 = 211002
            try:
                last_code = int(last_account.code)
                new_code = str(last_code + 1)
            except ValueError:
                new_code = radical + "001"
        else:
            # Premier compte de la série
            new_code = radical + "001"

        # 3. Création effective du compte dans le plan comptable Odoo
        return self.env['account.account'].create({
            'code': new_code,
            'name': _("Titre : %s") % instrument_id.name,
            'user_type_id': self.env.ref('account.data_account_type_non_current_assets').id,  # Type Actif Immobilisé
            'reconcile': True,
        })

