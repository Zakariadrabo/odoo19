# from odoo import http


# class L10nFcp(http.Controller):
#     @http.route('/l10n_fcp/l10n_fcp', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/l10n_fcp/l10n_fcp/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('l10n_fcp.listing', {
#             'root': '/l10n_fcp/l10n_fcp',
#             'objects': http.request.env['l10n_fcp.l10n_fcp'].search([]),
#         })

#     @http.route('/l10n_fcp/l10n_fcp/objects/<model("l10n_fcp.l10n_fcp"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('l10n_fcp.object', {
#             'object': obj
#         })

