from odoo import models, fields, api

class JoinFundWizard(models.TransientModel):
    _name = 'efund.investor.join.fund.wizard'
    _description = 'Assistant adhésion fonds'

    investor_id = fields.Many2one('efund.investor', string="Investisseur", required=True, readonly=True)
    fund_id = fields.Many2one('efund.vehicule.fund', string="Choisir le Fonds", required=True)
    #fund_id = fields.Many2one('efund.vehicule.fund', string="Fonds à rejoindre", required=True, domain="[('id', 'in', available_fund_ids)]")

    # Champ technique pour stocker les IDs autorisés
    available_fund_ids = fields.Many2many('efund.vehicule.fund', compute='_compute_available_funds')

    @api.depends('investor_id')
    def _compute_available_funds(self):
        for rec in self:
            if rec.investor_id:
                # 1. Trouver tous les comptes titres existants pour cet investisseur
                existing_accounts = self.env['efund.investor.part_account'].search([
                    ('investor_id', '=', rec.investor_id.id)
                ])
                # 2. Récupérer les IDs des véhicules (fonds) liés à ces comptes
                # On remonte du véhicule vers le fonds spécifique
                excluded_vehicule_ids = existing_accounts.mapped('vehicule_id').ids

                # 3. Chercher les fonds dont le véhicule n'est pas dans la liste d'exclusion
                available_funds = self.env['efund.vehicule.fund'].search([
                    ('vehicule_id', 'not in', excluded_vehicule_ids)
                ])
                rec.available_fund_ids = available_funds
            else:
                rec.available_fund_ids = self.env['efund.vehicule.fund'].search([])

    def action_confirm_join(self):
        """Appelle la méthode métier sur l'investisseur avec le fonds choisi"""
        self.ensure_one()
        # On appelle la méthode de l'investisseur que nous avons conçue
        return self.investor_id.action_join_fund(self.fund_id)