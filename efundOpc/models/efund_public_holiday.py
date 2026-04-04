from odoo import models, fields, api


class EfundPublicHoliday(models.Model):
    _name = 'efund.public.holiday'
    _description = 'Gestion des Jours Fériés'
    _order = 'holiday_date desc'

    name = fields.Char(string="Nom du jour férié", required=True, help="Ex: Fête de l'Indépendance")
    holiday_date = fields.Date(string="Date", required=True)
    year = fields.Integer(string="Année", compute="_compute_year", store=True)

    """
    # Pour gérer plusieurs zones (BVMAC vs BRVM par exemple)
    location_ids = fields.Selection([
        ('uemoa', 'Zone UEMOA'),
        ('cemac', 'Zone CEMAC'),
    ], string="Zone concernée", default='uemoa')
    """

    # Contraintes
    _sql_constraints = [
        ('unique_holiday_date', 'unique(holiday_date, location_ids)',
         'Ce jour férié est déjà enregistré pour cette zone !')
    ]

    @api.depends('holiday_date')
    def _compute_year(self):
        for rec in self:
            rec.year = rec.holiday_date.year if rec.holiday_date else 0