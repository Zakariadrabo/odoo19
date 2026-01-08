from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class FundPositionWizard(models.TransientModel):
    _name = 'efund.position.wizard'
    _description = 'Assistant pour ajouter des positions'

    # ========== MODE D'OPÉRATION ==========
    operation_type = fields.Selection([
        ('add', 'Ajouter une nouvelle position'),
        ('import', 'Importer plusieurs positions'),
        ('update', 'Mettre à jour une position existante')
    ], string="Type d'opération", default='add', required=True)

    title = fields.Char(string="Title", compute='_compute_title')



    # ========== POUR AJOUT SIMPLE ==========
    fund_id = fields.Many2one(
        'efund.fund',
        string="Fonds",
        required=True
    )

    instrument_id = fields.Many2one(
        'efund.fund.instrument',
        string="Instrument",
        required=True,
        domain="[('is_active', '=', True)]"
    )

    quantity = fields.Float(
        string="Quantité",
        required=True,
        default=0.0
    )

    avg_cost = fields.Monetary(
        string="Prix d'acquisition unitaire",
        currency_field='currency_id',
        required=True
    )

    valuation_date = fields.Date(
        string="Date de valorisation",
        default=fields.Date.today,
        required=True
    )

    # ========== POUR IMPORT MULTIPLE ==========
    import_file = fields.Binary(string="Fichier CSV")
    filename = fields.Char(string="Nom du fichier")

    # ========== INFORMATIONS CONTEXTUELLES ==========
    currency_id = fields.Many2one(
        'res.currency',
        string="Devise",
        related='fund_id.currency_id',
        readonly=True
    )

    # ========== MÉTHODES ==========
    @api.depends('operation_type')
    def _compute_title(self):
        for record in self:
            if record.operation_type == 'add':
                record.title = "Ajouter une position"
            elif record.operation_type == 'import':
                record.title = "Importer des positions"
            elif record.operation_type == 'update':
                record.title = "Mettre à jour une position"
            else:
                record.title = ""  # Ou une valeur par défaut

    def action_add_position(self):
        """Ajouter une nouvelle position"""
        self.ensure_one()

        # Validation
        if self.quantity <= 0:
            raise UserError(_("La quantité doit être supérieure à zéro."))

        if self.avg_cost <= 0:
            raise UserError(_("Le prix d'acquisition doit être supérieur à zéro."))

        # Vérifier si une position existe déjà pour cette date
        existing = self.env['efund.fund.position'].search([
            ('fund_id', '=', self.fund_id.id),
            ('instrument_id', '=', self.instrument_id.id),
            ('valuation_date', '=', self.valuation_date)
        ], limit=1)

        if existing:
            raise UserError(_(
                "Une position existe déjà pour cet instrument à cette date.\n"
                "Utilisez la fonction 'Mettre à jour' pour modifier la position existante."
            ))

        # Créer la position
        position = self.env['efund.fund.position'].create({
            'fund_id': self.fund_id.id,
            'instrument_id': self.instrument_id.id,
            'quantity': self.quantity,
            'avg_cost': self.avg_cost,
            'valuation_date': self.valuation_date,
        })
        self.fund_id.message_post(body=_(
            "Nouvelle position ajoutée sur <b>%s</b> : %s unités à %.2f"
        ) % (self.instrument_id.name, self.quantity, self.avg_cost))

        return [
            {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Succès'),
                    'message': _('La position a été ajoutée avec succès.'),
                    'type': 'success',
                    'sticky': False,
                }
            },
            {
                'type': 'ir.actions.act_window',
                'res_model': 'efund.fund',
                'res_id': self.fund_id.id,
                'view_mode': 'form',
                'target': 'current',
            }
        ]
        """
        # Message de confirmation
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Position ajoutée'),
                'message': _('La position a été ajoutée avec succès.'),
                'type': 'success',
                'sticky': False,
                'next': {
                    'type': 'ir.actions.act_window',
                    'res_model': 'efund.fund.position',
                    'view_mode': 'form',
                    'res_id': position.id,
                    'target': 'current',
                }
            }
        }
        """

    def action_import_positions(self):
        """Importer plusieurs positions depuis un fichier CSV"""
        self.ensure_one()

        if not self.import_file:
            raise UserError(_("Veuillez sélectionner un fichier à importer."))

        try:
            import base64
            import io
            import csv

            # Décoder le fichier
            file_content = base64.b64decode(self.import_file)
            text_content = file_content.decode('utf-8')

            # Lire le CSV
            csv_file = io.StringIO(text_content)
            reader = csv.DictReader(csv_file, delimiter=',')

            positions_created = []
            errors = []

            for i, row in enumerate(reader, 1):
                try:
                    # Extraire les données
                    instrument_code = row.get('instrument_code', '').strip()
                    quantity = float(row.get('quantity', 0))
                    avg_cost = float(row.get('avg_cost', 0))
                    valuation_date = row.get('valuation_date', fields.Date.today())

                    # Chercher l'instrument
                    instrument = self.env['efund.fund.instrument'].search([
                        '|',
                        ('isin', '=', instrument_code),
                        ('ticker', '=', instrument_code),
                        ('name', 'ilike', instrument_code)
                    ], limit=1)

                    if not instrument:
                        errors.append(f"Ligne {i}: Instrument '{instrument_code}' non trouvé")
                        continue

                    # Créer la position
                    position = self.env['efund.fund.position'].create({
                        'fund_id': self.fund_id.id,
                        'instrument_id': instrument.id,
                        'quantity': quantity,
                        'avg_cost': avg_cost,
                        'valuation_date': valuation_date,
                    })

                    positions_created.append(position.id)

                except Exception as e:
                    errors.append(f"Ligne {i}: {str(e)}")

            # Message de résultat
            message = f"{len(positions_created)} positions importées avec succès."
            if errors:
                message += f"\n{len(errors)} erreurs."
                if len(errors) <= 3:
                    for error in errors:
                        message += f"\n- {error}"

            return {
                'type': 'ir.actions.client',
                'tag': 'display_notification',
                'params': {
                    'title': _('Import terminé'),
                    'message': message,
                    'type': 'info' if errors else 'success',
                    'sticky': True,
                    'next': {
                        'type': 'ir.actions.act_window',
                        'res_model': 'efund.fund.position',
                        'view_mode': 'tree,form',
                        'domain': [('id', 'in', positions_created)],
                        'target': 'current',
                    }
                }
            }

        except Exception as e:
            raise UserError(_("Erreur lors de l'import: %s") % str(e))