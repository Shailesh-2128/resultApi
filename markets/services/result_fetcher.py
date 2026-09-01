import logging
from datetime import datetime, timedelta
from django.db import transaction
from django.utils import timezone
from django.conf import settings

from ..models import Market, Result, FetchAttempt, FetchStatus, ResultType
from .result_api import ResultAPIClient

logger = logging.getLogger('markets')


class ResultFetcherService:
    """
    Orchestrates checking database state, calling external API client, enforcing polling windows,
    updating audit logs (FetchAttempt), and saving results idempotently inside transactions.
    """

    def __init__(self, api_client=None):
        self.api_client = api_client or ResultAPIClient()

    def process_fetch(self, market_id: int, result_date, result_type: str) -> dict:
        """
        Execute fetch cycle for a specific market, date, and result_type.
        """
        try:
            market = Market.objects.get(id=market_id)
        except Market.DoesNotExist:
            logger.error(f"Market with id={market_id} does not exist.")
            return {"status": FetchStatus.FAILED, "message": "Market not found"}

        if not market.is_active:
            logger.info(f"Market '{market.name}' is inactive. Skipping fetch.")
            return {"status": FetchStatus.WAITING, "message": "Market inactive"}

        date_str = result_date.strftime('%Y-%m-%d') if isinstance(result_date, (datetime, timezone.datetime)) else str(result_date)

        # 1. Idempotency Check: Stop if result already exists in database
        existing_result = Result.objects.filter(
            market=market,
            result_date=result_date,
            result_type=result_type
        ).first()

        if existing_result:
            logger.info(f"Result already present in DB for {market.name} [{date_str} {result_type}]: {existing_result.result_value}")
            self._update_fetch_attempt(
                market=market,
                result_date=result_date,
                result_type=result_type,
                status=FetchStatus.SUCCESS,
                response_status=200,
                error_message=None
            )
            return {"status": FetchStatus.SUCCESS, "result": existing_result.result_value}

        # 2. FetchAttempt Audit & Polling Window Check
        with transaction.atomic():
            attempt, created = FetchAttempt.objects.select_for_update().get_or_create(
                market=market,
                result_date=result_date,
                result_type=result_type,
                defaults={
                    'status': FetchStatus.WAITING,
                    'attempt_count': 0
                }
            )

            # If already succeeded earlier, exit
            if attempt.status == FetchStatus.SUCCESS:
                return {"status": FetchStatus.SUCCESS, "message": "Already fetched"}

            now = timezone.now()

            # Check timeout condition: max poll minutes exceeded since first attempt
            max_minutes = getattr(settings, 'RESULT_MAX_POLL_MINUTES', 30)
            max_retries = getattr(settings, 'RESULT_MAX_RETRIES', 100)

            if attempt.created_at and (now - attempt.created_at) > timedelta(minutes=max_minutes):
                attempt.status = FetchStatus.TIMEOUT
                attempt.error_message = f"Maximum polling window of {max_minutes} minutes exceeded."
                attempt.save()
                logger.warning(f"Polling timeout reached for {market.name} [{date_str} {result_type}]")
                return {"status": FetchStatus.TIMEOUT, "message": attempt.error_message}

            if attempt.attempt_count >= max_retries:
                attempt.status = FetchStatus.TIMEOUT
                attempt.error_message = f"Maximum retry limit of {max_retries} attempts reached."
                attempt.save()
                logger.warning(f"Max retries reached for {market.name} [{date_str} {result_type}]")
                return {"status": FetchStatus.TIMEOUT, "message": attempt.error_message}

            # Update status to FETCHING
            attempt.status = FetchStatus.FETCHING
            attempt.attempt_count += 1
            attempt.last_attempt_at = now
            poll_interval = getattr(settings, 'RESULT_POLL_INTERVAL', 15)
            attempt.next_attempt_at = now + timedelta(seconds=poll_interval)
            attempt.save()

        # 3. Call External API
        api_res = self.api_client.fetch_result(
            external_name=market.external_name,
            result_date_str=date_str,
            result_type=result_type
        )

        success = api_res.get('success', False)
        available = api_res.get('available', False)
        result_value = api_res.get('result_value')
        response_status = api_res.get('response_status')
        error_msg = api_res.get('error')

        # 4. Process Response & Database Atomic Save
        with transaction.atomic():
            attempt = FetchAttempt.objects.select_for_update().get(id=attempt.id)
            attempt.response_status = response_status

            if success and available and result_value:
                # Save result idempotently using get_or_create inside atomic block
                res_obj, res_created = Result.objects.get_or_create(
                    market=market,
                    result_date=result_date,
                    result_type=result_type,
                    defaults={
                        'result_value': result_value,
                        'source': 'API',
                        'fetched_at': timezone.now()
                    }
                )
                attempt.status = FetchStatus.SUCCESS
                attempt.error_message = None
                attempt.save()
                logger.info(f"Successfully fetched and saved result for {market.name} [{date_str} {result_type}]: {result_value}")
                return {"status": FetchStatus.SUCCESS, "result": result_value}

            elif success and not available:
                attempt.status = FetchStatus.NOT_AVAILABLE
                attempt.error_message = error_msg or "Result not published yet"
                attempt.save()
                logger.info(f"Result not yet available for {market.name} [{date_str} {result_type}]")
                return {"status": FetchStatus.NOT_AVAILABLE, "message": attempt.error_message}

            else:
                attempt.status = FetchStatus.FAILED
                attempt.error_message = error_msg or "API fetch failed"
                attempt.save()
                logger.error(f"Fetch failed for {market.name} [{date_str} {result_type}]: {error_msg}")
                return {"status": FetchStatus.FAILED, "message": attempt.error_message}

    def _update_fetch_attempt(self, market, result_date, result_type, status, response_status, error_message):
        FetchAttempt.objects.update_or_create(
            market=market,
            result_date=result_date,
            result_type=result_type,
            defaults={
                'status': status,
                'response_status': response_status,
                'error_message': error_message,
                'last_attempt_at': timezone.now()
            }
        )
