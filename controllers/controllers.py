# from odoo import http


# class Efund(http.Controller):
#     @http.route('/efund/efund', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/efund/efund/objects', auth='public')
#     def list(self, **kw):
#         return http.request.render('efund.listing', {
#             'root': '/efund/efund',
#             'objects': http.request.env['efund.efund'].search([]),
#         })

#     @http.route('/efund/efund/objects/<model("efund.efund"):obj>', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('efund.object', {
#             'object': obj
#         })

