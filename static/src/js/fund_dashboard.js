odoo.define('efundOpc.fund_dashboard', function(require) {
    "use strict";

    const AbstractAction = require('web.AbstractAction');
    const core = require('web.core');
    const rpc = require('web.rpc');

    const FundDashboard = AbstractAction.extend({
        template: 'efund_fund_dashboard',

        init: function(parent, context) {
            this._super(parent, context);
            this.fund_id = context.context.active_id;
        },

        willStart: function() {
            return Promise.all([
                rpc.query({
                    model: 'efund.fund',
                    method: 'get_dashboard_data',
                    args: [this.fund_id],
                }).then(data => { this.dashboard_data = data; })
            ]);
        },

        start: function() {
            this.$el.html(
                core.qweb.render("efund_fund_dashboard", this.dashboard_data)
            );
        }
    });

    core.action_registry.add('efund_fund_dashboard', FundDashboard);
});
