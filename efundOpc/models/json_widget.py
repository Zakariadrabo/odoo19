
from odoo import fields, models


class JsonWidget(fields.Field):
    """Widget personnalisé pour afficher du JSON formaté"""

    def _setup_regular_base(self, model):
        super()._setup_regular_base(model)
        self.widget = 'json_widget'

    # Dans le JavaScript (à créer dans un fichier js)
    # Un widget qui formatte le JSON avec coloration syntaxique