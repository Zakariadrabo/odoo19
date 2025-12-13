from odoo import models, api

class IrUiMenu(models.Model):
    _inherit = "ir.ui.menu"

    @api.model
    def load_menus(self, debug=False):
        menus = super().load_menus(debug)

        company = self.env.company  # société active
        user = self.env.user

        # si l'utilisateur n'est pas OPCVM → masquer tout le module
        if not user.has_group("efundOpc.group_opc_manager"):
            self._hide_menu(menus, "menu_fund_management_root")
            return menus

        # Cas Société de gestion : accès total
        if company.is_management_company:
            return menus

        # Cas Fonds : masquer menus inutiles
        if company.is_fund:
            self._hide_menu(menus, "menu_management_company_root")
            self._hide_menu(menus, "menu_clients_root")
            self._hide_menu(menus, "menu_operations_root")
            self._hide_menu(menus, "menu_accounting_root")

        return menus

    def _hide_menu(self, menus, xmlid):
        """Masque un menu par son XMLID."""
        try:
            menu_id = self.env.ref(f"efundOpc.{xmlid}").id
        except:
            return  # si le menu n'existe pas encore

        if menu_id in menus.get('parents', []):
            menus['parents'].pop(menu_id, None)
        if menu_id in menus.get('children', []):
            menus['children'].pop(menu_id, None)
        if menu_id in menus:
            menus.pop(menu_id, None)
