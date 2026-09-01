import datetime
from django.test import TestCase
from django.db.utils import IntegrityError
from django.utils import timezone
from markets.models import Market, Result, FetchAttempt, FetchStatus, ResultType


class MarketModelTest(TestCase):
    def setUp(self):
        self.market = Market.objects.create(
            name="Test Market",
            external_name="test_market",
            open_time=datetime.time(10, 0),
            close_time=datetime.time(15, 0),
            is_active=True
        )

    def test_market_creation_and_slug(self):
        self.assertEqual(self.market.slug, "test-market")
        self.assertTrue(self.market.is_active)
        self.assertEqual(str(self.market), "Test Market (Active)")

    def test_duplicate_slug_handling(self):
        duplicate_market = Market.objects.create(
            name="Test Market",
            external_name="test_market_2",
            open_time=datetime.time(11, 0),
            close_time=datetime.time(16, 0)
        )
        self.assertEqual(duplicate_market.slug, "test-market-1")


class ResultModelTest(TestCase):
    def setUp(self):
        self.market = Market.objects.create(
            name="Market Alpha",
            external_name="alpha",
            open_time=datetime.time(12, 0),
            close_time=datetime.time(18, 0)
        )
        self.today = timezone.now().date()

    def test_create_result_success(self):
        res = Result.objects.create(
            market=self.market,
            result_date=self.today,
            result_type=ResultType.OPEN,
            result_value="170-8"
        )
        self.assertEqual(res.result_value, "170-8")
        self.assertEqual(res.source, "API")

    def test_unique_constraint_prevent_duplicate_result(self):
        Result.objects.create(
            market=self.market,
            result_date=self.today,
            result_type=ResultType.OPEN,
            result_value="170-8"
        )
        with self.assertRaises(IntegrityError):
            Result.objects.create(
                market=self.market,
                result_date=self.today,
                result_type=ResultType.OPEN,
                result_value="170-9"
            )


class FetchAttemptModelTest(TestCase):
    def setUp(self):
        self.market = Market.objects.create(
            name="Market Beta",
            external_name="beta",
            open_time=datetime.time(14, 0),
            close_time=datetime.time(20, 0)
        )
        self.today = timezone.now().date()

    def test_fetch_attempt_creation(self):
        attempt = FetchAttempt.objects.create(
            market=self.market,
            result_date=self.today,
            result_type=ResultType.OPEN,
            status=FetchStatus.WAITING
        )
        self.assertEqual(attempt.attempt_count, 0)
        self.assertEqual(attempt.status, FetchStatus.WAITING)
