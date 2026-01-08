from odoo import models, _


class ConfirmableActionMixin(models.AbstractModel):
    _name = 'efund.confirmable.mixin'
    _description = 'Mixin action confirmable'

    def _open_confirmation_wizard(self, message, method_name):
        self.ensure_one()

        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirmation'),
            'res_model': 'efund.confirm.action.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_res_model': self._name,
                'default_res_id': self.id,
                'default_method_name': method_name,
                'default_message': message,
            }
        }
