import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
_logger = logging.getLogger(__name__)

class FundAccountingSchema(models.Model):
    _name = "efund.accounting.schema.new"
    _description = "Mapping comptable des fonds"

    _rec_name = "name"

    name = fields.Char(string="Nom", required=True)

    event_type_id = fields.Many2one('efund.event.type.new', string="Type d'Événement", required=True)
    journal_code = fields.Selection([('BNK','Banque'),('SUB','Souscriptions investisseurs'),('RED','Rachats investisseurs'),('SEC','Opérations sur titres'),('NAV','Valorisation / Valeur liquidative'),('EXP','Frais'),])
    active = fields.Boolean(default=True)
    line_ids = fields.One2many('efund.accounting.schema.line.new', 'schema_id', string="Lignes comptables")


    @api.onchange('company_id')
    def _onchange_company_id(self):
        """
        Met à jour le domaine du journal et sélectionne automatiquement
        le premier journal disponible pour la société choisie.
        """
        # 1. Réinitialisation si aucune société n'est sélectionnée
        if not self.company_id:
            self.journal_id = False
            return {'domain': {'journal_id': []}}

        # 2. Préparation de l'environnement de recherche
        # On utilise sudo() pour ignorer les Record Rules et with_company pour le contexte
        # active_test=False permet de voir même les journaux archivés si besoin
        target_company = self.company_id
        JournalObj = self.env['account.journal'].sudo().with_company(target_company)

        # 3. Recherche des journaux appartenant à cette société
        # On peut filtrer par type (ex: 'general') si nécessaire
        journals = JournalObj.search([
            ('company_id', '=', target_company.id),
        ])

        _logger.info(f"Recherche journaux pour {target_company.name} : {len(journals)} trouvés.")

        if journals:
            # 4. On remplit le champ avec le premier journal trouvé
            self.journal_id = journals[0]

            # 5. On renvoie le domaine filtré pour que l'utilisateur puisse changer si besoin
            return {
                'domain': {
                    'journal_id': [('id', 'in', journals.ids)]
                }
            }
        else:
            # Si aucun journal n'existe pour cette société
            self.journal_id = False
            return {
                'warning': {
                    'title': _("Attention"),
                    'message': _("Aucun journal comptable n'a été trouvé pour la société %s. "
                                 "Veuillez en créer un avant de continuer.") % target_company.name
                },
                'domain': {'journal_id': [('id', '=', False)]}
            }

    @api.constrains('company_id', 'journal_id')
    def _check_company_journal_consistency(self):
        for record in self:
            if record.journal_id and record.journal_id.company_id != record.company_id:
                raise ValidationError("Le journal doit appartenir à la société sélectionnée.")
