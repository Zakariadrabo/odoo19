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
            ('event_type_id', '=', event.event_type_id.id),
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

                # On utilise la méthode de mapping chronologique

                target_account = self.env["efund.service"].get_or_create_accounting_mapping(instrument ,event.vehicule_id )

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


        # target_company = event.vehicule_id.company_id
        target_company = self.env['res.company'].search([('id', '=', idcompany_id.id)], limit=1)

        #log info schema utilisé
        _logger.info(f"***** Schéma comptable : {lines}")

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


