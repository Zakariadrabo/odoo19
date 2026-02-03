# efund_fund_position.py
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


class FundPosition(models.Model):
    _name = "efund.vehicule.position"
    _description = "Position du véhicule sur un instrument"
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _rec_name = "display_name"
    _order = "valuation_date desc, instrument_id"

    # ========== CHAMPS DE BASE ==========
    vehicule_id = fields.Many2one('efund.vehicule', required=True, ondelete='cascade')
    instrument_id = fields.Many2one('efund.vehicule.instrument.core', string="Instrument", required=True, index=True, )
    issuance_price = fields.Monetary(string="Price", store=True, )

    # ========== INFORMATIONS DE POSITION ==========
    quantity = fields.Float(string="Quantité", digits=(16, 4), default=0.0, required=True)
    avg_cost = fields.Monetary(string="Coût moyen unitaire")
    market_value = fields.Monetary(string="Valeur de marché", compute='_compute_market_value', store=True, )
    valuation_date = fields.Date(string="Date de valorisation",  index=True, )

    # ========== INFORMATIONS DE COURS ==========
    last_price = fields.Float(string="Dernier cours", digits=(16, 4), compute='_compute_last_price', store=True, )
    last_price_date = fields.Date(string="Date dernier cours", compute='_compute_last_price', store=True, )
    first_price = fields.Float(string="Premier cours", digits=(16, 4), store=True, )
    first_price_date = fields.Date(string="Date premier cours", default=fields.Date.today, store=True, )

    # ========== CALCULS DE PERFORMANCE ==========
    unrealized_pl = fields.Monetary(string="Plus/Moins-value latente", currency_field='currency_id',
                                    compute='_compute_market_value', store=True, )
    unrealized_pl_percent = fields.Float(string="PL %", digits=(16, 2), compute='_compute_market_value', store=True, )
    decoration_state = fields.Selection([('normal', 'Normal'), ('success', 'Success'), ('danger', 'Danger')],
                                        string="Decoration State", compute='_compute_decoration_state',
                                        store=True
                                        )

    # ========== AUTRES INFORMATIONS ==========
    currency_id = fields.Many2one(string="Devise de valorisation", related='vehicule_id.currency_id', )
    state = fields.Selection([('active', 'Active'), ('closed', 'Clôturée'), ('suspended', 'Suspendue')],
                             string="Statut", default='active', required=True)
    notes = fields.Text(string="Notes")
    display_name = fields.Char(string="Nom", compute='_compute_display_name', store=True)
    adjustment_ids = fields.One2many('efund.position.adjustment', 'position_id', string="Ajustements")
    cashflow_ids = fields.One2many('efund.vehicule.cashflow', 'position_id', string="Flux de trésorerie prévus")

    @api.depends('quantity', 'avg_cost', 'instrument_id', 'valuation_date')
    def _compute_market_value(self):
        for rec in self:
            instrument = rec.instrument_id
            today = rec.valuation_date or fields.Date.today()
            price = 0.0

            # --- CAS 1 : INSTRUMENTS COTÉS OU OPCVM ---
            if instrument.is_listed:
                if instrument.valuation_method == 'listed':
                    if instrument.instrument_type == 'bond':
                        bond = self.env['efund.vehicule.instrument.core.bond'].browse(instrument.id)
                        if hasattr(bond, 'maturity_date') and bond.maturity_date >= today:
                            price = rec._calculate_linear_accretion(bond, today)
                        else:
                            raise ValidationError('La date de maturité est invalide.')
                else:
                    if hasattr(instrument, 'last_validated_price') and instrument.last_validated_price > 0:
                        price = instrument.last_validated_price
            else:
                price = rec.first_price or rec.avg_cost

            rec.last_price = price
            rec.market_value = rec.quantity * price
            rec.unrealized_pl = rec.market_value - (rec.quantity * rec.avg_cost)
            rec.unrealized_pl_percent = ((rec.market_value - (rec.quantity * rec.avg_cost)) / (rec.quantity * rec.avg_cost)) * 100

    def _calculate_linear_accretion(self, instrument, target_date):
        """ Calcule la valeur étalée de l'obligation à une date donnée """
        self.ensure_one()

        # 1. Vérifier les dates
        date_achat = self.first_price_date
        date_fin = instrument.maturity_date

        if not date_achat or not date_fin or target_date >= date_fin:
            return instrument.face_value  # On est à la maturité, vaut le nominal

        if target_date <= date_achat:
            return self.avg_cost  # On est au prix d'achat

        # 2. Calcul du prorata temporis (Linéaire)
        jours_totaux = (date_fin - date_achat).days
        jours_ecoules = (target_date - date_achat).days

        # Différence à amortir (Décote)
        decote_totale = instrument.face_value - self.avg_cost

        # Valeur actuelle = Prix Achat + Part de la décote gagnée
        valeur_actuelle = self.avg_cost + (decote_totale * (jours_ecoules / jours_totaux))

        return valeur_actuelle


    def get_instrument_listed_value(self, instrument, target_date):
        self.ensure_one()
        if instrument.name != 'efund.vehicule.instrument.core':
            raise ValidationError("Objet instrument invalide.")

        return self._calculate_linear_accretion(instrument, target_date)



    # les méthodes de dépendances
    def apply_trade(self, trade):
        self.ensure_one()

        if trade._name != 'efund.investment.transaction':
            raise ValidationError("Objet trade invalide.")

        Q_old = self.quantity
        PRU_old = self.avg_cost or 0.0

        if trade.move_type == 'in':
            cost_old = Q_old * PRU_old
            cost_buy = (trade.quantity * trade.price_unit)  # + trade.total_fees

            Q_new = Q_old + trade.quantity
            PRU_new = (cost_old + cost_buy) / Q_new if Q_new else 0.0

            self.write({
                'quantity': Q_new,
                'avg_cost': PRU_new,
            })

        else:
            if trade.quantity > Q_old:
                raise ValidationError("Quantité vendue supérieure à la position.")

            cost_sold = trade.quantity * PRU_old
            proceeds = (trade.quantity * trade.price_unit)  # - trade.total_fees
            realized_pl = proceeds - cost_sold

            Q_new = Q_old - trade.quantity

            self.write({
                'quantity': Q_new,
                'avg_cost': PRU_old if Q_new else 0.0,
                'state': 'closed' if Q_new == 0 else 'active'
            })

        # trade.write({'realized_pl': realized_pl})


    @api.depends('unrealized_pl')
    def _compute_decoration_state(self):
        for record in self:
            if record.unrealized_pl > 0:
                record.decoration_state = 'success'
            elif record.unrealized_pl < 0:
                record.decoration_state = 'danger'
            else:
                record.decoration_state = 'normal'


    @api.depends('instrument_id')
    def _compute_last_price(self):
        """Récupère le dernier cours validé pour l'instrument"""
        for pos in self:
            if pos.instrument_id:
                # Chercher le dernier cours validé
                last_price = self.env['efund.vehicule.instrument.core.price'].search([
                    ('instrument_id', '=', pos.instrument_id.id),
                    ('is_validated', '=', True)
                ], order='date desc', limit=1)

                if last_price:
                    pos.last_price = last_price.price
                    pos.last_price_date = last_price.date
                else:
                    pos.last_price = 0.0
                    pos.last_price_date = False
            else:
                pos.last_price = 0.0
                pos.last_price_date = False


    @api.depends('quantity', 'avg_cost', 'last_price')
    def _compute_market_value(self):
        """Calcule la valeur de marché basée sur le dernier cours"""
        for pos in self:
            if pos.quantity and pos.last_price:
                pos.market_value = pos.quantity * pos.last_price
            elif pos.quantity and not pos.issuance_price:
                pos.market_value = pos.quantity * pos.issuance_price
            else:
                pos.market_value = 0.0


    @api.depends('market_value', 'quantity', 'avg_cost')
    def _compute_performance(self):
        """Calcule les plus/moins-values latentes"""
        for pos in self:
            cost_basis = pos.quantity * (pos.avg_cost or 0.0)
            market_value = pos.market_value

            if cost_basis:
                pos.unrealized_pl = market_value - cost_basis
                pos.unrealized_pl_percent = ((market_value - cost_basis) / cost_basis) * 100
            else:
                pos.unrealized_pl = 0.0
                pos.unrealized_pl_percent = 0.0


    @api.depends('vehicule_id', 'instrument_id', 'valuation_date')
    def _compute_display_name(self):
        """Génère un nom d'affichage convivial"""
        for rec in self:
            if rec.vehicule_id and rec.instrument_id:
                rec.display_name = f"{rec.vehicule_id.name} - {rec.instrument_id.name} ({rec.valuation_date or fields.Date.today()})"
            else:
                rec.display_name = "Nouvelle position"


    @api.constrains('quantity', 'avg_cost')
    def _check_positive_values(self):
        """Vérifie que les valeurs sont positives"""
        for rec in self:
            if rec.quantity < 0:
                raise ValidationError(_("La quantité ne peut pas être négative."))
            if rec.avg_cost < 0:
                raise ValidationError(_("Le coût moyen ne peut pas être négatif."))


    # ========== MÉTHODES D'ACTION ==========
    def action_update_position(self):
        """Mettre à jour une position existante"""
        self.ensure_one()
        return {
            'name': _('Mettre à jour la position'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.position.update.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_position_id': self.id,
                'default_vehicule_id': self.vehicule_id.id,
                'default_instrument_id': self.instrument_id.id,
                'default_current_quantity': self.quantity,
                'default_current_avg_cost': self.avg_cost,
            }
        }


    def action_close_position(self):
        """Clôturer une position"""
        self.ensure_one()
        return {
            'name': _('Clôturer la position'),
            'type': 'ir.actions.act_window',
            'res_model': 'efund.position.close.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_position_id': self.id,
            }
        }


    def action_view_instrument(self):
        """Ouvrir la fiche de l'instrument"""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Instrument'),
            'res_model': 'efund.fund.instrument',
            'view_mode': 'form',
            'res_id': self.instrument_id.id,
        }


    def _apply_instrument_event(self, event):
        """
        Applique un événement d'instrument à la position
        """
        self.ensure_one()

        _logger.info(f"Applying event {event.name} to position {self.id}")

        # Créer un enregistrement d'ajustement
        adjustment_vals = {
            'position_id': self.id,
            'event_id': event.id,
            'adjustment_date': fields.Date.today(),
            'adjustment_type': event.event_type,
            'description': f"Ajustement suite à l'événement: {event.name}",
        }

        # Appliquer les ajustements selon le type d'événement
        if event.event_type == 'dividend':
            # Pour un dividende, on crée un revenu
            adjustment_vals.update({
                'cash_impact': event.net_amount * self.quantity,
                'tax_amount': (event.cash_amount * (event.tax_rate / 100)) * self.quantity,
            })

        elif event.event_type in ['stock_split', 'reverse_split']:
            # Pour un split, on ajuste la quantité
            new_quantity = self.quantity * event.adjustment_ratio
            adjustment_vals.update({
                'quantity_change': new_quantity - self.quantity,
                'new_quantity': new_quantity,
                'price_adjustment': 1.0 / event.adjustment_ratio if event.adjustment_ratio > 0 else 1.0,
            })

            # Mettre à jour la position
            self.write({'quantity': new_quantity})

        elif event.event_type == 'capital_increase':
            # Pour une augmentation de capital
            adjustment_vals.update({
                'quantity_change': self.quantity * event.quantity_ratio,
                'description': f"Augmentation de capital - Ratio: {event.quantity_ratio}",
            })

        elif event.event_type == 'coupon_payment':
            # Pour un paiement de coupon
            adjustment_vals.update({
                'cash_impact': event.net_amount,
                'tax_amount': event.cash_amount - event.net_amount,
            })

        # Créer l'enregistrement d'ajustement
        adjustment = self.env['efund.position.adjustment'].create(adjustment_vals)

        # Poste un message sur la position
        self.message_post(
            body=_("Événement appliqué: %s") % event.name,
            subject=_("Ajustement de position")
        )

        return adjustment

    def get_or_create_position(self, instrument_id, first_price_date, first_price, vehicule_id):
        # Par défaut on considère que nous avons un fond
        pos = self.env['efund.vehicule.position']
        position = pos.search([
            ('vehicule_id', '=', vehicule_id),
            ('instrument_id', '=', instrument_id),
            ('state', '=', 'active')
        ], limit=1)

        if not position:
            position = pos.create({
                'vehicule_id': vehicule_id,
                'instrument_id': instrument_id,
                'first_price': first_price,
                'quantity': 0.0,
                'avg_cost': 0.0,
                'first_price_date': first_price_date,
            })

        return position


    # retourne la position du titre
    def get_position_by_instrument(self, instrument_id, vehicule_id):
        result = self.search([('instrument_id', '=', instrument_id), ('vehicule_id', '=', vehicule_id)])
        if len(result) > 0:
            return result[0].quantity
        return 0.0

    # renvoie la liste des véhicule pour un instrument donnée
    # utiliser pour générer le paiement d'annuité
    def get_vehicles_by_instrument(self, instrument_id):
        """
        Récupère la liste des véhicules détenant un instrument spécifique.
        :param instrument_id: ID de l'instrument (efund.vehicule.instrument.core)
        :return: Liste de dictionnaires contenant le nom du véhicule et la quantité
        """
        # 1. Recherche des positions actives pour cet instrument
        # On filtre sur la quantité > 0 pour n'avoir que les détenteurs réels
        positions = self.env['efund.vehicule.position'].search([
            ('instrument_id', '=', instrument_id),
            ('quantity', '>', 0),
            ('state', '=', 'active')
        ])

        # 2. Construction de la liste de résultats
        result_list = []
        for pos in positions:
            result_list.append({
                'vehicule_id': pos.vehicule_id.id,
                'vehicule_name': pos.vehicule_id.name,
                'quantity': pos.quantity,
                'avg_cost': pos.avg_cost,  # Optionnel : ajout du prix de revient
                'market_value': pos.market_value  # Optionnel : ajout de la valeur actuelle
            })

        return result_list

    # Methode pour générer les cashflow à venir
    def action_generate_cashflows(self, instrument):
        """Méthode appelée pour générer l'échéancier de cette position"""
        self.ensure_one()
        # 1. Nettoyage des anciens flux non encaissés
        self.cashflow_ids.filtered(lambda f: f.state == 'draft').unlink()

        #instrument = self.instrument_id
        # On ne génère des flux que pour les obligations (Bonds) ou DAT
        if instrument.instrument_type == 'bond':
            # On suppose que l'instrument a un modèle lié pour son calendrier
            bond = self.env['efund.vehicule.instrument.core.bond'].search([('instrument_id', '=', instrument.id)])
            if bond:
                for coupon in bond.coupon_ids:
                    if coupon.date_paiement > fields.Date.today():
                        self.env['efund.vehicule.cashflow'].create({
                            'vehicule_id': self.vehicule_id.id,
                            'position_id': self.id,
                            'instrument_id': instrument.id,
                            'date_scheduled': coupon.date_paiement,
                            'amount_expected': self.quantity * bond.face_value * (bond.coupon_rate / 100),
                            'flow_type': 'coupon',
                        })

