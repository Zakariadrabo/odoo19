# -*- coding: utf-8 -*-
from odoo import api, fields, models, _


class FundPep(models.Model):
    _name = "efund.investor.pep"
    _description = "PEP"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "create_date desc"

    nom = fields.Char(string="Nom", required=True)
    prenom= fields.Char(string="Prenom", required=True)
    fonction = fields.Char(string='Fonction', required=True)
    country_id = fields.Many2one("res.country", string="Pays")
    full_name = fields.Char(string="Nom complet", compute="_compute_full_name", store=True)

    @api.depends('nom', 'prenom')
    def _compute_full_name(self):
        for record in self:
            if record.nom and record.prenom:
                record.full_name = f"{record.nom} {record.prenom}"
            else:
                record.full_name = record.nom or record.prenom or ''
