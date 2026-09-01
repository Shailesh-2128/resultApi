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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'Market'
        verbose_name_plural = 'Markets'

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

