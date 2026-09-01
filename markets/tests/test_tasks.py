import datetime
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.utils import timezone
from markets.models import Market, Result, FetchAttempt, FetchStatus, ResultType
from markets.services.result_api import ResultAPIClient
from markets.services.result_fetcher import ResultFetcherService
from markets.tasks import check_and_schedule_result_fetches, fetch_market_result_task


class ServiceAndTaskTestCase(TestCase):
    def setUp(self):
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
        msg = check_and_schedule_result_fetches()
        self.assertTrue(mock_delay.called)
        self.assertIn("Scheduled", msg)
