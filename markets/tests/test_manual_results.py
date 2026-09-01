from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from markets.models import Market, Result, FetchAttempt, FetchStatus, ResultType

User = get_user_model()


class ManualResultManagementTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(username='admin', password='password123', is_staff=True)
        self.non_staff_user = User.objects.create_user(username='regular', password='password123')

        self.market = Market.objects.create(
            name='Kalyan Night',
            external_name='kalyan_night',
            open_time='21:30',
            close_time='23:30',
            is_active=True
        )
        self.test_date = date(2026, 9, 1)

    def test_non_staff_access_denied(self):
        self.client.login(username='regular', password='password123')
        response = self.client.get(reverse('markets:result_manage'))
        self.assertEqual(response.status_code, 403)

    def test_staff_access_result_manage(self):
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('markets:result_manage') + f'?date={self.test_date}')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Kalyan Night')

    def test_add_manual_open_result_inline(self):
        self.client.login(username='admin', password='password123')
        response = self.client.post(reverse('markets:result_manage'), {
            'market_id': self.market.id,
            'result_date': str(self.test_date),
            'result_type': ResultType.OPEN,
            'result_value': '123-6'
        })
        self.assertEqual(response.status_code, 302)

        # Check Result created
        res = Result.objects.get(market=self.market, result_date=self.test_date, result_type=ResultType.OPEN)
        self.assertEqual(res.result_value, '123-6')
        self.assertEqual(res.source, 'Manual')

        # Check FetchAttempt updated to SUCCESS
        attempt = FetchAttempt.objects.get(market=self.market, result_date=self.test_date, result_type=ResultType.OPEN)
        self.assertEqual(attempt.status, FetchStatus.SUCCESS)

    def test_add_manual_close_result_inline(self):
        self.client.login(username='admin', password='password123')
        response = self.client.post(reverse('markets:result_manage'), {
            'market_id': self.market.id,
            'result_date': str(self.test_date),
            'result_type': ResultType.CLOSE,
            'result_value': '123-68-350'
        })
        self.assertEqual(response.status_code, 302)

        res = Result.objects.get(market=self.market, result_date=self.test_date, result_type=ResultType.CLOSE)
        self.assertEqual(res.result_value, '123-68-350')
        self.assertEqual(res.source, 'Manual')

    def test_delete_manual_result(self):
        self.client.login(username='admin', password='password123')
        res = Result.objects.create(
            market=self.market,
            result_date=self.test_date,
            result_type=ResultType.OPEN,
            result_value='123-6',
            source='Manual'
        )

        response = self.client.post(reverse('markets:result_delete', kwargs={'pk': res.pk}))
        self.assertEqual(response.status_code, 302)
        self.assertFalse(Result.objects.filter(pk=res.pk).exists())

    def test_manual_result_create_view_form_submit(self):
        self.client.login(username='admin', password='password123')
        response = self.client.post(reverse('markets:result_create'), {
            'market': self.market.id,
            'result_date': str(self.test_date),
            'result_type': ResultType.OPEN,
            'result_value': '456-5'
        })
        self.assertEqual(response.status_code, 302)

        res = Result.objects.get(market=self.market, result_date=self.test_date, result_type=ResultType.OPEN)
        self.assertEqual(res.result_value, '456-5')
        self.assertEqual(res.source, 'Manual')

    def test_invalid_open_result_format(self):
        self.client.login(username='admin', password='password123')
        response = self.client.post(reverse('markets:result_create'), {
            'market': self.market.id,
            'result_date': str(self.test_date),
            'result_type': ResultType.OPEN,
            'result_value': 'invalid-format'
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Result.objects.filter(market=self.market, result_date=self.test_date).exists())
