import logging

from odoo import models, fields, api, _
_logger = logging.getLogger(__name__)

class FundInstrument(models.Model):
    _name = "efund.vehicule.instrument.core"
    _description = "Instrument Financier - Core"


    # Identification
    name = fields.Char(required=True, string='Nom instrument')
    isin = fields.Char(index=True,string="Code ISIN")
    instrument_type = fields.Selection([('equity', 'Action'), ('bond', 'Obligation'),('dat', 'DAT'), ('opcvm', 'OPCVM'),('tcn','Bon')], required=True)
    currency_id = fields.Many2one('res.currency')
    issuer_id = fields.Many2one('efund.vehicule.instrument.issuer', string="Émetteur")
    asset_class_id = fields.Many2one('efund.asset.class', required=True, string="Classe d'actif")
    state = fields.Selection([('draft', 'Draft'), ('active', 'Active'), ('suspended', 'Suspended'), ('liquidated', 'Liquidated'), ],
        string='Status', default='draft')

    # Prise en compte des prix
    price_source = fields.Selection([('external', 'Externe'), ('internal', 'Interne'), ], string="Source des prix")
    last_validated_price = fields.Float(string="Dernier cours validé")
    last_price_date = fields.Date(string="Date dernier cours")
    is_listed = fields.Boolean(string='Est Coté', default=False)
    valuation_method = fields.Selection([('market', 'Au marché'), ('listed', 'Cours Lissé')], string="Valorisation")
    #valuation_type = fields.Selection([('actuarial', 'Actuarielle'), ('linear', 'Linéaire')])

    tax_rate = fields.Float("Taux IRVM/IRCM (%)",)
    is_tax_exempt = fields.Boolean("Exonéré d'impôt", default=False)
    settlement_mode = fields.Selection([ ('market', 'Dénouement de Marché (J+X)'), ('direct', 'Direct / Sans dénouement (DAT, Billet)')
    ], string="Mode de règlement", default='market')

    # Relations techniques
    position_ids = fields.One2many('efund.vehicule.portfolio','instrument_id',string='Positions')
    instrument_fee_ids = fields.One2many('efund.vehicule.instrument.fee.rule', 'instrument_id', string="Frais",help="Frais sur cet instrument")
    orders_ids = fields.One2many('efund.investment.order', 'instrument_id', string="Commandes")
    instrument_price_ids = fields.One2many('efund.vehicule.instrument.core.price', 'instrument_id', string="Prix")
    attached_account = fields.Many2one('account.account', string="Compte associé", help="Compte associé à cet instrument")


    @api.depends('instrument_price_ids')
    def _compute_last_validated_price(self):
        for instrument in self:
            last_price = instrument.instrument_price_ids.filtered(
                lambda p: p.is_validated
            ).sorted('date', reverse=True)

            if last_price:
                instrument.last_validated_price = last_price[0].price
                instrument.last_price_date = last_price[0].date
            else:
                instrument.last_validated_price = 0.0
                instrument.last_price_date = False

    def _get_account_root(self,instrument_type ):
        """ Définit la racine SYSCOHADA selon le type d'instrument """
        mapping = {
            'bond': '211',
            'tcn': '212',
            'equity': '213',
            'opcvm': '214',
            'dat': '215',

        }
        return mapping.get(instrument_type, '218')

    def _create_chronological_account(self, company):
        """
        Génère un compte comptable chronologique compatible Odoo 19+.
        Format : Racine + Séquence 5 chiffres (ex: 21100001).
        """
        self.ensure_one()
        target_company = self.env['res.company'].browse(company.id)
        AccountObj = self.env['account.account'].with_company(target_company).sudo()
        root = self._get_account_root(self.instrument_type)
        company_id = str(company)


        # 1. Recherche de TOUS les comptes de cette racine pour cette société
        # On utilise le pattern JSON pour filtrer en SQL via code_store
        search_pattern = f'"{company_id}": "{root}%"'
        accounts = AccountObj.search([
            ('code_store', '=like', f'%{search_pattern}%')
        ])

        next_number = 1
        if accounts:
            # 2. Tri manuel en Python car 'code' n'est plus stocké en base
            # On extrait le code spécifique à la société pour chaque compte trouvé
            codes = []
            for acc in accounts:
                # code_store est un dictionnaire { 'company_id': 'code' }
                c = acc.code_store.get(company_id)
                if c and c.startswith(root):
                    codes.append(c)

            if codes:
                # On trie les codes et on prend le plus grand
                codes.sort()
                last_code = codes[-1]

                # On extrait la partie numérique après la racine
                sequence_str = last_code[len(root):]
                try:
                    next_number = int(sequence_str) + 1
                except (ValueError, IndexError):
                    next_number = 1

        # 3. Formater le nouveau code (ex: 21100001)
        new_code = f"{root}{str(next_number).zfill(3)}"

        # 4. Création du compte
        # Utiliser with_company(company) est crucial pour que Odoo
        # injecte le code dans la bonne clé du dictionnaire JSON 'code_store'
        return AccountObj.create({
            'name': f"Titres {self.name}",
            'code': new_code,
            'account_type': 'asset_fixed',
            'code_store': f'"{company_id}": "{new_code}"',
        })
    def get_or_create_accounting_mapping(self):
        """
        Retourne le compte comptable associé.
        Le crée s'il n'existe pas encore pour cette société.
        """
        self.ensure_one()
        # Le véhicule définit la société (le fonds a sa propre company,
        # les mandats partagent la company de gestion)
        # 1. Récupérer la compagnie 'MANDATS'

        if self.vehicule_id.company_id:
            company = self.vehicule_id.company_id
        else:
            company = self.env['res.company'].search([('company_code', '=', 'MANDATS')], limit=1)

        mapping_obj = self.env['efund.instrument.account']
        mapping = mapping_obj.search([
            ('instrument_id', '=', self.instrument_id.id),
            ('company_id', '=', company.id)
        ], limit=1)
        _logger.info(f"********** mapping {mapping}")


        if not mapping:
            # Appel de la création chronologique

            new_account = self.instrument_id._create_chronological_account(company,self.instrument_id )
            mapping = mapping_obj.create({
                'instrument_id': self.instrument_id.id,
                'company_id': company.id,
                'account_id': new_account.id
            })

        return mapping.account_id


    def get_or_create_accounting_mapping(self, company):
        """
        Méthode déplacée dans l'Instrument Core.
        Prend un objet record 'res.company' en paramètre.
        """
        self.ensure_one()


        mapping_obj = self.env['efund.instrument.account']
        mapping = mapping_obj.search([
            ('instrument_id', '=', self.id),
            ('company_id', '=', company.id)
        ], limit=1)




        if not mapping:
            # On appelle la création chronologique (que nous avons définie ensemble)
            # On passe 'self' car ici 'self' EST l'instrument
            new_account = self._create_chronological_account(company)

            mapping = mapping_obj.create({
                'instrument_id': self.id,
                'company_id': company.id,
                'account_id': new_account.id
            })

        return mapping.account_id


