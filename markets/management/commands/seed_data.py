import datetime
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.utils import timezone
from markets.models import Market, Result, FetchAttempt, FetchStatus, ResultType

User = get_user_model()


class Command(BaseCommand):
    help = 'Seeds initial superuser, active markets, and sample result data for demonstration'

    def handle(self, *args, **options):
        self.stdout.write("Seeding data...")

        # 1. Create Superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
            self.stdout.write(self.style.SUCCESS("Superuser created: admin / admin123"))
        else:
            self.stdout.write("Superuser 'admin' already exists.")

        # 2. Create Sample Markets
        markets_data = [
            {
                "name": "Market A",
                "external_name": "market_a",
                "open_time": datetime.time(16, 20),
                "close_time": datetime.time(18, 20),
                "is_active": True,
            },
            {
                "name": "Market B",
                "external_name": "market_b",
                "open_time": datetime.time(14, 0),
                "close_time": datetime.time(20, 0),
                "is_active": True,
            },
            {
                "name": "Market C",
                "external_name": "market_c",
                "open_time": datetime.time(11, 30),
                "close_time": datetime.time(17, 30),
                "is_active": True,
            },
        ]

        created_markets = []
        for m_data in markets_data:
            market, created = Market.objects.get_or_create(
                name=m_data["name"],
                defaults=m_data
            )
            created_markets.append(market)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Market created: {market.name}"))

        # 3. Create Sample Today & History Results
        current_tz = timezone.get_current_timezone()
        today = timezone.now().astimezone(current_tz).date()
        yesterday = today - datetime.timedelta(days=1)

        # Market A Today Results
        Result.objects.get_or_create(
            market=created_markets[0],
            result_date=today,
            result_type=ResultType.OPEN,
            defaults={"result_value": "170-8", "source": "API"}
        )
        Result.objects.get_or_create(
            market=created_markets[0],
            result_date=today,
            result_type=ResultType.CLOSE,
            defaults={"result_value": "170-89-450", "source": "API"}
        )

        # Market B Today First Result
        Result.objects.get_or_create(
            market=created_markets[1],
            result_date=today,
            result_type=ResultType.OPEN,
            defaults={"result_value": "245-7", "source": "API"}
        )

        # Yesterday Results
        for m in created_markets:
            Result.objects.get_or_create(
                market=m,
                result_date=yesterday,
                result_type=ResultType.OPEN,
                defaults={"result_value": "123-4", "source": "API"}
            )
            Result.objects.get_or_create(
                market=m,
                result_date=yesterday,
                result_type=ResultType.CLOSE,
                defaults={"result_value": "123-45-678", "source": "API"}
            )

        # Audit Fetch Attempts
        FetchAttempt.objects.get_or_create(
            market=created_markets[0],
            result_date=today,
            result_type=ResultType.OPEN,
            defaults={
                "status": FetchStatus.SUCCESS,
                "attempt_count": 1,
                "last_attempt_at": timezone.now(),
                "response_status": 200
            }
        )

        self.stdout.write(self.style.SUCCESS("Database seeding completed successfully!"))
