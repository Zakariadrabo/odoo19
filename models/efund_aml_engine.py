# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
import logging
_logger = logging.getLogger(__name__)

class FundAmlEngine(models.AbstractModel):
    _name = 'efund.aml.engine'
    _description = 'AML Scoring Engine'

    @api.model
    def compute_score_for_investor(self, investor_id):
        inv = self.env['fund.investor'].browse(investor_id)
        score = 0
        # Base score from documents completeness
        docs = inv.document_ids
        required_types = {'id_card','passport','proof_of_address'}
        present = set(d.document_type for d in docs if d.status in ('verified','uploaded'))
        doc_score = int(20 * (len(present & required_types) / len(required_types)))
        score += doc_score  # up to 20

        # PEP / sanctions checks
        if inv.sanctions_flag:
            score += 100
        if inv.pep_flag:
            score += 50

        # Transactional behavior (simple heuristics)
        tx_model = self.env['fund.transaction']
        recent_tx_total = tx_model.search([('partner_id','=',inv.partner_id.id),('date','>=', fields.Date.today().replace(day=1))]).mapped('amount')
        try:
            recent_total = sum([abs(a) for a in recent_tx_total]) if recent_tx_total else 0.0
        except Exception:
            recent_total = 0.0
        if recent_total > 100000:  # configurable threshold
            score += 30

        # Risk country heuristic (example)
        partner = inv.partner_id
        if partner.country_id and partner.country_id.code in ['KP','IR','SY']:  # example high risk
            score += 25

        # Ensure bounds
        if score > 150:
            score = 150
        return int(score)
