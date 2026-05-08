import logging

from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
_logger = logging.getLogger(__name__)

class EfundNavSession(models.Model):
    _name = 'efund.nav.session'
    _description = 'Séance de calcul de la VL'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = "valuation_date desc"

    name = fields.Char(string="Référence", default='/')
    fund_id = fields.Many2one('efund.vehicule.fund', string="Fonds", required=True)
    valuation_date = fields.Date(string="Date de VL", required=True, )

    # Résultats globaux
    total_assets = fields.Monetary(string="Total Actif", compute="_compute_nav", store=True,)
    total_liabilities = fields.Monetary(string="Total Passif", compute="_compute_nav", store=True,)
    net_asset_value = fields.Monetary(string="Actif Net", compute="_compute_nav", store=True,)

    nb_parts = fields.Float(string="Nombre de parts",compute='_compute_nb_parts', store=True, digits=(16, 4), readonly=False, )
    unit_nav = fields.Float(string="Valeur Liquidative",)

    # Deflacation
    capital = fields.Float(string="Capital", digits=(18, 10))
    non_distributable_sum = fields.Float(string="Somme non distribuables", digits=(18, 10))
    previous_fiscal_year_result = fields.Float(string="Résultat exercice antérieur", digits=(18, 10))
    closed_fiscal_year_result = fields.Float(string="Résultat exercice clos", digits=(18, 10))
    current_fiscal_year_result = fields.Float(string="Résultat exercice en cours", digits=(18, 10))

    currency_id = fields.Many2one(related='fund_id.currency_id')
    state = fields.Selection([('draft', 'Brouillon'),('verify','Vérifié'), ('validated', 'Validé')], default='draft')
    line_ids = fields.One2many('efund.nav.line', 'session_id', string="Détails de l'Inventaire")
    fiscal_year_id = fields.Many2one('efund.fiscal.year',string="Exercice Fiscal", compute="_compute_fiscal_year", store=True)

    # Récupération des données de performances
    PerformanceHebdomadaire = fields.Float(string="Performance Hebdomadaire")
    PerformanceMensuelle = fields.Float(string="Performance Mensuelle")
    PerformanceAnnuelle = fields.Float(string="Performance Annuelle")
    PerformanceOrigine = fields.Float(string="Performance Origine")
    event_reset_id = fields.Many2one('efund.accounting.event', string="Événement", readonly=True)
    event_frais_id = fields.Many2one('efund.accounting.event', string="Événement", readonly=True)

    @api.depends('fund_id', 'valuation_date')
    def _compute_nb_parts(self):
        for rec in self:
            if rec.fund_id and rec.valuation_date:
                nbpart = self.env['efund.service'].get_total_shares_at_date(rec.fund_id.vehicule_id, rec.valuation_date,)
                rec.nb_parts = nbpart


    @api.depends('valuation_date', 'fund_id')
    def _compute_fiscal_year(self):
        for nav in self:
            # Recherche automatique de l'exercice correspondant à la date de la VL
            fy = self.env['efund.fiscal.year'].search([
                ('date_start', '<=', nav.valuation_date),
                ('date_end', '>=', nav.valuation_date),

            ], limit=1)
            nav.fiscal_year_id = fy

    @api.depends('line_ids', 'nb_parts')
    def _compute_nav(self):
        for rec in self:
            if rec.nb_parts and rec.nb_parts != 0:
                assets = sum(rec.line_ids.filtered(lambda l: l.type == 'asset').mapped('total_amount'))
                liabilities = sum(rec.line_ids.filtered(lambda l: l.type == 'liability').mapped('total_amount'))
                _logger.info(f"***** compute nav {rec.id} et {rec.line_ids} actif {assets} et passif {liabilities}")
                rec.total_assets = assets
                rec.total_liabilities = liabilities
                rec.net_asset_value = assets - liabilities



    def action_generate_lines(self):
        self.ensure_one()
        # Nettoyage des anciennes lignes si on recalcule
        self.line_ids.unlink()

        lines_vals = []

        # --- 1. VALORISATION DES TITRES (Actif) ---
        # On récupère les positions du fonds (en supposant un champ position_ids sur le fonds)
        for pos in self.fund_id.position_ids:
            # On récupère le dernier prix (votre méthode existante)
            # La valorisation = (Quantité * Prix) + Coupons Courus
            total_valuation = pos.market_value + pos.accrued_interest

            lines_vals.append((0, 0, {
                'name': f"Titre : {pos.instrument_id.name}",
                'type': 'asset',
                'amount': total_valuation,
                'session_id': self.id
            }))

        # --- 2. RÉCUPÉRATION DU CASH (Actif) ---
        # On interroge la balance du compte 121001 pour ce mandat/fond
        cash_balance = self.env['account.analytic.account'].browse(
            self.fund_id.analytic_account_id.id)._compute_account_balance('121001')

        lines_vals.append((0, 0, {
            'name': "Liquidités (Compte 121001)",
            'type': 'asset',
            'amount': cash_balance,
            'session_id': self.id
        }))

        # --- 3. PROVISION DES FRAIS DE GESTION (Passif) ---
        # Exemple de calcul simplifié : (Actif Brut * Taux / 365)
        gross_assets = sum(l[2]['amount'] for l in lines_vals if l[2]['type'] == 'asset')
        daily_fees = (gross_assets * (self.fund_id.management_fee_rate / 100)) / 365

        lines_vals.append((0, 0, {
            'name': "Provision Frais de Gestion (Journalier)",
            'type': 'liability',
            'amount': daily_fees,
            'session_id': self.id
        }))

        # --- 4. RÉCUPÉRATION DU NOMBRE DE PARTS ---
        # On peut soit le lire sur un champ du fonds, soit via le compte 371100
        # Ici on suppose un champ technique qui suit les parts
        self.nb_parts = self.fund_id.total_shares_count

        self.write({'line_ids': lines_vals})
        return True

    def action_compute_nav_lines(self):
        for rec in self:
            # 1. Nettoyage de l'ancien inventaire
            rec.line_ids.unlink()

            lines_vals = []

            # Valorisation du Portefeuille (Titres)
            # On utilise le service centralisé pour chaque instrument
            serviceEngine = self.env['efund.service']
            result = serviceEngine.get_portfolio_asset_value(rec.fund_id.vehicule_id, rec.valuation_date,)
            if result:
                for res in result:
                    lines_vals.append((0, 0, {
                        'name': res.get('instrument'),
                        'date': res.get('date'),
                        'type': res.get('type'),
                        'quantity': res.get('quantity'),
                        'price_acquisition': res.get('price_acquisition'),
                        'price': res.get('price'),
                        'interest': res.get('interest'),
                        'total_amount': res.get('total_amount'),
                    }))

            # Injection des lignes dans la session
            self.write({'line_ids': lines_vals})

            # vérification des données de calcul VL

            result = serviceEngine.get_valuation_by_type(rec.fund_id.vehicule_id, rec.valuation_date)
            payload = {
                'reset_interest': serviceEngine.get_balance_sql_optimized('217100', rec.fund_id.vehicule_id.company_id,
                                                                          rec.valuation_date.year,
                                                                          rec.valuation_date),
                'interest':result.get ('total_valuation_bond_interest'),
                'reset_dfe': serviceEngine.get_balance_sql_optimized('553100', rec.fund_id.vehicule_id.company_id,
                                                                          rec.valuation_date.year,
                                                                          rec.valuation_date),
                'dfe_obligation':result.get ('total_valuation_bond_value'),

            }
            raise ValidationError(f"payload {payload}")
            event = self.env['efund.accounting.event'].create(
                serviceEngine.build_event_payload('VL_RESET_INTEREST', rec.fund_id.vehicule_id.id, 'Intérêt couru et Différence Estimation - VL',  rec.valuation_date, payload))
            rec.event_reset_id = event.id
            self.env['efund.accounting.engine'].process_event(event)

            fund_id = self.env['efund.vehicule.fund'].search(
                [('state', '=', 'active'), ('vehicule_id', '=', rec.fund_id.vehicule.id)], limit=1)
            if fund_id:
                if not fund_id:
                    raise ValidationError(_("Aucun fond actif trouvé."))
                share_class = self.env['efund.fund.share.class'].search([
                    ('vehicule_fund_id', '=', rec.fund_id.id),
                    ('is_default', '=', True)
                ])

            management_fee = share_class.management_fee_rate
            total_actifnet = serviceEngine.get_actif_net(rec.fund_id.vehicule_id, rec.date_operation)
            management_amount = self.compute_fixed_charges(total_actifnet, fund_id, rec.date_operation, management_fee)


            payload = {
                "frais_gestion": management_amount,
            }
            event = self.env['efund.accounting.event'].create(
                serviceEngine.build_event_payload('VL_INIT_INTEREST', rec.fund_id.vehicule_id.id,
                                                  'Intérêt couru et Différence Estimation - VL', rec.valuation_date,
                                                  payload))
            rec.event_frais_id = event.id
            self.env['efund.accounting.engine'].process_event(event)

            total_actifnet = serviceEngine.get_actif_net(rec.fund_id.vehicule_id, rec.date_operation)
            rec.unit_nav = total_actifnet / rec.nb_parts

            return True

    def action_validate(self):
        for record in self:
            if not record.line_ids:
                raise ValidationError(_("Impossible de valider une séance sans inventaire."))

            # Ici, on pourrait générer les écritures de réévaluation comptable
            # record._generate_accounting_entries()

            record.write({
                'state': 'validated',
                'name': self.env['ir.sequence'].next_by_code('efund.nav.session') or _('VL/%s') % record.valuation_date
            })

    def action_cancel(self):
        for record in self:
            if record.state == 'validated':
                # Optionnel : Vérifier si des écritures comptables liées existent
                pass
            record.write({'state': 'cancel'})

    def action_view_journal_entries(self):
        self.ensure_one()
        # On cherche les écritures (account.move) qui ont cette session comme source
        # (Nécessite d'avoir ajouté un champ nav_session_id sur account.move)
        return {
            'name': _('Écritures Comptables'),
            'type': 'ir.actions.act_window',
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('ref', 'ilike', self.name)],  # Ou un champ Many2one dédié
            'context': {'create': False},
        }