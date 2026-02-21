from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class FundClass(models.Model):
    _name = "efund.fund.share.class"
    _description = 'Classe de Parts'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = ' sequence, name'

    # === Fields ===
    name = fields.Char(string='Classe de Parts',required=True,help="Nom de la classe de parts (ex: 'Class A EUR Acc', 'Class I USD Dist')")
    sequence = fields.Integer(string='Sequence',default=10,help="Ordre d'affichage dans les listes")
    # === Relations ===
    vehicule_fund_id = fields.Many2one('efund.vehicule.fund', required=True, ondelete='cascade')

    # === Frais ===
    management_fee_rate = fields.Float(string='Frais de gestion (%)',digits=(6, 4), help="Frais de gestion annuels exprimés en pourcentage de l'actif")
    performance_fee_rate = fields.Float(string='Frais de performance (%)',digits=(6, 4),default=0.0,help="Frais de performance sur la plus-value")
    entry_load = fields.Float(string="Frais d'entrée (%)",digits=(16, 4),default=0.0)
    exit_load = fields.Float(string="Frais de sortie (%)",digits=(16, 4),default=0.0)

    # === Caractéristiques ===
    is_accumulating = fields.Boolean(string='Réinvestissement des dividendes',default=True,help="Si coché, les dividendes sont réinvestis automatiquement (Acc). Sinon, ils sont distribués (Dist).")
    minimum_subscription = fields.Float(string='Montant minimum de souscription initiale',help="Montant minimum de souscription initiale")
    minimum_additional_subscription = fields.Float(string='Montant minimum pour les souscriptions supplémentaires',help="Montant minimum pour les souscriptions supplémentaires")
    minimum_redemption = fields.Float(string='Montant minimum de rachat',help="Montant minimum de rachat")
    is_default = fields.Boolean(string="Classe par défaut",default=False)
    minimum_duration = fields.Integer(string="Durée minimun pour rachat (mois)")

    # === Statuts et Dates ===
    state = fields.Selection([('draft', 'Brouillon'),('validate', 'Validé'),('suspended', 'Suspendu'),('closed', 'Fermer aux nouveau investisseurs'),],string='Status',default='draft',)
    launch_date = fields.Date(string='Date de lancement',default=fields.Date.context_today)
    closure_date = fields.Date(string='Date de fermeture',help="Date de fermeture aux nouveaux investisseurs")

    # === Calculs et Statistiques ===
    total_shares = fields.Float(string='Total Shares Outstanding',digits=(16, 2),compute='_compute_share_statistics',store=True,help="Nombre total de parts en circulation")
    total_net_assets = fields.Float(string='Total Net Assets',compute='_compute_share_statistics',store=True,help="Actifs nets attribués à cette classe")
    current_nav = fields.Float(string='Valeur Liquidative',compute='_compute_current_nav',help="Dernière valeur liquidative disponible", store=True)

    # decomposition de la VL
    vl_capital_init = fields.Float(string="VL Capital (Début Période)", digits=(12, 4))
    vl_non_distribuable = fields.Float(string="VL Sommes Non Distrib.", digits=(12, 4))

    # revenu
    vl_res_anterieurs = fields.Float(string="VL Résult. Antérieurs", digits=(12, 4))
    vl_res_clos = fields.Float(string="VL Résult. Exercice Clos", digits=(12, 4))
    vl_res_en_cours = fields.Float(string="VL Résult. en Cours (ICNE)", digits=(12, 4))


    # === Computed Methods ===
    @api.depends('vehicule_fund_id')
    def _compute_share_statistics(self):
        """Calcule les statistiques de parts en circulation et actifs nets"""
        # Note: Cette méthode serait complétée avec la logique réelle de calcul
        for share_class in self:
            # Exemple de calcul - à adapter avec la logique métier réelle
            share_class.total_shares = 0.0
            share_class.total_net_assets = 0.0

    @api.depends('total_net_assets', 'total_shares')
    def _compute_current_nav(self):
        """Calcule la NAV actuelle"""
        for share_class in self:
            if share_class.total_shares > 0:
                share_class.current_nav = share_class.total_net_assets / share_class.total_shares
            else:
                share_class.current_nav = 11000 # A changer après le calcul de la VL

    # === Constraints ===
    @api.constrains('management_fee_rate', 'subscription_fee_rate', 'redemption_fee_rate', 'performance_fee_rate')
    def _check_fee_rates(self):
        """Vérifie que les taux de frais sont raisonnables"""
        for share_class in self:
            if share_class.management_fee_rate > 5.0:
                raise ValidationError(_("Les frais de gestion ne doivent pas dépassés 5%."))

            if share_class.entry_load > 10.0:
                raise ValidationError(_("Les frais de souscription ne doivent pas dépassés 10%."))

            if share_class.exit_load > 10.0:
                raise ValidationError(_("Les frais de rachat ne doivent pas dépassés 10%."))

            if share_class.performance_fee_rate > 50.0:
                raise ValidationError(_("Les frais de performance ne doivent pas dépassés 50%."))

    @api.constrains('minimum_subscription', 'minimum_additional_subscription', 'minimum_redemption')
    def _check_minimum_amounts(self):
        """Vérifie la cohérence des montants minimums"""
        for share_class in self:
            if (share_class.minimum_additional_subscription and
                    share_class.minimum_subscription and
                    share_class.minimum_additional_subscription > share_class.minimum_subscription):
                raise ValidationError(
                    _("La souscription minimale additionnelle ne peut pas être supérieur à la souscription minimale initiale."))

    # === Actions ===
    def action_activate(self):
        """Active la classe de parts"""
        self.write({'state': 'active'})

    def action_suspend(self):
        """Suspend la classe de parts"""
        self.write({'state': 'suspended'})

    def action_close(self):
        """Ferme la classe de parts aux nouveaux investisseurs"""
        self.write({
            'state': 'closed',
            'closure_date': fields.Date.context_today(self)
        })

    def action_reopen(self):
        """Rouvre la classe de parts"""
        self.write({
            'state': 'active',
            'closure_date': False
        })



    def action_view_nav_history(self):
        """Affiche l'historique NAV de cette classe de parts"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'NAV History - {self.name}',
            'res_model': 'fund.nav',
            'view_mode': 'list,form,graph',
            'domain': [('share_class_id', '=', self.id)],
            'context': {
                'default_share_class_id': self.id,
                'search_default_share_class_id': self.id,
                'graph_group_by': ['nav_date'],
            }
        }

    @api.constrains(
        'management_fee_rate',
        'entry_load',
        'exit_load'
    )
    def _check_fee_rates(self):
        for rec in self:
            for rate in [
                rec.management_fee_rate,
                rec.entry_load,
                rec.exit_load
            ]:
                if rate < 0 or rate > 100:
                    raise ValidationError(
                        "Les taux de frais doivent être compris entre 0 et 100 %."
                    )

