import logging
from datetime import datetime, date
from celery import shared_task
from django.utils import timezone
from django.conf import settings

from .models import Market, Result, FetchAttempt, FetchStatus, ResultType
from .services.result_fetcher import ResultFetcherService

logger = logging.getLogger('celery')


@shared_task(bind=True, name='markets.tasks.check_and_schedule_result_fetches')
def check_and_schedule_result_fetches(self):
    """
    Scheduled beat task running every 60 seconds.
    Inspects all active markets, checks open_time and close_time against current local time,
    and dispatches fetch tasks for missing results.
    """
    current_tz = timezone.get_current_timezone()
    now_local = timezone.now().astimezone(current_tz)
    today_date = now_local.date()
    current_time = now_local.time()

    logger.info(f"Running periodic check at {now_local.strftime('%Y-%m-%d %H:%M:%S %Z')} for active markets")

    active_markets = Market.objects.filter(is_active=True)
    scheduled_count = 0

    for market in active_markets:
        # Check Open Time Schedule
        if current_time >= market.open_time:
            if _should_trigger_fetch(market, today_date, ResultType.OPEN):
                fetch_market_result_task.delay(market.id, str(today_date), ResultType.OPEN)
                scheduled_count += 1

        # Check Close Time Schedule
        if current_time >= market.close_time:
            if _should_trigger_fetch(market, today_date, ResultType.CLOSE):
                fetch_market_result_task.delay(market.id, str(today_date), ResultType.CLOSE)
                scheduled_count += 1

    logger.info(f"Periodic check completed. Scheduled {scheduled_count} fetch tasks.")
    return f"Scheduled {scheduled_count} tasks"


def _should_trigger_fetch(market, target_date, result_type: str) -> bool:
    """
    Determines whether a fetch task should be queued.
    Returns False if result already exists in DB or if fetch is actively running right now.
    """
    # 1. If result exists, do not trigger
    if Result.objects.filter(market=market, result_date=target_date, result_type=result_type).exists():
        return False

    # 2. Check FetchAttempt state
    attempt = FetchAttempt.objects.filter(market=market, result_date=target_date, result_type=result_type).first()
    if attempt:
        if attempt.status == FetchStatus.SUCCESS:
            return False
        # Avoid queuing duplicate tasks if fetch is actively running right now within poll interval
        if attempt.status == FetchStatus.FETCHING:
            poll_interval = getattr(settings, 'RESULT_POLL_INTERVAL', 5)
            if attempt.last_attempt_at and (timezone.now() - attempt.last_attempt_at).total_seconds() < poll_interval:
                return False

    return True


@shared_task(bind=True, max_retries=None, default_retry_delay=5, name='markets.tasks.fetch_market_result_task')
def fetch_market_result_task(self, market_id: int, result_date_str: str, result_type: str):
    """
    Celery background worker task for polling external API continuously for a specific result.
    """
    logger.info(f"Executing fetch_market_result_task for market_id={market_id}, date={result_date_str}, type={result_type}")
    
    try:
        target_date = datetime.strptime(result_date_str, '%Y-%m-%d').date()
    except ValueError:
        logger.error(f"Invalid date format: {result_date_str}")
        return "Invalid date format"

    fetcher = ResultFetcherService()
    res = fetcher.process_fetch(market_id, target_date, result_type)

    status = res.get('status')
    poll_interval = getattr(settings, 'RESULT_POLL_INTERVAL', 5)

    if status in [FetchStatus.NOT_AVAILABLE, FetchStatus.FAILED, FetchStatus.TIMEOUT]:
        retry_delay = max(5, poll_interval)
        logger.info(f"Result not ready/loading for market_id={market_id} [{result_date_str} {result_type}]. Scheduling retry in {retry_delay}s")
        raise self.retry(countdown=retry_delay, max_retries=None)

    return f"Fetch completed with status: {status}"
