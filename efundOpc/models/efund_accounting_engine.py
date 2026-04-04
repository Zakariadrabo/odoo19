import logging

from odoo import models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class FundAccountingEngine(models.AbstractModel):
    _name = "efund.accounting.engine"
    _description = "Engine for generating accounting entries for fund operations"

    def _resolve_amount(self, event, amount_type):
        amount = event.payload.get(amount_type)
        if amount is None:
            return 0
        return amount

    def process_event(self, event):
        if event.state != 'draft':
            return event.move_id

        # Verification si mandat ou fond (company_id = null)
        analytic_account = event.vehicule_id.analytic_account_id
        company_mandats = self.env['res.company'].sudo().search([('company_code', '=', 'MANDATS')], limit=1)

        if not event.vehicule_id.company_id:
            idcompany_id = company_mandats
        else:
            idcompany_id = event.vehicule_id.company_id

        schema = self.env['efund.accounting.schema'].search([
            ('event_type_id', '=', event.event_type_id),
            ('company_id', '=', idcompany_id.id),
            # ('active', '=', True)
        ], limit=1)

        if not schema:
            raise UserError(_("Aucun schema pour %s") % event.event_type_id)

        lines = []

        for rule in schema.line_ids:
            amount = self._resolve_amount(event, rule.amount_type)

            if not amount:
                continue
            # Logique de filtrage par signe
            if rule.account_selection_type == 'if_positive' and amount <= 0:
                continue
            if rule.account_selection_type == 'if_negative' and amount >= 0:
                continue

            amount = abs(amount)
            if amount == 0: continue

            # Construction de la distribution analytique (Format Odoo 19)
            # On ne l'applique que si la règle le demande ET que le mandat a un compte
            analytic_distribution = {}
            if rule.use_analytic and analytic_account:
                analytic_distribution = {str(analytic_account.id): 100.0}

            # RÉSOLUTIONS DYNAMIQUE DU COMPTE
            target_account = False

            if rule.account_resolution_type == 'fixed':
                target_account = rule.account_id

            elif rule.account_resolution_type == 'instrument':

                # RÉSOLUTION : On va chercher dans le dictionnaire payload
                instrument_id = event.payload.get('instrument_id')

                if not instrument_id:
                    raise UserError(_("L'ID de l'instrument est manquant dans le payload de l'événement."))

                # On récupère l'objet instrument pour appeler sa méthode de mapping
                instrument = self.env['efund.vehicule.instrument.core'].browse(instrument_id)
                _logger.info(f"**************** Instrument: {instrument.name}")

                # On utilise la méthode de mapping chronologique
                target_account = instrument.get_or_create_accounting_mapping(idcompany_id)

            elif rule.account_resolution_type == 'liquidity':
                # On récupère le compte de trésorerie lié au fonds/véhicule
                target_account = event.vehicule_id.cash_account_id

            if not target_account:
                raise UserError(_("Impossible de déterminer le compte pour la ligne") )

            lines.append((0, 0, {
                'account_id': target_account.id,
                'name': rule.label or event.reference,
                'debit': amount if rule.side == 'debit' else 0,
                'credit': amount if rule.side == 'credit' else 0,
                'currency_id': event.vehicule_id.company_id.currency_id.id if event.vehicule_id.company_id else company_mandats.currency_id.id,
                # Injection de la dimension analytique
                'analytic_distribution': analytic_distribution if analytic_distribution else False,
            }))

        # raise UserError(f"lines = {lines}")
        # target_company = event.vehicule_id.company_id
        target_company = self.env['res.company'].search([('id', '=', idcompany_id.id)], limit=1)

        _logger.info(f"**************** Company: {lines}")

        move = self.env['account.move'].sudo().with_company(target_company).create({
            'journal_id': schema.journal_id.id,
            'company_id': idcompany_id.id,
            'ref': event.reference,
            'line_ids': lines,
            'currency_id': event.vehicule_id.company_id.currency_id.id if event.vehicule_id.company_id else company_mandats.currency_id.id,
        })

        move.action_post()

        event.write({
            'state': 'processed',
            'move_id': move.id
        })

        return move

    """
    def generate_account_move(self, fund, operation_type, data_map, ref=None):
        # data_map serait un dictionnaire : {'gross': 1000, 'fees': 20, 'net': 980}

        schema = self.env['efund.accounting.schema'].search([
            ('operation_type', '=', operation_type),
            ('company_id', '=', fund.company_id.id)
        ], limit=1)

        move_lines = []
        for rule in schema.line_ids.sorted('sequence'):
            # On récupère le montant spécifique selon le type défini dans la règle
            line_amount = data_map.get(rule.amount_type, 0.0)

            if line_amount == 0: continue  # Optionnel : éviter les lignes à zéro

            move_lines.append((0, 0, {
                'account_id': rule.account_id.id,
                'name': ref or schema.operation_type,
                'debit': line_amount if rule.side == 'debit' else 0,
                'credit': line_amount if rule.side == 'credit' else 0,
            }))

        move = self.env['account.move'].create({
            'journal_id': schema.journal_id.id,
            'company_id': fund.company_id.id,
            'ref': ref,
            'line_ids': move_lines
        })

        move.action_post()

        return move

    def process_pending_events(self, limit=100):

        events = self.env['efund.accounting.event'].search([
            ('processed', '=', False),
            ('state', '=', 'pending')
        ], limit=limit)

        for event in events:
            try:
                self.process_event(event)
            except Exception as e:
                event.state = 'failed'

    def generate_account_move(self, fund, operation_type, amount, ref=None):

        schema = self.env['efund.accounting.schema'].search([
            ('operation_type','=',operation_type),
            ('company_id','=',fund.company_id.id)
        ], limit=1)

        if not schema:
            raise UserError(
                _("Aucun schéma comptable pour %s") % operation_type
            )

        move_lines = []

        for rule in schema.line_ids.sorted('sequence'):

            move_lines.append((0,0,{
                'account_id': rule.account_id.id,
                'name': ref or operation_type,
                'debit': amount if rule.side == 'debit' else 0,
                'credit': amount if rule.side == 'credit' else 0,
            }))

        move = self.env['account.move'].create({
            'journal_id': schema.journal_id.id,
            'company_id': fund.company_id.id,
            'ref': ref,
            'line_ids': move_lines
        })

        move.action_post()

        return move
        
       
    # Supposons que 'self' est un enregistrement de modèle Odoo
    # et que 'env' est l'environnement Odoo (self.env)

    # --- Définir la compagnie cible ---
    # Vous devez d'abord identifier la compagnie pour laquelle vous voulez créer l'écriture.
    # Cela peut venir d'un paramètre, d'un champ sur le modèle courant, etc.
    target_company = self.env['res.company'].search([('name', '=', 'Ma Compagnie France')], limit=1)
    if not target_company:
        raise ValueError("La compagnie cible 'Ma Compagnie France' n'a pas été trouvée.")

    # Utiliser with_context pour toutes les opérations liées à cette compagnie
    # C'est la méthode la plus robuste pour gérer la multi-compagnie.
    env_for_company = self.env(company=target_company.id)

    # 1. Récupérer ou créer les comptes et balises analytiques
    #    Il est important de les créer ou les rechercher dans le contexte de la compagnie cible
    #    si vous voulez qu'ils soient spécifiques à cette compagnie.
    #    Si company_id est vide sur l'analytique, il est global.

    # Exemple de récupération d'un compte analytique par son nom pour la compagnie cible
    analytic_account_project_a = env_for_company['account.analytic.account'].search([
        ('name', '=', 'Projet A'),
        ('company_id', 'in', [False, target_company.id])  # Recherche globale ou spécifique à la compagnie
    ], limit=1)
    if not analytic_account_project_a:
        analytic_account_project_a = env_for_company['account.analytic.account'].create({
            'name': 'Projet A',
            'company_id': target_company.id  # Associer le compte analytique à la compagnie
        })
        print(f"Compte analytique 'Projet A' créé pour {target_company.name} avec ID: {analytic_account_project_a.id}")
    else:
        print(
            f"Compte analytique 'Projet A' trouvé pour {target_company.name} avec ID: {analytic_account_project_a.id}")

    # Exemple de récupération ou création d'une balise analytique pour la compagnie cible
    analytic_tag_marketing = env_for_company['account.analytic.tag'].search([
        ('name', '=', 'Marketing'),
        ('company_id', 'in', [False, target_company.id])  # Recherche globale ou spécifique à la compagnie
    ], limit=1)
    if not analytic_tag_marketing:
        analytic_tag_marketing = env_for_company['account.analytic.tag'].create({
            'name': 'Marketing',
            'company_id': target_company.id  # Associer la balise analytique à la compagnie
        })
        print(f"Balise analytique 'Marketing' créée pour {target_company.name} avec ID: {analytic_tag_marketing.id}")
    else:
        print(f"Balise analytique 'Marketing' trouvée pour {target_company.name} avec ID: {analytic_tag_marketing.id}")

    # 2. Récupérer les comptes généraux nécessaires
    #    Les comptes généraux sont toujours spécifiques à une compagnie.
    account_debit = env_for_company['account.account'].search([('code', '=', '600000')], limit=1)
    account_credit = env_for_company['account.account'].search([('code', '=', '401000')], limit=1)

    if not account_debit or not account_credit:
        raise ValueError(
            f"Les comptes généraux de débit ou de crédit n'ont pas été trouvés pour la compagnie {target_company.name}.")

    # 3. Créer l'écriture comptable (account.move)
    #    Le journal doit aussi être spécifique à la compagnie.
    journal = env_for_company['account.journal'].search([('type', '=', 'purchase')], limit=1)
    if not journal:
        raise ValueError(f"Aucun journal d'achat trouvé pour la compagnie {target_company.name}.")

    move_vals = {
        'ref': 'Facture Fournisseur #2026-001',
        'date': '2026-03-11',
        'journal_id': journal.id,
        'move_type': 'in_invoice',
        'company_id': target_company.id,  # Spécifier explicitement la compagnie pour l'écriture
    }
    move = env_for_company['account.move'].create(move_vals)
    print(f"Écriture comptable créée pour {target_company.name} avec ID: {move.id}")

    # 4. Créer les lignes de l'écriture comptable (account.move.line)
    #    Les lignes héritent du company_id de l'écriture parente, mais il est bon de s'assurer
    #    que les objets liés (comptes analytiques, balises) sont compatibles avec cette compagnie.

    # Ligne de débit
    debit_line_vals = {
        'move_id': move.id,
        'account_id': account_debit.id,
        'name': 'Achat de fournitures pour Projet A',
        'debit': 100.00,
        'credit': 0.0,
        'analytic_account_id': analytic_account_project_a.id,
        'analytic_tag_ids': [(6, 0, [analytic_tag_marketing.id])],
        # 'company_id': target_company.id, # Pas nécessaire ici, hérité de move_id
    }
    env_for_company['account.move.line'].create(debit_line_vals)

    # Ligne de crédit
    credit_line_vals = {
        'move_id': move.id,
        'account_id': account_credit.id,
        'name': 'Facture Fournisseur #2026-001',
        'debit': 0.0,
        'credit': 100.00,
        # 'company_id': target_company.id, # Pas nécessaire ici, hérité de move_id
    }
    env_for_company['account.move.line'].create(credit_line_vals)

    # 5. Valider l'écriture comptable
    move.action_post()
    print(f"Écriture comptable {move.name} validée pour {target_company.name}.")
    
     """
