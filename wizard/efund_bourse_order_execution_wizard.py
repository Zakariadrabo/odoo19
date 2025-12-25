from odoo import models, fields, api, _
from odoo.exceptions import UserError


class EfundBourseOrderExecutionWizard(models.TransientModel):
    _name = 'efund.bourse.order.execution.wizard'
    _description = 'Execution of Bourse Order'

    order_id = fields.Many2one(
        'efund.bourse.order',
        string="Ordre de bourse",
        required=True,
        readonly=True
    )

    executed_quantity = fields.Float(
        string="Quantité exécutée",
        required=True
    )

    execution_price = fields.Float(
        string="Cours d'exécution",
        required=True
    )

    execution_date = fields.Date(
        string="Date d'exécution",
        default=fields.Date.context_today,
        required=True
    )

    remaining_quantity = fields.Float(
        string="Quantité restante",
        readonly=True
    )

    # ----------------------------------------------------
    # VALIDATION
    # ----------------------------------------------------
    def action_confirm_execution(self):
        self.ensure_one()
        order = self.order_id

        # 1) Mise à jour ordre
        order.executed_quantity += self.executed_quantity
        order.executed_price = self.executed_price

        if order.executed_quantity < order.quantity:
            order.state = 'partially_executed'
        else:
            order.state = 'executed'

        # 2) Création / mise à jour position
        order._update_fund_position(
            qty=self.executed_quantity,
            price=self.executed_price
        )

        # 3) Écriture comptable
        order._create_accounting_entry(
            qty=self.executed_quantity,
            price=self.executed_price
        )

        return {'type': 'ir.actions.act_window_close'}

    def _update_fund_position(self, qty, price):
        position = self.env['efund.fund.position'].search([
            ('fund_id', '=', self.fund_id.id),
            ('instrument_id', '=', self.instrument_id.id)
        ], limit=1)

        if not position:
            self.env['efund.fund.position'].create({
                'fund_id': self.fund_id.id,
                'instrument_id': self.instrument_id.id,
                'quantity': qty,
                'avg_cost': price,
                'valuation_date': fields.Date.today(),
            })
        else:
            total_qty = position.quantity + qty
            new_avg = ((position.quantity * position.avg_cost) + (qty * price)) / total_qty
            position.write({
                'quantity': total_qty,
                'avg_cost': new_avg,
                'valuation_date': fields.Date.today(),
            })

