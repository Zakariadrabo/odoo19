from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class FundKycDocument(models.Model):
    _name = "efund.kyc.document"
    _description = "KYC Document"
    _order = "id desc"

    investor_id = fields.Many2one('efund.investor', string="Investor", required=True, ondelete='cascade')
    document_type = fields.Selection([
        ('id_card','ID Card'),
        ('passport','Passport'),
        ('proof_of_address','Proof of Address'),
        ('company_doc','Company Documents'),
        ('ubo','UBO Document'),
        ('other','Other')
    ], required=True)
    file_id = fields.Many2one('ir.attachment', string="Attachment")
    filename = fields.Char(related='file_id.name', readonly=True)
    issued_date = fields.Date()
    expiry_date = fields.Date()
    verified_by = fields.Many2one('res.users', string="Verified By")
    verified_date = fields.Datetime()
    status = fields.Selection([('uploaded','Uploaded'),('verified','Verified'),('expired','Expired')], default='uploaded')
    notes = fields.Text()
    company_id = fields.Many2one('res.company', related='investor_id.company_id', store=True, readonly=True)

    @api.constrains('expiry_date')
    def _check_dates(self):
        for rec in self:
            if rec.expiry_date and rec.issued_date and rec.expiry_date < rec.issued_date:
                raise ValidationError(_("Document expiry date must be after issue date"))

    def action_verify(self):
        for rec in self:
            rec.status = 'verified'
            rec.verified_by = self.env.uid
            rec.verified_date = fields.Datetime.now()
            rec.message_post(body=_("Document verified: %s") % rec.document_type)

    def action_mark_expired(self):
        for rec in self:
            rec.status = 'expired'