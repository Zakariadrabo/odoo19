from odoo import models, fields, _
from odoo.exceptions import UserError


class ConfirmActionWizard(models.TransientModel):
    _name = 'efund.confirm.action.wizard'
    _description = 'Wizard générique de confirmation'

    res_model = fields.Char(readonly=True)
    res_id = fields.Integer(readonly=True)
    method_name = fields.Char(readonly=True)

    message = fields.Text(
        string="Confirmation",
        readonly=True
    )

    def action_confirm(self):
        self.ensure_one()

        if not self.res_model or not self.method_name:
            raise UserError(_("Action non définie."))

        record = self.env[self.res_model].browse(self.res_id)

        if not hasattr(record, self.method_name):
            raise UserError(_("Méthode %s introuvable.") % self.method_name)

        # 🔥 appel dynamique
        getattr(record, self.method_name)()

        return {'type': 'ir.actions.act_window_close'}

    def action_cancel(self):
        return {'type': 'ir.actions.act_window_close'}
