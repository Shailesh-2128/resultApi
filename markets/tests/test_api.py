import datetime
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from markets.models import Market, Result, ResultType


class MarketAPITestCase(APITestCase):
    def setUp(self):
        from markets.views import get_current_app_date
        self.market = Market.objects.create(
            name="API Market A",
            external_name="api_market_a",
            open_time=datetime.time(10, 0),
            close_time=datetime.time(16, 0),
            is_active=True
        )
        self.today = get_current_app_date()
        self.result = Result.objects.create(
            market=self.market,
            result_date=self.today,
            result_type=ResultType.OPEN,
            result_value="555-9"
        )

    def test_get_today_results(self):
        url = reverse('api:api_results_today')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('date', response.data)
        self.assertIn('results', response.data)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['open'], "555-9")

    def test_get_results_by_date(self):
        url = f"{reverse('api:api_results_date')}?date={self.today.strftime('%Y-%m-%d')}"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['date'], str(self.today))

    def test_get_results_invalid_date(self):
        url = f"{reverse('api:api_results_date')}?date=invalid-date"
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_markets_list(self):
        url = reverse('api:api_market_list')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['markets']), 1)
        self.assertEqual(response.data['markets'][0]['slug'], self.market.slug)

    def test_get_market_specific_results(self):
        url = reverse('api:api_market_results', kwargs={'slug': self.market.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['market'], self.market.name)
        self.assertEqual(len(response.data['results']), 1)

    def test_dashboard_access_staff(self):
        from django.contrib.auth.models import User
        staff_user = User.objects.create_user('staff', 'staff@test.com', 'password123', is_staff=True)
        self.client.force_login(staff_user)
        
        dashboard_url = reverse('markets:dashboard')
        response = self.client.get(dashboard_url)
        self.assertEqual(response.status_code, 200)

        add_url = reverse('markets:market_create')
        post_data = {
            'name': 'New Test Market',
            'external_name': 'new_test_market',
            'open_time': '12:00',
            'close_time': '18:00',
            'is_active': True
        }
        res_post = self.client.post(add_url, post_data)
        self.assertEqual(res_post.status_code, 302)
        self.assertTrue(Market.objects.filter(external_name='new_test_market').exists())

    def test_get_matka_all_results(self):
        url = reverse('api:api_results_all')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['status'])
        self.assertEqual(response.data['message'], 'success')
        self.assertEqual(len(response.data['data']), 1)
        self.assertEqual(response.data['data'][0]['result'], '555-9')

    def test_delete_market(self):
        from django.contrib.auth.models import User
        staff_user = User.objects.create_user('staff_del', 'del@test.com', 'pass123', is_staff=True)
        self.client.force_login(staff_user)

        del_url = reverse('markets:market_delete', kwargs={'pk': self.market.pk})
        res = self.client.post(del_url)
        self.assertEqual(res.status_code, 302)
        self.assertFalse(Market.objects.filter(pk=self.market.pk).exists())


class ResultAPIClientParsingTestCase(APITestCase):
    def setUp(self):
        from unittest.mock import MagicMock
        from markets.services.result_api import ResultAPIClient
        self.client_instance = ResultAPIClient(api_url="https://www.matkaapi.com/mapi/market_api.php", api_key="testkey", api_domain="quebix.in")

    def test_parse_json_with_php_warning_prefix(self):
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = (
            '<br />\n<b>Warning</b>: fopen(/cache/flood.json): Permission denied in <b>mapi_protect.php</b> on line 75<br />\n'
            '{"status":true,"message":"success","data":[{"name":"SRIDEVI","result":"234-9"}]}'
        )
        mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")

        with patch.object(self.client_instance.session, 'get', return_value=mock_resp):
            res = self.client_instance.fetch_result("SRIDEVI", "2026-10-04", "OPEN")
            self.assertTrue(res['success'])
            self.assertTrue(res['available'])
            self.assertEqual(res['result_value'], "234-9")

    def test_parse_ip_whitelist_error_with_php_warning(self):
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = (
            '<br />\n<b>Warning</b>: fopen(/cache/flood.json): Permission denied in <b>mapi_protect.php</b> line 75<br />\n'
            '{"status":false,"message":"Please update your IP from dashboard","your_ip":"2401:4900:891f::1","allowed_ip":"212.38.94.69"}'
        )
        mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")

        with patch.object(self.client_instance.session, 'get', return_value=mock_resp):
            res = self.client_instance.fetch_result("SRIDEVI", "2026-10-04", "OPEN")
            self.assertFalse(res['success'])
            self.assertFalse(res['available'])
            self.assertIn("Please update your IP from dashboard", res['error'])
            self.assertIn("Your Server IP: 2401:4900:891f::1", res['error'])
            self.assertIn("Whitelisted IP: 212.38.94.69", res['error'])

    def test_parse_html_error_page(self):
        from unittest.mock import patch, MagicMock
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html><head><title>403 Forbidden</title></head><body>Access Denied</body></html>"
        mock_resp.json.side_effect = ValueError("Expecting value: line 1 column 1 (char 0)")

        with patch.object(self.client_instance.session, 'get', return_value=mock_resp):
            res = self.client_instance.fetch_result("SRIDEVI", "2026-10-04", "OPEN")
            self.assertFalse(res['success'])
            self.assertIn("403 Forbidden", res['error'])


class MatkaWebhookClientTestCase(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        from markets.services.result_api import ResultAPIClient
        self.client = ResultAPIClient(
            api_url="https://matkawebhook.matkaapi.net/market-data",
            webhook_data_url="https://matkawebhook.matkaapi.net/market-data",
            webhook_token_url="https://matkawebhook.matkaapi.net/get-refresh-token",
            username="7769971133",
            password="123"
        )

    def test_webhook_fetch_result_open_and_close(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache

        # Pre-seed cached token
        cache.set("matka_webhook_refresh_token", "mock_token_123", timeout=3600)

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status":true,"message":"success","today_result":[{"market_name":"PADMAVATHI","aankdo_open":"150","figure_open":"6","aankdo_close":null,"figure_close":"","jodi":""}],"refresh_token":"mock_next_token"}'
        mock_resp.json.return_value = {
            "status": True,
            "message": "success",
            "today_result": [{
                "market_name": "PADMAVATHI",
                "aankdo_open": "150",
                "figure_open": "6",
                "aankdo_close": None,
                "figure_close": "",
                "jodi": ""
            }],
            "refresh_token": "mock_next_token"
        }

        with patch.object(self.client.session, 'post', return_value=mock_resp):
            # Test OPEN: Should be declared as 150-6
            res_open = self.client.fetch_result("PADMAVATHI", "2026-10-13", "OPEN")
            self.assertTrue(res_open['success'])
            self.assertTrue(res_open['available'])
            self.assertEqual(res_open['result_value'], "150-6")

            # Check that rotated refresh token was saved to cache
            self.assertEqual(cache.get("matka_webhook_refresh_token"), "mock_next_token")

            # Test CLOSE: Close figure is null, should be available=False
            cache.delete("matka_api_cache_padmavathi_2026-10-13_CLOSE")
            res_close = self.client.fetch_result("PADMAVATHI", "2026-10-13", "CLOSE")
            self.assertTrue(res_close['success'])
            self.assertFalse(res_close['available'])
            self.assertIn("CLOSE result not declared yet", res_close['error'])

    def test_webhook_token_recovery_on_invalid_token(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache

        cache.set("matka_webhook_refresh_token", "expired_token", timeout=3600)

        # 1st call to market-data fails with token invalid
        resp_invalid = MagicMock()
        resp_invalid.status_code = 200
        resp_invalid.json.return_value = {"status": False, "message": "Somthing wrong or token not valid"}
        resp_invalid.text = '{"status":false,"message":"Somthing wrong or token not valid"}'

        # call to get-refresh-token returns new token
        resp_token = MagicMock()
        resp_token.status_code = 200
        resp_token.json.return_value = {"status": True, "message": "success", "refresh_token": "renewed_token_999"}
        resp_token.text = '{"status":true,"message":"success","refresh_token":"renewed_token_999"}'

        # 2nd call to market-data succeeds
        resp_success = MagicMock()
        resp_success.status_code = 200
        resp_success.json.return_value = {
            "status": True,
            "message": "success",
            "today_result": [{
                "market_name": "PADMAVATHI",
                "aankdo_open": "227",
                "figure_open": "1",
                "aankdo_close": "440",
                "figure_close": "8",
                "jodi": "18"
            }],
            "refresh_token": "final_token_111"
        }
        resp_success.text = '{"status":true,"message":"success"}'

        with patch.object(self.client.session, 'post', side_effect=[resp_invalid, resp_token, resp_success]):
            res = self.client.fetch_result("PADMAVATHI", "2026-10-12", "CLOSE")
            self.assertTrue(res['success'])
            self.assertTrue(res['available'])
            self.assertEqual(res['result_value'], "227-18-440")
            self.assertEqual(cache.get("matka_webhook_refresh_token"), "final_token_111")


