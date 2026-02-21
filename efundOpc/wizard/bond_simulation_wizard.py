from odoo import models, fields, api, _
from datetime import timedelta
import base64
import io
import xlsxwriter



class BondSimulationWizard(models.TransientModel):
    _name = 'efund.bond.simulation.wizard'
    _description = 'Simulation du Cours Listé'

    bond_id = fields.Many2one('efund.vehicule.instrument.core.bond', string="Obligation", required=True)

    # Saisies utilisateur
    acquisition_date = fields.Date(string="Date d'acquisition", required=True)
    acquisition_price = fields.Float(string="Prix d'acquisition (%)", required=True, default=100.0)

    date_start = fields.Date(string="Date début simulation", required=True)
    date_end = fields.Date(string="Date fin simulation", required=True)

    excel_file = fields.Binary(string="Fichier Excel", readonly=True)
    file_name = fields.Char(string="Nom du fichier", readonly=True)

    def action_simulate(self):
        self.ensure_one()

        # Récupération des données du titre
        face_value = self.bond_id.face_value
        maturity_date = self.bond_id.maturity_date

        simulation_results = []

        # Logique de simulation simple : Progression linéaire vers le nominal (100%)
        # On calcule la pente : (Nominal - Prix Acquisition) / Jours restants jusqu'à maturité
        total_days_to_maturity = (maturity_date - self.acquisition_date).days
        price_diff = 100.0 - self.acquisition_price
        daily_increment = price_diff / total_days_to_maturity if total_days_to_maturity > 0 else 0

        current_date = self.date_start
        while current_date <= self.date_end:
            # Calcul du prix simulé à la date T
            days_passed = (current_date - self.acquisition_date).days
            simulated_price_percent = self.acquisition_price + (daily_increment * days_passed)

            # Calcul de la valeur monétaire
            market_value = (simulated_price_percent / 100.0) * face_value

            simulation_results.append({
                'date': current_date,
                'price_percent': simulated_price_percent,
                'market_value': market_value,
            })
            current_date += timedelta(days=1)




    def action_generate_excel(self):
        self.ensure_one()

        # 1. Préparation du flux mémoire
        output = io.BytesIO()
        workbook = xlsxwriter.Workbook(output, {'in_memory': True})
        sheet = workbook.add_worksheet('Simulation Cours')

        # 2. Formats
        header_format = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
        date_format = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        num_format = workbook.add_format({'num_format': '#,##0.00'})

        # 3. En-têtes
        headers = ['Date', 'Cours (%)', 'Valeur de Marché']
        for col, header in enumerate(headers):
            sheet.write(0, col, header, header_format)

        # 4. Génération des données (Logique Pull-to-Par)
        bond = self.bond_id
        total_days = (bond.maturity_date - self.acquisition_date).days
        price_diff = 10000 - self.acquisition_price
        daily_inc = price_diff / total_days if total_days > 0 else 0

        row = 1
        curr_date = self.date_start
        while curr_date <= self.date_end:
            days_passed = (curr_date - self.acquisition_date).days
            price = self.acquisition_price + (daily_inc * days_passed)
            market_val = (price / 100.0) * bond.face_value

            sheet.write(row, 0, curr_date, date_format)
            sheet.write(row, 1, price, num_format)
            sheet.write(row, 2, market_val, num_format)

            curr_date += timedelta(days=1)
            row += 1

        workbook.close()
        output.seek(0)

        # 5. Enregistrement du fichier dans le wizard
        file_data = base64.b64encode(output.read())
        self.write({
            'excel_file': file_data,
            'file_name': f'Simulation_{bond.name}_{fields.Date.today()}.xlsx'
        })

        # 6. Retourner la vue pour afficher le lien de téléchargement
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'efund.bond.simulation.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
        }