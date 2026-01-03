from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

class FundClass(models.Model):
    _name = "efund.fund.class"
    _description = 'Fund Share Class'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'fund_id, sequence, name'

    # === Fields ===
    name = fields.Char(string='Share Class Name',required=True,help="Nom de la classe de parts (ex: 'Class A EUR Acc', 'Class I USD Dist')")

    sequence = fields.Integer(string='Sequence',default=10,help="Ordre d'affichage dans les listes")

    # === Relations ===
    fund_id = fields.Many2one('efund.fund',string='Fund',required=True,ondelete='cascade' )

    # === Structure de Frais ===
    fee_structure = fields.Selection([
        ('front_end', 'Front-End Load'),
        ('back_end', 'Back-End Load'),
        ('level', 'Level Load'),
        ('none', 'No Load'),
    ],
        string='Fee Structure',
        default='front_end',
        required=True,
        help="Structure des frais de souscription/rachat"
    )

    # === Frais ===
    management_fee_rate = fields.Float(string='Management Fee Rate (%)',digits=(6, 4),default=1.5,help="Frais de gestion annuels exprimés en pourcentage de l'actif")
    subscription_fee_rate = fields.Float(string='Subscription Fee Rate (%)',digits=(6, 4),default=0.0,help="Frais de souscription (entrée) en pourcentage")
    redemption_fee_rate = fields.Float(string='Redemption Fee Rate (%)',digits=(6, 4),default=0.0,help="Frais de rachat (sortie) en pourcentage")
    performance_fee_rate = fields.Float(string='Performance Fee Rate (%)',digits=(6, 4), default=0.0,help="Frais de performance sur la plus-value")

    # === Caractéristiques ===
    is_accumulating = fields.Boolean(string='Accumulating Shares',default=True,help="Si coché, les dividendes sont réinvestis automatiquement (Acc). Sinon, ils sont distribués (Dist).")
    minimum_subscription = fields.Float(string='Minimum Subscription Amount',help="Montant minimum de souscription initiale")
    minimum_additional_subscription = fields.Float(string='Minimum Additional Subscription',help="Montant minimum pour les souscriptions supplémentaires")
    minimum_redemption = fields.Float(string='Minimum Redemption Amount',help="Montant minimum de rachat")

    # === Statuts et Dates ===
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('closed', 'Closed to New Investors'),
    ],
        string='Status',
        default='draft',)

    launch_date = fields.Date(string='Launch Date',default=fields.Date.context_today)
    closure_date = fields.Date(string='Closure Date',help="Date de fermeture aux nouveaux investisseurs" )

    # === Calculs et Statistiques ===
    total_shares = fields.Float(string='Total Shares Outstanding',digits=(16, 2),compute='_compute_share_statistics',store=True,help="Nombre total de parts en circulation")
    total_net_assets = fields.Float(string='Total Net Assets',compute='_compute_share_statistics',store=True,help="Actifs nets attribués à cette classe")
    current_nav = fields.Float(string='Current NAV per Share',compute='_compute_current_nav',help="Dernière valeur liquidative disponible")


    # === Computed Methods ===
    @api.depends('fund_id')
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
                share_class.current_nav = 0.0

    # === Constraints ===
    @api.constrains('management_fee_rate', 'subscription_fee_rate', 'redemption_fee_rate', 'performance_fee_rate')
    def _check_fee_rates(self):
        """Vérifie que les taux de frais sont raisonnables"""
        for share_class in self:
            if share_class.management_fee_rate > 5.0:
                raise ValidationError(_("Management fee rate cannot exceed 5%."))

            if share_class.subscription_fee_rate > 10.0:
                raise ValidationError(_("Subscription fee rate cannot exceed 10%."))

            if share_class.redemption_fee_rate > 10.0:
                raise ValidationError(_("Redemption fee rate cannot exceed 10%."))

            if share_class.performance_fee_rate > 50.0:
                raise ValidationError(_("Performance fee rate cannot exceed 50%."))

    @api.constrains('minimum_subscription', 'minimum_additional_subscription', 'minimum_redemption')
    def _check_minimum_amounts(self):
        """Vérifie la cohérence des montants minimums"""
        for share_class in self:
            if (share_class.minimum_additional_subscription and
                    share_class.minimum_subscription and
                    share_class.minimum_additional_subscription > share_class.minimum_subscription):
                raise ValidationError(
                    _("Minimum additional subscription cannot be greater than initial minimum subscription."))

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

    def action_view_transactions(self):
        """Affiche les transactions de cette classe de parts"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Transactions - {self.name}',
            'res_model': 'fund.transaction',
            'view_mode': 'tree,form',
            'domain': [('share_class_id', '=', self.id)],
            'context': {
                'default_share_class_id': self.id,
                'search_default_share_class_id': self.id
            }
        }

    def action_view_nav_history(self):
        """Affiche l'historique NAV de cette classe de parts"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'NAV History - {self.name}',
            'res_model': 'fund.nav',
            'view_mode': 'tree,form,graph',
            'domain': [('share_class_id', '=', self.id)],
            'context': {
                'default_share_class_id': self.id,
                'search_default_share_class_id': self.id,
                'graph_group_by': ['nav_date'],
            }
        }



"""
    name = fields.Char(required=True)
    fund_id = fields.Many2one('res.company', domain="[('company_type','=','fonds')]", required=True)
    currency_id = fields.Many2one('res.currency')
    shares_outstanding = fields.Float(default=0.0)
    """

