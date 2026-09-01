import datetime
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from django.core.cache import cache
from markets.models import Market, Result, FetchAttempt, FetchStatus, ResultType
from markets.services.result_api import ResultAPIClient
from markets.services.result_fetcher import ResultFetcherService
from markets.tasks import check_and_schedule_result_fetches, fetch_market_result_task


class ServiceAndTaskTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.market = Market.objects.create(
            name="Test Service Market",
            external_name="test_service_mkt",
            open_time=datetime.time(0, 0),
            close_time=datetime.time(0, 0),
            is_active=True
        )
        self.today = timezone.now().date()

    @patch('markets.services.result_api.requests.Session.get')
    def test_result_api_client_success(self, mock_get):
        cache.clear()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": True,
            "data": [{"result": "789-0"}]
        }
        mock_get.return_value = mock_response

        client = ResultAPIClient(api_url="https://live-api.com/results")
        res = client.fetch_result("test_service_mkt", "2026-08-31", "OPEN")

        self.assertTrue(res["success"])
        self.assertTrue(res["available"])
        self.assertEqual(res["result_value"], "789-0")

    @patch('markets.services.result_api.requests.Session.get')
    def test_result_fetcher_service_idempotent_save(self, mock_get):
        cache.clear()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": True,
            "data": [{"result": "456-7"}]
        }
        mock_get.return_value = mock_response

        client = ResultAPIClient(api_url="https://live-api.com/results")
        fetcher = ResultFetcherService(api_client=client)

        out1 = fetcher.process_fetch(self.market.id, self.today, ResultType.OPEN)
        self.assertEqual(out1["status"], FetchStatus.SUCCESS)
        self.assertEqual(Result.objects.filter(market=self.market, result_date=self.today).count(), 1)

        out2 = fetcher.process_fetch(self.market.id, self.today, ResultType.OPEN)
        self.assertEqual(out2["status"], FetchStatus.SUCCESS)
        self.assertEqual(Result.objects.filter(market=self.market, result_date=self.today).count(), 1)

    @patch('markets.tasks.fetch_market_result_task.delay')
    def test_check_and_schedule_result_fetches_task(self, mock_delay):
        cache.clear()
        msg = check_and_schedule_result_fetches()
        self.assertTrue(mock_delay.called)
        self.assertIn("Scheduled", msg)

    @patch('markets.services.result_api.requests.Session.get')
    def test_open_and_close_format_validation(self, mock_get):
        cache.clear()
        client = ResultAPIClient(api_url="https://live-api.com/results")

        # Open result format valid: 234-9
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": True, "data": [{"result": "234-9"}]}
        mock_get.return_value = mock_response
        res_open = client.fetch_result("test_service_mkt", "2026-08-31", "OPEN")
        self.assertTrue(res_open["available"])
        self.assertEqual(res_open["result_value"], "234-9")

        # Open result when API returns full close string e.g. 234-99-289 -> extracts 234-9
        cache.clear()
        mock_response.json.return_value = {"status": True, "data": [{"result": "234-99-289"}]}
        res_open_full = client.fetch_result("test_service_mkt", "2026-08-31", "OPEN")
        self.assertTrue(res_open_full["available"])
        self.assertEqual(res_open_full["result_value"], "234-9")

        # Close result format valid: 234-99-289
        cache.clear()
        mock_response.json.return_value = {"status": True, "data": [{"result": "234-99-289"}]}
        res_close = client.fetch_result("test_service_mkt", "2026-08-31", "CLOSE")
        self.assertTrue(res_close["available"])
        self.assertEqual(res_close["result_value"], "234-99-289")

        # Close result when API only returns open result e.g. 234-9 -> close result loading
        cache.clear()
        mock_response.json.return_value = {"status": True, "data": [{"result": "234-9"}]}
        res_close_loading = client.fetch_result("test_service_mkt", "2026-08-31", "CLOSE")
        self.assertFalse(res_close_loading["available"])

        # API returns loading response or stars
        cache.clear()
        mock_response.json.return_value = {"status": True, "data": [{"result": "***-**-***"}]}
        res_loading = client.fetch_result("test_service_mkt", "2026-08-31", "OPEN")
        self.assertFalse(res_loading["available"])

    @patch('markets.services.result_api.requests.Session.get')
    def test_infinite_retries_high_attempt_count(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": True, "data": [{"result": "***-**-***"}]}
        mock_get.return_value = mock_response

        client = ResultAPIClient(api_url="https://live-api.com/results")
        fetcher = ResultFetcherService(api_client=client)

        # Create a FetchAttempt with 1500 attempts (past 1000)
        attempt, _ = FetchAttempt.objects.get_or_create(
            market=self.market,
            result_date=self.today,
            result_type=ResultType.OPEN,
            defaults={'attempt_count': 1500, 'status': FetchStatus.WAITING}
        )
        attempt.attempt_count = 1500
        attempt.save()

        res = fetcher.process_fetch(self.market.id, self.today, ResultType.OPEN)
        # Should not throw Timeout or Max retries limit
        self.assertEqual(res["status"], FetchStatus.NOT_AVAILABLE)
        attempt.refresh_from_db()
        self.assertEqual(attempt.attempt_count, 1501)
