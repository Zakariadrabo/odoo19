# efund_fund_import_price_wizard.py
import logging

from odoo import models, fields, api, _
from odoo.exceptions import UserError
import base64
import io
import csv
_logger = logging.getLogger(__name__)

class FundImportPriceWizard(models.TransientModel):
    _name = "efund.fund.import.price.wizard"
    _description = "Assistant d'import des cours"

    import_type = fields.Selection([
        ('single', 'Pour cet instrument'),
        ('file', 'Depuis un fichier'),
        ('api', 'Depuis une API')
    ], string="Type d'import", default='single', required=True)

    # Pour import unique
    instrument_id = fields.Many2one('efund.fund.instrument', string="Instrument")
    price_date = fields.Date(string="Date du cours", default=fields.Date.today)
    price = fields.Float(string="Cours", digits=(16, 4))
    currency_id = fields.Many2one('res.currency', string="Devise")

    # Pour import fichier
    import_file = fields.Binary(string="Fichier CSV", required=False)
    filename = fields.Char(string="Nom du fichier")

    # Pour import API
    api_config_id = fields.Many2one('efund.fund.instrument.price.import', string="Configuration API")

    def action_import(self):
        """Exécuter l'import"""
        if self.import_type == 'single':
            return self._import_single_price()
        elif self.import_type == 'file':
            return self._import_from_file()
        elif self.import_type == 'api':
            return self._import_from_api()

    def _import_single_price(self):
        """Importer un prix unique"""
        if not self.instrument_id:
            raise UserError(_("Veuillez sélectionner un instrument"))

        if not self.price or self.price <= 0:
            raise UserError(_("Veuillez entrer un prix valide"))

        # Vérifier si le cours existe déjà pour cette date
        existing = self.env['efund.fund.instrument.price'].search([
            ('instrument_id', '=', self.instrument_id.id),
            ('date', '=', self.price_date)
        ], limit=1)

        if existing:
            existing.write({
                'price': self.price,
                'currency_id': self.currency_id.id or self.instrument_id.currency_id.id,
            })
            message = _("Cours mis à jour")
        else:
            _logger.info(f"********** je vais créer le cours")
            self.env['efund.fund.instrument.price'].create({
                'instrument_id': self.instrument_id.id,
                'date': self.price_date,
                'price': self.price,
                'currency_id': self.currency_id.id or self.instrument_id.currency_id.id,
                'is_validated': False,
            })
            message = _("Cours créé")

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _('Import réussi'),
                'message': message,
                'type': 'success',
                'sticky': False,
            }
        }

    def _import_from_file(self):
        """Importer depuis un fichier CSV"""
        if not self.import_file:
            raise UserError(_("Veuillez sélectionner un fichier"))

        try:
            file_content = base64.b64decode(self.import_file)
            text_content = file_content.decode('utf-8', errors='ignore')

            csv_file = io.StringIO(text_content)
            reader = csv.reader(csv_file, delimiter=',')

            imported = 0
            errors = []

            for i, row in enumerate(reader, 1):
                try:
                    if i == 1 and len(row) > 0 and 'instrument' in row[0].lower():
                        continue  # Sauter l'en-tête


                    if len(row) >= 3:
                        instrument_code = row[0].strip().strip('"')
                        price_value = float(row[1].replace(',', '.').strip())
                        price_date = row[2].strip()


                        instrument_code = instrument_code.strip().strip('"')
                        # Chercher l'instrument
                        instrument = self.env['efund.fund.instrument'].search([('isin', '=', instrument_code)], limit=1)



                        if not instrument:
                            errors.append(f"Ligne {i}: Instrument '{instrument_code}' non trouvé")
                            continue

                        # Convertir la date
                        from datetime import datetime
                        try:
                            date_obj = datetime.strptime(price_date, '%Y-%m-%d').date()
                        except:
                            date_obj = fields.Date.today()

                        # Créer ou mettre à jour le prix
                        existing = self.env['efund.fund.instrument.price'].search([
                            ('instrument_id', '=', instrument.id),
                            ('date', '=', date_obj)
                        ], limit=1)

                        if existing:
                            existing.write({
                                'price': price_value,
                                'currency_id': instrument.currency_id.id,
                            })
                        else:
                            self.env['efund.fund.instrument.price'].create({
                                'instrument_id': instrument.id,
                                'date': date_obj,
                                'price': price_value,
                                'currency_id': instrument.currency_id.id,
                                'is_validated': False,
                            })

                        imported += 1

                except Exception as e:
                    errors.append(f"Ligne {i}: {str(e)}")

            # Message de résultat
            message = f"{imported} cours importés/mis à jour."
            if errors:
                message += f"\n{len(errors)} erreurs."
                if len(errors) <= 5:
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
                }
            }

        except Exception as e:
            raise UserError(_("Erreur lors de l'import: %s") % str(e))

    def _import_from_api(self):
        """Importer depuis une API"""
        if not self.api_config_id:
            raise UserError(_("Veuillez sélectionner une configuration API"))

        return self.api_config_id.action_import_prices()