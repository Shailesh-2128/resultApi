import logging
import re
import time
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger('markets')

_last_request_timestamp = 0.0


class ResultAPIClient:
    """
    Client for interacting with external Matka API (https://www.matkaapi.com/mapi/market_api.php).
    Implements:
    1. Local 45-second response caching for valid results.
    2. Enforced 5-second gap lock per request.
    3. Strict Regex format validation:
       - OPEN: 3-digit number - 1 digit number (e.g. 234-9)
       - CLOSE: 3-digit number - 2-digit number - 3-digit number (e.g. 234-99-289)
    """

    def __init__(self, api_url=None, api_key=None, api_domain=None, connect_timeout=5, read_timeout=10):
        self.api_url = api_url or getattr(settings, 'RESULT_API_URL', '')
        self.api_key = api_key or getattr(settings, 'RESULT_API_KEY', '')
        self.api_domain = api_domain or getattr(settings, 'RESULT_API_DOMAIN', '')
        self.timeout = (connect_timeout, read_timeout)
        self.session = requests.Session()

    def _enforce_rate_limit(self):
        """Enforces a minimum 5-second gap between outbound API calls to comply with rate rules"""
        if getattr(settings, 'TESTING', False):
            return

        global _last_request_timestamp
        now = time.time()
        elapsed = now - _last_request_timestamp
        min_gap = float(getattr(settings, 'RESULT_POLL_INTERVAL', 5.0))

        if elapsed < min_gap and _last_request_timestamp > 0:
            wait_time = min_gap - elapsed
            logger.info(f"Enforcing Matka API rate limit: sleeping {wait_time:.1f}s to maintain {min_gap}s gap")
            time.sleep(wait_time)

        _last_request_timestamp = time.time()

    def fetch_result(self, external_name: str, result_date_str: str, result_type: str) -> dict:
        """
        Fetch result for a market on a specific date and type (OPEN/CLOSE).
        Checks 45-second response cache before making external HTTP requests.
        """
        if not self.api_url or 'example.com' in self.api_url:
            logger.info(f"API client in mock/dev mode for market='{external_name}' date='{result_date_str}' type='{result_type}'")
            return self._mock_response(external_name, result_date_str, result_type)

        clean_market_code = external_name.lower().replace(' ', '').replace('-', '')
        
        # 1. Check Local 45-Second Cache to match Matka API 45s server cache
        cache_key = f"matka_api_cache_{clean_market_code}_{result_date_str}_{result_type.upper()}"
        cached_res = cache.get(cache_key)
        if cached_res:
            logger.info(f"Returning 45s cached Matka API result for market={clean_market_code}, type={result_type}")
            return cached_res

        # 2. Enforce 10-second gap lock before making outbound call
        self._enforce_rate_limit()

        params = {
            'market': clean_market_code,
            'domain_key': self.api_key,
        }
        if self.api_domain:
            params['domain'] = self.api_domain
        if result_date_str:
            params['date'] = result_date_str

        headers = {
            'Accept': 'application/json',
            'User-Agent': 'ResultsManagementSystem/1.0',
        }

        masked_key = self.api_key[:4] + '***' if self.api_key else ''
        logger.info(f"Calling Matka API {self.api_url} for market={clean_market_code}, date={result_date_str}, domain={self.api_domain}")

        try:
            response = self.session.get(
                self.api_url,
                headers=headers,
                params=params,
                timeout=self.timeout
            )

            status_code = response.status_code

            if status_code == 429:
                logger.warning(f"Rate limited (429) by Matka API for market={clean_market_code}")
                return {
                    "success": False,
                    "available": False,
                    "result_value": None,
                    "response_status": 429,
                    "error": "Rate limited by Matka API (10s gap required). Retrying shortly."
                }

            if status_code == 200:
                try:
                    data = response.json()
                except ValueError as json_err:
                    logger.error(f"Invalid JSON returned from Matka API: {json_err}")
                    return {
                        "success": False,
                        "available": False,
                        "result_value": None,
                        "response_status": status_code,
                        "error": f"Invalid JSON response: {str(json_err)}"
                    }

                msg = str(data.get('message', '')).lower()
                if 'rate_limited' in msg or '10 sec gap' in msg or 'flood' in msg:
                    logger.warning(f"Rate limit / Flood message in response body: {msg}")
                    return {
                        "success": False,
                        "available": False,
                        "result_value": None,
                        "response_status": 429,
                        "error": f"Matka API Rate Limit: {data.get('message')}. Retrying after gap."
                    }

                api_status = data.get('status', False)
                data_list = data.get('data', [])

                if api_status and isinstance(data_list, list) and len(data_list) > 0:
                    market_item = data_list[0]
                    raw_result = market_item.get('result', '').strip()
                    res_dict = self._process_raw_result(raw_result, result_type, status_code)
                    
                    # Store in 45-second cache
                    if res_dict.get('available'):
                        cache.set(cache_key, res_dict, timeout=45)
                    return res_dict

                # Fallback: Query market=all to find market by string matching
                fallback_res = self._fetch_all_markets_fallback(external_name, result_date_str, result_type, headers)
                if fallback_res.get('available'):
                    cache.set(cache_key, fallback_res, timeout=45)
                    return fallback_res

                msg_str = data.get('message') or "Result not declared yet"
                res_dict = {
                    "success": True,
                    "available": False,
                    "result_value": None,
                    "response_status": status_code,
                    "error": f"Matka API: {msg_str}"
                }
                # Cache negative response for 5s to match 5-second polling interval
                cache.set(cache_key, res_dict, timeout=5)
                return res_dict

            else:
                logger.warning(f"Matka API returned HTTP status {status_code} for market={clean_market_code}")
                return {
                    "success": False,
                    "available": False,
                    "result_value": None,
                    "response_status": status_code,
                    "error": f"HTTP {status_code} error from Matka API"
                }

        except requests.exceptions.Timeout:
            logger.error(f"Timeout calling Matka API for market={clean_market_code}")
            return {
                "success": False,
                "available": False,
                "result_value": None,
                "response_status": None,
                "error": "Matka API connection/read timeout"
            }
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Network request error calling Matka API for market={clean_market_code}: {req_err}")
            return {
                "success": False,
                "available": False,
                "result_value": None,
                "response_status": None,
                "error": f"Connection error: {str(req_err)}"
            }

    def _fetch_all_markets_fallback(self, external_name: str, result_date_str: str, result_type: str, headers: dict) -> dict:
        """
        Fallback search querying market=all with 5-second cache timeout.
        """
        all_cache_key = f"matka_api_cache_all_{result_date_str}"
        all_data = cache.get(all_cache_key)

        if not all_data:
            self._enforce_rate_limit()
            params = {
                'market': 'all',
                'domain_key': self.api_key,
            }
            if self.api_domain:
                params['domain'] = self.api_domain

            try:
                resp = self.session.get(self.api_url, headers=headers, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    data = resp.json()
                    if data.get('status') and isinstance(data.get('data'), list):
                        all_data = data['data']
                        cache.set(all_cache_key, all_data, timeout=5)
            except Exception as e:
                logger.debug(f"Fallback fetch all markets failed: {e}")

        if all_data:
            target_name_clean = external_name.lower().replace(' ', '').replace('-', '')
            for item in all_data:
                item_name_clean = item.get('name', '').lower().replace(' ', '').replace('-', '')
                if target_name_clean in item_name_clean or item_name_clean in target_name_clean:
                    raw_result = item.get('result', '').strip()
                    return self._process_raw_result(raw_result, result_type, 200)

        return {"success": True, "available": False, "result_value": None, "response_status": 200, "error": "Not found"}

    def _process_raw_result(self, raw_result: str, result_type: str, status_code: int) -> dict:
        raw_str = str(raw_result).strip() if raw_result else ''
        if not raw_str or raw_str.lower() in ['- -', '-', 'loading', 'loading...', 'null', 'none']:
            return {
                "success": True,
                "available": False,
                "result_value": None,
                "response_status": status_code,
                "error": f"{result_type} result loading... / not declared yet by market provider"
            }

        parsed_val = self._parse_matka_result(raw_str, result_type)
        if parsed_val:
            return {
                "success": True,
                "available": True,
                "result_value": parsed_val,
                "response_status": status_code,
                "error": None
            }
        return {
            "success": True,
            "available": False,
            "result_value": None,
            "response_status": status_code,
            "error": f"{result_type} result loading... / format not valid yet: '{raw_result}'"
        }

    def _parse_matka_result(self, raw_result: str, result_type: str):
        if not raw_result:
            return None

        clean_raw = raw_result.strip()
        parts = clean_raw.split('-')

        if result_type in ['OPEN', 'FIRST']:
            # Open result format must be 3 digits - 1 digit e.g. 234-9
            # Matka API can return "234-9", "234-9*", "234-9*-***", "234-99-289", "234-9**-***"
            if len(parts) >= 2:
                p0 = parts[0].strip()
                p1 = parts[1].strip()
                if re.match(r'^\d{3}$', p0) and p1 and re.match(r'^\d$', p1[0]):
                    candidate = f"{p0}-{p1[0]}"
                    return candidate
            elif len(parts) == 1:
                candidate = parts[0].strip()
                if re.match(r'^\d{3}-\d$', candidate):
                    return candidate
            return None
        else:
            # Close result format must be 3 digits - 2 digits - 3 digits e.g. 234-99-289
            # If string contains stars (*) or open-only result like "234-9*", it is NOT a valid close result yet
            if len(parts) == 3:
                p0 = parts[0].strip()
                p1 = parts[1].strip()
                p2 = parts[2].strip()
                if re.match(r'^\d{3}$', p0) and re.match(r'^\d{2}$', p1) and re.match(r'^\d{3}$', p2):
                    candidate = f"{p0}-{p1}-{p2}"
                    return candidate
            return None

    def _mock_response(self, external_name: str, result_date_str: str, result_type: str) -> dict:
        hash_val = abs(hash(f"{external_name}-{result_date_str}-{result_type}"))
        p1 = (hash_val % 900) + 100
        p2 = hash_val % 10
        if result_type in ['OPEN', 'FIRST']:
            mock_val = f"{p1}-{p2}"
        else:
            p3 = (hash_val % 90) + 10
            p4 = (hash_val % 900) + 100
            mock_val = f"{p1}-{p3}-{p4}"

        return {
            "success": True,
            "available": True,
            "result_value": mock_val,
            "response_status": 200,
            "error": None
        }
