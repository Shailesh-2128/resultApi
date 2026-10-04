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

