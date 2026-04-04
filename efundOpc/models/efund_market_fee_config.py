from odoo import models, fields, api, _

class EfundMarketFeeConfig(models.Model):
    _name = 'efund.market.fee.config'
    _description = 'Configuration des Commissions de Marché'

    name = fields.Char("Libellé", required=True)  # Ex: Commission BVMAC
    code = fields.Selection([
        ('bvmac', 'BVMAC'),
        ('cosumaf', 'COSUMAF'),
        ('dc', 'Dépositaire Central (DC)'),
        ('courtage', 'Courtage SGI'),
        ('tva', 'TVA sur Commissions')
    ], string="Type")

    computation_base = fields.Selection([
        ('nominal', 'Valeur Nominale'),
        ('transaction', 'Valeur Totale Transaction')
    ], string="Base de calcul", default='transaction')
    description = fields.Char("Description")

    rate = fields.Float("Taux (%)", digits=(16, 6))  # Ex: 0.3 pour BVMAC
    state = fields.Selection([('draft', 'Draft'), ('validated', 'Validé'), ('archived', 'Archivé'), ], default='draft')