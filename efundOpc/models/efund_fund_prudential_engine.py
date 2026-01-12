from odoo import models, fields, api, _


class FundPrudentialEngine(models.AbstractModel):
    _name = 'efund.fund.prudential.engine'

    def compute_all_ratios(self, fund, date):
        self.compute_exposure_by_issuer(fund, date)
        self.compute_concentration(fund, date)
        self.compute_weighted_average_maturity(fund, date)
        self.compute_weighted_duration(fund, date)
        self.compute_liquidity_ratio(fund, date)

    def compute_ratios(self, fund, date):
        portfolio = fund.get_portfolio_at_date(date)
        nav = fund.get_nav(date)

        for ratio in self.env['efund.fund.prudential.ratio'].search([]):
            value = self._compute_ratio(ratio, portfolio, nav)
            self._save_result(fund, ratio, date, value)

    def compute_exposure_by_issuer(self, fund, date):
        assets = fund.get_assets(date)
        nav = fund.get_nav(date)
        if not nav:
            return

        exposures = {}
        for a in assets:
            exposures.setdefault(a.issuer_id, 0.0)
            exposures[a.issuer_id] += a.market_value

        ratio = self.env['efund.fund.prudential.ratio'].search([
            ('code', '=', 'EXPO_ISSUER')
        ], limit=1)

        limit = self.env['efund.fund.prudential.limit'].search([
            ('fund_id', '=', fund.id),
            ('ratio_id', '=', ratio.id),
        ], limit=1)



        for issuer, value in exposures.items():
            pct = (value / nav) * 100
            status = 'ok'
            if limit and pct > limit.max_value:
                status = 'breach'
            elif limit and pct > limit.max_value * 0.9:
                status = 'warning'

            self.env['efund.fund.prudential.result'].create({
                'fund_id': fund.id,
                'ratio_id': ratio.id,
                'date': date,
                'value': pct,
                'breakdown_key': issuer.name,
                'status': status,
            })

    def compute_concentration(self, fund, date, top_n=5):
        assets = fund.get_assets(date)
        nav = fund.get_nav(date)
        if not nav:
            return

        top_assets = assets.sorted(
            key=lambda a: a.market_value, reverse=True
        )[:top_n]

        concentration = sum(top_assets.mapped('market_value')) / nav * 100
        ratio = self.env['efund.fund.prudential.ratio'].search([
            ('code', '=', 'CONCENTRATION')
        ], limit=1)

        limit = self.env['efund.fund.prudential.limit'].search([
            ('fund_id', '=', fund.id),
            ('ratio_id', '=', ratio.id),
        ], limit=1)

        """
        for issuer, value in exposures.items():
            pct = (value / nav) * 100
            status = 'ok'
            if limit and pct > limit.max_value:
                status = 'breach'
            elif limit and pct > limit.max_value * 0.9:
                status = 'warning'
        """

        self.env['efund.fund.prudential.result'].create({
            'fund_id': fund.id,
            'ratio_id': ratio.id,
            'date': date,
            'value': concentration,
            'status': 'ok',
        })

    def compute_weighted_average_maturity(self, fund, date):
        assets = fund.get_assets(date).filtered(lambda a: a.maturity_date)
        nav = fund.get_nav(date)
        if not nav:
            return

        today = date
        wam = 0.0

        for a in assets:
            days_to_maturity = (a.maturity_date - today).days
            years = max(days_to_maturity / 365, 0)
            wam += (a.market_value / nav) * years

        ratio = self.env.ref('efundOpc.ratio_wam')

        self.env['efund.fund.prudential.result'].create({
            'fund_id': fund.id,
            'ratio_id': ratio.id,
            'date': date,
            'value': wam,
            'status': 'ok',
        })

    def compute_weighted_duration(self, fund, date):
        assets = fund.get_assets(date).filtered(lambda a: a.duration)
        nav = fund.get_nav(date)
        if not nav:
            return

        duration = sum(
            (a.market_value / nav) * a.duration
            for a in assets
        )

        ratio = self.env.ref('efundOpc.ratio_duration')

        self.env['efund.fund.prudential.result'].create({
            'fund_id': fund.id,
            'ratio_id': ratio.id,
            'date': date,
            'value': duration,
            'status': 'ok',
        })

    def compute_liquidity_ratio(self, fund, date, allowed_buckets=('d0', 'd1', 'd7')):
        assets = fund.get_assets(date)
        nav = fund.get_nav(date)
        if not nav:
            return

        liquid_value = sum(
            a.market_value for a in assets
            if a.liquidity_bucket in allowed_buckets
        )

        liquidity_ratio = (liquid_value / nav) * 100

        ratio = self.env.ref('efundOpc.ratio_liquidity')

        self.env['efund.fund.prudential.result'].create({
            'fund_id': fund.id,
            'ratio_id': ratio.id,
            'date': date,
            'value': liquidity_ratio,
            'status': 'ok',
        })

