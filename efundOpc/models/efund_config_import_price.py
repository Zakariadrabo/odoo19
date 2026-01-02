# efund_fund_instrument_price_import.py
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError
import base64
import io
import logging
import csv
import json
from datetime import datetime

_logger = logging.getLogger(__name__)


class FundInstrumentPriceImport(models.Model):
    _name = "efund.fund.instrument.price.import"
    _description = "Configuration d'import des cours"

    name = fields.Char(string="Nom de la configuration", required=True)
    import_method = fields.Selection([
        ('excel', 'Fichier Excel/CSV'),
        ('api', 'API de marché'),
        ('manual', 'Saisie manuelle')
    ], string="Méthode d'import", default='excel', required=True)

    # Configuration pour l'import Excel/CSV
    excel_file = fields.Binary(string="Fichier Excel/CSV")
    filename = fields.Char(string="Nom du fichier")

    # Configuration pour l'API
    api_url = fields.Char(string="URL de l'API")
    api_key = fields.Char(string="Clé API")
    api_parameters = fields.Text(string="Paramètres API")

    # Informations d'import
    last_import_date = fields.Datetime(string="Dernier import")
    import_log = fields.Text(string="Log d'import")
    active = fields.Boolean(string="Actif", default=True)

    def action_import_prices(self):
        """Lancer l'import des prix"""
        self.ensure_one()

        if self.import_method == 'excel':
            return self._import_from_file()
        elif self.import_method == 'api':
            return self._import_from_api()
        else:
            raise UserError(_("Méthode d'import non supportée"))

    def _import_from_file(self):
        """Importer depuis un fichier"""
        if not self.excel_file:
            raise UserError(_("Veuillez d'abord charger un fichier"))

        try:
            file_content = base64.b64decode(self.excel_file)
            text_content = file_content.decode('utf-8', errors='ignore')

            # Lire le CSV
            csv_file = io.StringIO(text_content)
            reader = csv.reader(csv_file, delimiter=',')

            prices_created = []
            errors = []

            for i, row in enumerate(reader, 1):
                try:
                    if i == 1 and len(row) > 0 and 'instrument' in row[0].lower():
                        continue  # Sauter l'en-tête

                    if len(row) >= 3:
                        instrument_code = row[0].strip()
                        price_value = float(row[1].replace(',', '.').strip())
                        price_date = row[2].strip()

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

                        # Convertir la date
                        try:
                            date_obj = datetime.strptime(price_date, '%Y-%m-%d').date()
                        except:
                            date_obj = fields.Date.today()

                        # Vérifier si le cours existe déjà
                        existing = self.env['efund.fund.instrument.price'].search([
                            ('instrument_id', '=', instrument.id),
                            ('date', '=', date_obj)
                        ], limit=1)

                        if existing:
                            existing.write({
                                'price': price_value,
                                'currency_id': instrument.currency_id.id
                            })
                            prices_created.append(existing.id)
                        else:
                            # Créer un nouveau prix
                            price = self.env['efund.fund.instrument.price'].create({
                                'instrument_id': instrument.id,
                                'date': date_obj,
                                'price': price_value,
                                'currency_id': instrument.currency_id.id,
                                'is_validated': False,
                            })
                            prices_created.append(price.id)

                except Exception as e:
                    errors.append(f"Ligne {i}: {str(e)}")

            # Mettre à jour le log
            log_message = f"Import terminé le {fields.Datetime.now()}\n"
            log_message += f"Cours importés/mis à jour: {len(prices_created)}\n"
            log_message += f"Erreurs: {len(errors)}\n"

            if errors:
                log_message += "\nErreurs:\n"
                for error in errors[:10]:
                    log_message += f"- {error}\n"

            self.import_log = log_message
            self.last_import_date = fields.Datetime.now()

            # Retourner les prix créés
            if prices_created:
                return {
                    'name': _('Cours importés'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'efund.fund.instrument.price',
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', prices_created)],
                    'context': {'create': False},
                }
            else:
                raise UserError(_("Aucun cours n'a été importé. Vérifiez les erreurs dans le log."))

        except Exception as e:
            _logger.error(f"Erreur lors de l'import: {str(e)}", exc_info=True)
            raise UserError(_("Erreur lors de l'import du fichier: %s") % str(e))

    def _import_from_api(self):
        """Importer depuis une API"""
        if not self.api_url:
            raise UserError(_("URL API non configurée"))

        try:
            import requests

            headers = {}
            if self.api_key:
                headers['Authorization'] = f"Bearer {self.api_key}"

            params = {}
            if self.api_parameters:
                try:
                    params = json.loads(self.api_parameters)
                except:
                    pass

            response = requests.get(
                self.api_url,
                headers=headers,
                params=params,
                timeout=30
            )

            if response.status_code != 200:
                raise UserError(_("Erreur API: %s - %s") % (response.status_code, response.text))

            # Traiter la réponse (à adapter selon l'API)
            data = response.json()

            # Exemple de traitement pour Yahoo Finance style
            prices_created = []

            if 'quoteResponse' in data and 'result' in data['quoteResponse']:
                for item in data['quoteResponse']['result']:
                    symbol = item.get('symbol', '')
                    price_value = item.get('regularMarketPrice', 0)

                    if symbol and price_value:
                        instrument = self.env['efund.fund.instrument'].search([
                            ('ticker', '=', symbol)
                        ], limit=1)

                        if instrument:
                            price = self.env['efund.fund.instrument.price'].create({
                                'instrument_id': instrument.id,
                                'date': fields.Date.today(),
                                'price': price_value,
                                'currency_id': instrument.currency_id.id,
                                'is_validated': False,
                            })
                            prices_created.append(price.id)

            # Mettre à jour le log
            log_message = f"Import API terminé le {fields.Datetime.now()}\n"
            log_message += f"Cours importés: {len(prices_created)}\n"

            self.import_log = log_message
            self.last_import_date = fields.Datetime.now()

            if prices_created:
                return {
                    'name': _('Cours importés via API'),
                    'type': 'ir.actions.act_window',
                    'res_model': 'efund.fund.instrument.price',
                    'view_mode': 'tree,form',
                    'domain': [('id', 'in', prices_created)],
                    'context': {'create': False},
                }
            else:
                raise UserError(_("Aucun cours n'a été importé depuis l'API."))

        except Exception as e:
            _logger.error(f"Erreur lors de l'import API: {str(e)}", exc_info=True)
            raise UserError(_("Erreur lors de l'import API: %s") % str(e))

    def action_test_connection(self):
        """Tester la connexion API"""
        self.ensure_one()

        if self.import_method != 'api':
            raise UserError(_("Cette action n'est disponible que pour les imports API"))

        try:
            import requests

            headers = {}
            if self.api_key:
                headers['Authorization'] = f"Bearer {self.api_key}"

            params = {}
            if self.api_parameters:
                try:
                    params = json.loads(self.api_parameters)
                except:
                    pass

            response = requests.get(
                self.api_url,
                headers=headers,
                params=params,
                timeout=10
            )

            if response.status_code == 200:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _('Connexion réussie'),
                        'message': _('La connexion à l\'API a réussi. Code: %s') % response.status_code,
                        'type': 'success',
                        'sticky': False,
                    }
                }
            else:
                raise UserError(_("Erreur de connexion: %s") % response.status_code)

        except Exception as e:
            raise UserError(_("Erreur de connexion: %s") % str(e))




class FundInstrumentPriceImportMapping(models.Model):
    _name = "efund.fund.instrument.price.import.mapping"
    _description = "Mapping des colonnes pour l'import"

    import_config_id = fields.Many2one('efund.fund.instrument.price.import', required=True)
    field_name = fields.Selection([
        ('instrument_code', 'Code de l\'instrument'),
        ('instrument_name', 'Nom de l\'instrument'),
        ('price', 'Cours'),
        ('date', 'Date'),
        ('currency', 'Devise'),
        ('volume', 'Volume'),
        ('high', 'Plus haut'),
        ('low', 'Plus bas'),
        ('open', 'Ouverture'),
        ('close', 'Clôture'),
    ], string="Champ Odoo", required=True)

    column_name = fields.Char(string="Nom de la colonne dans le fichier", required=True)
    column_index = fields.Integer(string="Index de la colonne (0-based)")
    required = fields.Boolean(string="Requis", default=True)

