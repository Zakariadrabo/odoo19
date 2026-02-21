from odoo import models, _
from odoo.exceptions import UserError

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

        schema = self.env['efund.accounting.schema'].search([
            ('event_type', '=', event.event_type),
            ('company_id', '=', event.vehicule_id.company_id.id),
           #('active', '=', True)
        ], limit=1)

        if not schema:
            raise UserError(
                _("Aucun schema pour %s") % event.event_code
            )

        lines = []

        for rule in schema.line_ids:
            amount = self._resolve_amount(event,rule.amount_type)

            if not amount:
                continue
            # Logique de filtrage par signe
            if rule.account_selection_type == 'if_positive' and amount <= 0:
                continue
            if rule.account_selection_type == 'if_negative' and amount >= 0:
                continue

            amount = abs(amount)
            if amount == 0: continue

            lines.append((0, 0, {
                'account_id': rule.account_id.id,
                'name': rule.label or event.reference,
                'debit': amount if rule.side == 'debit' else 0,
                'credit': amount if rule.side == 'credit' else 0,
            }))

        #raise UserError(f"lines = {lines}")
        move = self.env['account.move'].create({
            'journal_id': schema.journal_id.id,
            'company_id': event.vehicule_id.company_id.id,
            'ref': event.reference,
            'line_ids': lines
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
        
        """
