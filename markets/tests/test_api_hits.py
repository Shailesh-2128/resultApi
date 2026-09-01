from datetime import date
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
from markets.models import DailyAPIHit

User = get_user_model()


class APIHitTrackingTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.staff_user = User.objects.create_user(username='admin', password='password123', is_staff=True)

    def test_api_results_all_increments_hit_count(self):
        url = reverse('markets:api_results_all')
        
        # Hit 1
        response1 = self.client.get(url)
        self.assertEqual(response1.status_code, 200)

        hit_record = DailyAPIHit.objects.filter(endpoint='/api/results/all/').first()
        self.assertIsNotNone(hit_record)
        self.assertEqual(hit_record.count, 1)

        # Hit 2
        response2 = self.client.get(url)
        self.assertEqual(response2.status_code, 200)

        hit_record.refresh_from_db()
        self.assertEqual(hit_record.count, 2)

    def test_dashboard_displays_api_hit_count(self):
        # Generate API hits
        url = reverse('markets:api_results_all')
        self.client.get(url)
        self.client.get(url)
        self.client.get(url)

        # Login to dashboard
        self.client.login(username='admin', password='password123')
        response = self.client.get(reverse('markets:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['stats']['today_api_hits'], 3)
        self.assertEqual(response.context['stats']['total_api_hits'], 3)
