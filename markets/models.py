from django.db import models
from django.utils.text import slugify
from django.utils import timezone


class ResultType(models.TextChoices):
    OPEN = 'OPEN', 'Open Result'
    CLOSE = 'CLOSE', 'Close Result'


class FetchStatus(models.TextChoices):
    WAITING = 'WAITING', 'Waiting'
    FETCHING = 'FETCHING', 'Fetching'
    SUCCESS = 'SUCCESS', 'Success'
    NOT_AVAILABLE = 'NOT_AVAILABLE', 'Not Available'
    FAILED = 'FAILED', 'Failed'
    TIMEOUT = 'TIMEOUT', 'Timeout'


class Market(models.Model):
    name = models.CharField(max_length=100, help_text="Public market name (e.g. Market A)")
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    external_name = models.CharField(max_length=100, help_text="Market identifier in external API (e.g. market_a)")
    open_time = models.TimeField(help_text="Open Result Time (HH:MM)")
    close_time = models.TimeField(help_text="Close Result Time (HH:MM)")
    is_active = models.BooleanField(default=True, help_text="Whether this market is active for result processing")
    active_monday = models.BooleanField(default=True, verbose_name="Monday")
    active_tuesday = models.BooleanField(default=True, verbose_name="Tuesday")
    active_wednesday = models.BooleanField(default=True, verbose_name="Wednesday")
    active_thursday = models.BooleanField(default=True, verbose_name="Thursday")
    active_friday = models.BooleanField(default=True, verbose_name="Friday")
    active_saturday = models.BooleanField(default=True, verbose_name="Saturday")
    active_sunday = models.BooleanField(default=True, verbose_name="Sunday")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Market'
        verbose_name_plural = 'Markets'

    def is_active_on_date(self, target_date) -> bool:
        """Determines if the market scheduler is active on a given calendar date."""
        if not self.is_active or not target_date:
            return False
        weekday = target_date.weekday()  # 0 = Monday, 1 = Tuesday, ..., 6 = Sunday
        days_map = {
            0: self.active_monday,
            1: self.active_tuesday,
            2: self.active_wednesday,
            3: self.active_thursday,
            4: self.active_friday,
            5: self.active_saturday,
            6: self.active_sunday,
        }
        return days_map.get(weekday, True)

    def get_active_days_display(self) -> str:
        """Returns a human-readable list or range of active operating days."""
        days = [
            ("Mon", self.active_monday),
            ("Tue", self.active_tuesday),
            ("Wed", self.active_wednesday),
            ("Thu", self.active_thursday),
            ("Fri", self.active_friday),
            ("Sat", self.active_saturday),
            ("Sun", self.active_sunday),
        ]
        active_names = [name for name, is_on in days if is_on]
        if len(active_names) == 7:
            return "All Days"
        elif len(active_names) == 0:
            return "None"
        elif active_names == ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            return "Mon - Fri"
        elif active_names == ["Sat", "Sun"]:
            return "Sat - Sun"
        return ", ".join(active_names)

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name)
            slug = base_slug
            counter = 1
            while Market.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"


class Result(models.Model):
    market = models.ForeignKey(Market, on_delete=models.CASCADE, related_name='results')
    result_date = models.DateField(help_text="Date of the market result")
    result_type = models.CharField(max_length=10, choices=ResultType.choices)
    result_value = models.CharField(max_length=50, help_text="Formatted result string e.g. 170-8 or 170-89-450")
    source = models.CharField(max_length=50, default='API', help_text="Source of the result (API, Manual)")
    fetched_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-result_date', 'market', 'result_type']
        verbose_name = 'Result'
        verbose_name_plural = 'Results'
        constraints = [
            models.UniqueConstraint(
                fields=['market', 'result_date', 'result_type'],
                name='unique_market_date_type_result'
            )
        ]
        indexes = [
            models.Index(fields=['market', 'result_date', 'result_type']),
            models.Index(fields=['result_date']),
        ]

    def __str__(self):
        return f"{self.market.name} - {self.result_date} - {self.result_type}: {self.result_value}"


class FetchAttempt(models.Model):
    market = models.ForeignKey(Market, on_delete=models.CASCADE, related_name='fetch_attempts')
    result_date = models.DateField()
    result_type = models.CharField(max_length=10, choices=ResultType.choices)
    status = models.CharField(max_length=20, choices=FetchStatus.choices, default=FetchStatus.WAITING)
    attempt_count = models.IntegerField(default=0)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(null=True, blank=True)
    response_status = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = 'Fetch Attempt'
        verbose_name_plural = 'Fetch Attempts'
        constraints = [
            models.UniqueConstraint(
                fields=['market', 'result_date', 'result_type'],
                name='unique_market_date_type_fetch_attempt'
            )
        ]

    def __str__(self):
        return f"{self.market.name} - {self.result_date} [{self.result_type}]: {self.status} (Attempts: {self.attempt_count})"


class DailyAPIHit(models.Model):
    endpoint = models.CharField(max_length=100, help_text="API endpoint identifier e.g. /api/results/all/")
    hit_date = models.DateField(help_text="Date of recorded API hits")
    count = models.PositiveIntegerField(default=0, help_text="Number of requests received on hit_date")
    last_hit_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-hit_date', 'endpoint']
        verbose_name = 'Daily API Hit'
        verbose_name_plural = 'Daily API Hits'
        constraints = [
            models.UniqueConstraint(
                fields=['endpoint', 'hit_date'],
                name='unique_endpoint_hit_date'
            )
        ]

    def __str__(self):
        return f"{self.endpoint} ({self.hit_date}): {self.count} hits"

