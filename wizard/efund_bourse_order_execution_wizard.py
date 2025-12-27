from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


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
    reference = fields.Char(
        string="Référence SGI / Marché"
    )

    # ----------------------------------------------------
    # Contraintes
    # ----------------------------------------------------
    @api.constrains('executed_quantity')
    def _check_executed_quantity_depend(self):
        for rec in self:
            if rec.executed_quantity > rec.remaining_quantity:
                raise ValidationError(
                    _("la quantité exécutée ne peut pas être supérieure à la quantité restante."))

    # ----------------------------------------------------
    # VALIDATION
    # ----------------------------------------------------
    def action_confirm_execution(self):
        self.ensure_one()
        self.order_id.action_finalize_execution({
            'execution_date': self.execution_date,
            'quantity': self.executed_quantity,
            'price': self.execution_price,
            'reference': self.reference,
        })
        return {'type': 'ir.actions.act_window_close'}


