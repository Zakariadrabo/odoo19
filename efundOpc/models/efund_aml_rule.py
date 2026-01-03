from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
from datetime import datetime, date, timedelta
import json
import logging
_logger = logging.getLogger(__name__)

class FundAmlRule(models.Model):
    _name = "efund.aml.rule"
    _description = "AML Rule (configurable)"

    name = fields.Char(required=True)
    description = fields.Text()
    active = fields.Boolean(default=True)
    rule_type = fields.Selection([('threshold','Threshold'),('velocity','Velocity'),('pattern','Pattern'),('pep','PEP'),
        ('sanctions','Sanctions'),('custom','Custom Python')
    ], default='threshold', required=True)
    params = fields.Text(help="JSON parameters for the rule, e.g. {'amount':10000}")
    severity_default = fields.Selection([('info','Info'),('medium','Medium'),('high','High'),('critical','Critical')], default='medium')

    def evaluate_for_transaction(self, tx):
        """
        Evaluate rule against a transaction (fund.transaction).
        Returns (boolean_triggered, details dict)
        """
        params = {}
        try:
            if self.params:
                params = json.loads(self.params)
        except Exception:
            _logger.exception("Invalid params for AML rule %s", self.id)
        if self.rule_type == 'threshold':
            amount = float(params.get('amount', 0))
            if abs(tx.amount) >= amount:
                return True, {'amount': tx.amount, 'threshold': amount}
            return False, {}
        if self.rule_type == 'velocity':
            days = int(params.get('days', 7))
            total = self.env['fund.transaction'].search_sum_amount(tx.investor_id.id, tx.date - timedelta(days=days), tx.date)
            if total >= float(params.get('amount', 0)):
                return True, {'period_days': days, 'total': total}
            return False, {}
        # Other types can be implemented...
        return False, {}