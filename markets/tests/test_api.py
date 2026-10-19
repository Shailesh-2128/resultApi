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

    def test_query_params_and_headers_sent(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache
        cache.clear()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "status": True,
            "message": "success",
            "data": [{"name": "PADMAVATHI MORNING", "result": "150-6"}]
        }
        mock_resp.text = '{"status":true,"data":[{"name":"PADMAVATHI MORNING","result":"150-6"}]}'

        with patch.object(self.client_instance.session, 'get', return_value=mock_resp) as mock_get:
            res = self.client_instance.fetch_result("Padmavathi Morning", "2026-10-13", "OPEN")
            self.assertTrue(res['available'])
            self.assertEqual(res['result_value'], "150-6")
            
            mock_get.assert_called_once()
            args, kwargs = mock_get.call_args
            params = kwargs['params']
            self.assertEqual(params['market'], 'padmavathimorning')
            self.assertEqual(params['domain_key'], 'testkey')
            self.assertEqual(params['domain'], 'quebix.in')
            self.assertEqual(params['date'], '2026-10-13')

    def test_rate_limit_429_and_flood_response(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache
        cache.clear()

        # HTTP 429
        mock_429 = MagicMock()
        mock_429.status_code = 429
        mock_429.text = "Too Many Requests"
        with patch.object(self.client_instance.session, 'get', return_value=mock_429):
            res = self.client_instance.fetch_result("PADMAVATHI", "2026-10-13", "OPEN")
            self.assertFalse(res['success'])
            self.assertEqual(res['response_status'], 429)

        cache.clear()
        # 200 with flood message in body
        mock_flood = MagicMock()
        mock_flood.status_code = 200
        mock_flood.text = '{"status":false,"message":"Please wait 10 sec gap between requests"}'
        mock_flood.json.return_value = {"status": False, "message": "Please wait 10 sec gap between requests"}
        with patch.object(self.client_instance.session, 'get', return_value=mock_flood):
            res = self.client_instance.fetch_result("PADMAVATHI", "2026-10-13", "OPEN")
            self.assertFalse(res['success'])
            self.assertEqual(res['response_status'], 429)
            self.assertIn("10 sec gap", res['error'])

    def test_fallback_all_markets_query(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache
        cache.clear()

        # 1st call for single market returns empty data
        resp_single = MagicMock()
        resp_single.status_code = 200
        resp_single.json.return_value = {"status": True, "message": "success", "data": []}
        resp_single.text = '{"status":true,"data":[]}'

        # 2nd call for market=all returns list including target market
        resp_all = MagicMock()
        resp_all.status_code = 200
        resp_all.json.return_value = {
            "status": True,
            "message": "success",
            "data": [
                {"name": "KALYAN NIGHT", "result": "227-18-440"},
                {"name": "SRIDEVI", "result": "123-6"}
            ]
        }
        resp_all.text = '{"status":true}'

        with patch.object(self.client_instance.session, 'get', side_effect=[resp_single, resp_all]) as mock_get:
            res = self.client_instance.fetch_result("Kalyan-Night", "2026-10-13", "CLOSE")
            self.assertTrue(res['available'])
            self.assertEqual(res['result_value'], "227-18-440")
            self.assertEqual(mock_get.call_count, 2)


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


class MarketCollisionPreventionTestCase(APITestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        from markets.services.result_api import ResultAPIClient
        self.client_instance = ResultAPIClient(api_url="https://www.matkaapi.com/mapi/market_api.php", api_key="testkey", api_domain="quebix.in")

    def test_is_market_name_match_prevent_collisions(self):
        from markets.services.result_api import is_market_name_match

        # Sridevi vs Sridevi Night
        self.assertTrue(is_market_name_match("sridevi", "SRIDEVI"))
        self.assertTrue(is_market_name_match("sridevi_night", "SRIDEVI NIGHT"))
        self.assertTrue(is_market_name_match("sridevi-night", "SRIDEVI NIGHT"))
        self.assertFalse(is_market_name_match("sridevi", "SRIDEVI NIGHT"))
        self.assertFalse(is_market_name_match("sridevi_night", "SRIDEVI"))

        # Kalyan vs Kalyan Night
        self.assertTrue(is_market_name_match("kalyan", "KALYAN"))
        self.assertTrue(is_market_name_match("kalyan_night", "KALYAN NIGHT"))
        self.assertFalse(is_market_name_match("kalyan", "KALYAN NIGHT"))
        self.assertFalse(is_market_name_match("kalyan_night", "KALYAN"))

        # Milan Day vs Milan Night vs Milan Morning
        self.assertFalse(is_market_name_match("milan_day", "MILAN NIGHT"))
        self.assertFalse(is_market_name_match("milan_morning", "MILAN DAY"))
        self.assertFalse(is_market_name_match("milan_morning", "MILAN NIGHT"))
        self.assertTrue(is_market_name_match("milan_day", "MILAN DAY"))

        # Rajdhani Day vs Rajdhani Night
        self.assertFalse(is_market_name_match("rajdhani_day", "RAJDHANI NIGHT"))
        self.assertFalse(is_market_name_match("rajdhani_night", "RAJDHANI DAY"))

        # Time Bazar vs Main Bazar
        self.assertFalse(is_market_name_match("time_bazar", "MAIN BAZAR"))
        self.assertFalse(is_market_name_match("main_bazar", "TIME BAZAR"))

    def test_fallback_matches_sridevi_when_sridevi_night_is_first(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache
        cache.clear()

        resp_single = MagicMock()
        resp_single.status_code = 200
        resp_single.json.return_value = {"status": True, "message": "success", "data": []}
        resp_single.text = '{"status":true,"data":[]}'

        # In all_data, SRIDEVI NIGHT is listed BEFORE SRIDEVI
        resp_all = MagicMock()
        resp_all.status_code = 200
        resp_all.json.return_value = {
            "status": True,
            "message": "success",
            "data": [
                {"name": "SRIDEVI NIGHT", "result": "345-28-440"},
                {"name": "SRIDEVI", "result": "123-68-150"}
            ]
        }
        resp_all.text = '{"status":true}'

        with patch.object(self.client_instance.session, 'get', side_effect=[resp_single, resp_all]):
            # Querying SRIDEVI must return SRIDEVI (123-6), NEVER SRIDEVI NIGHT (345-2)!
            res = self.client_instance.fetch_result("sridevi", "2026-10-19", "OPEN")
            self.assertTrue(res['available'])
            self.assertEqual(res['result_value'], "123-6")

    def test_fallback_matches_sridevi_night_when_sridevi_is_first(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache
        cache.clear()

        resp_single = MagicMock()
        resp_single.status_code = 200
        resp_single.json.return_value = {"status": True, "message": "success", "data": []}
        resp_single.text = '{"status":true,"data":[]}'

        # In all_data, SRIDEVI is listed BEFORE SRIDEVI NIGHT
        resp_all = MagicMock()
        resp_all.status_code = 200
        resp_all.json.return_value = {
            "status": True,
            "message": "success",
            "data": [
                {"name": "SRIDEVI", "result": "123-68-150"},
                {"name": "SRIDEVI NIGHT", "result": "345-28-440"}
            ]
        }
        resp_all.text = '{"status":true}'

        with patch.object(self.client_instance.session, 'get', side_effect=[resp_single, resp_all]):
            # Querying SRIDEVI NIGHT must return SRIDEVI NIGHT (345-2), NEVER SRIDEVI (123-6)!
            res = self.client_instance.fetch_result("sridevi_night", "2026-10-19", "OPEN")
            self.assertTrue(res['available'])
            self.assertEqual(res['result_value'], "345-2")

    def test_single_market_rejects_colliding_name_in_data_list(self):
        from unittest.mock import patch, MagicMock
        from django.core.cache import cache
        cache.clear()

        # Third-party single market endpoint incorrectly returned SRIDEVI NIGHT when asked for sridevi
        resp_single = MagicMock()
        resp_single.status_code = 200
        resp_single.json.return_value = {
            "status": True,
            "message": "success",
            "data": [{"name": "SRIDEVI NIGHT", "result": "345-28-440"}]
        }
        resp_single.text = '{"status":true}'

        # Fallback queries market=all and returns both
        resp_all = MagicMock()
        resp_all.status_code = 200
        resp_all.json.return_value = {
            "status": True,
            "message": "success",
            "data": [
                {"name": "SRIDEVI NIGHT", "result": "345-28-440"},
                {"name": "SRIDEVI", "result": "123-68-150"}
            ]
        }
        resp_all.text = '{"status":true}'

        with patch.object(self.client_instance.session, 'get', side_effect=[resp_single, resp_all]):
            res = self.client_instance.fetch_result("sridevi", "2026-10-19", "OPEN")
            # Should reject SRIDEVI NIGHT from single endpoint and correctly find SRIDEVI from fallback
            self.assertTrue(res['available'])
            self.assertEqual(res['result_value'], "123-6")

    def test_api_results_all_sridevi_filter_does_not_return_sridevi_night(self):
        import datetime
        from markets.models import Market
        Market.objects.all().delete()
        m_sridevi = Market.objects.create(
            name="SRIDEVI",
            external_name="sridevi",
            open_time=datetime.time(11, 30),
            close_time=datetime.time(12, 30),
            is_active=True
        )
        m_sridevi_night = Market.objects.create(
            name="SRIDEVI NIGHT",
            external_name="sridevi_night",
            open_time=datetime.time(19, 0),
            close_time=datetime.time(20, 0),
            is_active=True
        )

        # Querying market=sridevi must ONLY return SRIDEVI, not SRIDEVI NIGHT
        url_sridevi = reverse('api:api_results_all') + '?market=sridevi'
        res_sridevi = self.client.get(url_sridevi)
        self.assertEqual(res_sridevi.status_code, 200)
        names = [item['name'] for item in res_sridevi.data['data']]
        self.assertEqual(names, ["SRIDEVI"])

        # Querying market=sridevi_night must ONLY return SRIDEVI NIGHT
        url_night = reverse('api:api_results_all') + '?market=sridevi_night'
        res_night = self.client.get(url_night)
        self.assertEqual(res_night.status_code, 200)
        names_night = [item['name'] for item in res_night.data['data']]
        self.assertEqual(names_night, ["SRIDEVI NIGHT"])



