from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FundKycDocument(models.Model):
    _name = "efund.kyc.document"
    _description = "KYC Document"
    _order = "id desc"

    investor_id = fields.Many2one('efund.investor', string="Investor", required=True, ondelete='cascade')
    full_name = fields.Char(string="Investisseur", related='investor_id.full_name')
    company_name = fields.Char(related='investor_id.company_name', string="Raison sociale")
    investor_type = fields.Selection(related='investor_id.investor_type', string="Type")
    name=fields.Char('Nom du document')
    document_type = fields.Selection([
        ('id_card','Carte d\'identité'),
        ('passport','Passeport'),
        ('proof_of_address','Preuve d\'adresse'),
        ('company_doc','statut compagnie'),
        ('ubo','Document bénéficiaire effectif'),
        ('other','Autre')
    ],string="Type Document", required=True)
    file_id = fields.Many2one('ir.attachment', string="fichier")
    filename = fields.Char(related='file_id.name', readonly=True)
    issued_date = fields.Date(string="Date d'émission")
    expiry_date = fields.Date(string="Date d'expiration")
    verified_by = fields.Many2one('res.users', string="Verifié par")
    verified_date = fields.Datetime(string="Date de verification")
    state = fields.Selection([('draft','Brouillon'),('uploaded','Chargé'),('verified','Vérifié'),('expired','Expiré')], string="Statut", default='draft')
    notes = fields.Text(string="Notes")
    file_data = fields.Binary(string="File",attachment=True, )
    file_name_fname = fields.Char(string="File Name")

    @api.onchange('file_data')
    def _onchange_file_id(self):
        for rec in self:
            if rec.file_data:
                rec.state='uploaded'
            else:
                rec.state='draft'


    @api.constrains('expiry_date')
    def _check_dates(self):
        for rec in self:
            if rec.expiry_date and rec.issued_date and rec.expiry_date < rec.issued_date:
                raise ValidationError(_("Document expiry date must be after issue date"))

    def action_verify(self):
        for rec in self:
            rec.state = 'verified'
            rec.verified_by = self.env.uid
            rec.verified_date = fields.Datetime.now()
            rec.message_post(body=_("Document verified: %s") % rec.document_type)

    def action_mark_expired(self):
        for rec in self:
            rec.state = 'expired'

    def action_uploaded(self):
        for rec in self:
            if not rec.file_name:
                raise ValidationError(_("Merci de charger la preuve avant de continuer la validation."))
            else:
                rec.state='uploaded'

