import logging
import re
import time
import requests
from django.conf import settings
from django.core.cache import cache
import socket
import urllib3.util.connection as urllib3_conn

# Force urllib3 to resolve IPv4 addresses to match whitelist rules
urllib3_conn.allowed_gai_family = lambda: socket.AF_INET

logger = logging.getLogger('markets')

_last_request_timestamp = 0.0


class ResultAPIClient:
    """
    Client for interacting with external Matka APIs:
    1. Primary: Matka Webhook API (https://matkawebhook.matkaapi.net/market-data)
       - Authenticates with username and password via /get-refresh-token.
       - Automates rotating token lifecycle (each call caches the new refresh token).
       - Self-heals if token expires or is rejected.
       - Extracts exact 3-digit and 1-digit open/close figures (e.g. 150-6 or 227-18-440).
    2. Legacy / Fallback: Matka API (https://www.matkaapi.com/mapi/market_api.php)
       - Maintained for backward compatibility and test suite fixtures.
    """

    def __init__(
        self,
        api_url=None,
        api_key=None,
        api_domain=None,
        webhook_data_url=None,
        webhook_token_url=None,
        username=None,
        password=None,
        connect_timeout=5,
        read_timeout=10
    ):
        self.api_url = api_url or getattr(settings, 'RESULT_API_URL', '')
        self.api_key = api_key or getattr(settings, 'RESULT_API_KEY', '')
        self.api_domain = api_domain or getattr(settings, 'RESULT_API_DOMAIN', '')

        self.webhook_data_url = webhook_data_url or getattr(settings, 'MATKA_API_DATA_URL', 'https://matkawebhook.matkaapi.net/market-data')
        self.webhook_token_url = webhook_token_url or getattr(settings, 'MATKA_API_TOKEN_URL', 'https://matkawebhook.matkaapi.net/get-refresh-token')
        self.username = username or getattr(settings, 'MATKA_API_USERNAME', '7769971133')
        self.password = password or getattr(settings, 'MATKA_API_PASSWORD', '123')

        self.timeout = (connect_timeout, read_timeout)
        self.session = requests.Session()

    def is_webhook_mode(self) -> bool:
        """Determines whether to use the new rotating-token webhook API."""
        if self.api_url:
            if 'matkawebhook' in self.api_url:
                return True
            if 'matkaapi.com' in self.api_url or 'live-api.com' in self.api_url or 'example.com' in self.api_url:
                return False
        return bool(self.webhook_data_url and self.username and self.password)

    def _enforce_rate_limit(self):
        """Enforces a minimum interval between outbound API calls to prevent flooding."""
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

    def _parse_response_json(self, response):
        """
        Parses JSON from HTTP response. Handles third-party API issues where PHP warnings,
        notices, HTML tags, BOMs, or extra text are prepended or appended to JSON responses.
        Returns tuple (data_dict_or_list_or_None, error_message_str_or_None).
        """
        raw_text = response.text if response is not None else ""
        if not raw_text or not raw_text.strip():
            return None, "Empty response body from Matka API"

        # 1. Direct JSON parse
        try:
            return response.json(), None
        except Exception:
            pass

        # 2. Extract JSON payload substring (handles PHP warnings/notices printed before JSON)
        text = raw_text.strip()
        first_brace = text.find('{')
        first_bracket = text.find('[')

        indices = [i for i in (first_brace, first_bracket) if i != -1]
        if indices:
            start = min(indices)
            last_brace = text.rfind('}')
            last_bracket = text.rfind(']')
            end = max(last_brace, last_bracket)

            if end > start:
                json_candidate = text[start:end + 1]
                try:
                    import json
                    parsed = json.loads(json_candidate)
                    logger.info("Successfully extracted and parsed embedded JSON from API response containing extra text/warnings")
                    return parsed, None
                except Exception as err:
                    logger.warning(f"Failed to parse extracted JSON candidate: {err}")

        # 3. Handle HTML error pages (e.g. Cloudflare / Nginx 403 / WAF / Server Error)
        if any(tag in text.lower() for tag in ['<html', '<body', '<title', '<br']):
            match = re.search(r'<title>(.*?)</title>', text, re.IGNORECASE | re.DOTALL)
            if match:
                clean_title = match.group(1).strip()
                return None, f"Matka API returned HTML page: '{clean_title}'"
            return None, "Matka API returned HTML instead of JSON"

        # 4. Fallback snippet error
        snippet = text[:100].replace('\n', ' ').strip()
        return None, f"Invalid JSON response from Matka API: '{snippet}'"

    # =========================================================================
    # Matka Webhook API (Rotating Token Flow)
    # =========================================================================

    def get_or_refresh_token(self, force_refresh=False) -> str:
        """
        Retrieves the active refresh_token from cache, or fetches a new one from
        https://matkawebhook.matkaapi.net/get-refresh-token.
        """
        cache_key = "matka_webhook_refresh_token"
        if not force_refresh:
            cached_token = cache.get(cache_key)
            if cached_token:
                return cached_token

        logger.info(f"Requesting new refresh token from {self.webhook_token_url} for user {self.username}")
        try:
            self._enforce_rate_limit()
            resp = self.session.post(
                self.webhook_token_url,
                data={'username': self.username, 'password': self.password},
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'ResultsManagementSystem/1.0'},
                timeout=self.timeout
            )
            data, err = self._parse_response_json(resp)
            if data and data.get('status') and data.get('refresh_token'):
                new_token = data['refresh_token']
                cache.set(cache_key, new_token, timeout=86400 * 7)
                logger.info(f"Successfully acquired and cached new Matka Webhook refresh token: {new_token[:4]}***")
                return new_token
            logger.error(f"Failed to acquire refresh token: {data or err or resp.text}")
            return None
        except Exception as e:
            logger.error(f"Error fetching refresh token from {self.webhook_token_url}: {e}")
            return None

    def fetch_webhook_market_data(self, external_name: str, result_date_str: str) -> tuple:
        """
        Calls /market-data with automatic token rotation and recovery.
        Returns tuple (data_dict_or_None, status_code, error_message).
        """
        token = self.get_or_refresh_token()
        if not token:
            return None, 401, "Unable to obtain Matka Webhook API token"

        def _do_post(active_token):
            self._enforce_rate_limit()
            post_data = {
                'username': self.username,
                'API_token': active_token,
                'markte_name': external_name or '',
                'date': result_date_str
            }
            return self.session.post(
                self.webhook_data_url,
                data=post_data,
                headers={'Content-Type': 'application/x-www-form-urlencoded', 'User-Agent': 'ResultsManagementSystem/1.0'},
                timeout=self.timeout
            )

        try:
            resp = _do_post(token)
            status_code = resp.status_code
            data, err = self._parse_response_json(resp)

            # Check if token was rejected or expired (recover automatically)
            if data and not data.get('status') and 'token not valid' in str(data.get('message', '')).lower():
                logger.warning("Token expired or invalid on Matka Webhook API. Refreshing token and retrying...")
                fresh_token = self.get_or_refresh_token(force_refresh=True)
                if not fresh_token:
                    return None, 401, "Token renewal failed"
                resp = _do_post(fresh_token)
                status_code = resp.status_code
                data, err = self._parse_response_json(resp)

            if not data:
                return None, status_code, err or "Invalid response from Matka Webhook API"

            # Always update cache with the next rotated refresh token if returned
            next_token = data.get('refresh_token')
            if next_token:
                cache.set("matka_webhook_refresh_token", next_token, timeout=86400 * 7)

            if not data.get('status'):
                return None, status_code, data.get('message') or "Matka Webhook reported failure"

            return data, status_code, None

        except requests.exceptions.Timeout:
            logger.error("Timeout connecting to Matka Webhook API")
            return None, 504, "Matka Webhook connection/read timeout"
        except requests.exceptions.RequestException as e:
            logger.error(f"Network error calling Matka Webhook API: {e}")
            return None, 502, f"Connection error: {str(e)}"

    def _extract_result_from_webhook_data(self, data: dict, external_name: str, result_type: str) -> dict:
        """
        Extracts formatted OPEN (3-1) or CLOSE (3-2-3) result string from Webhook payload.
        """
        all_results = data.get('today_result', []) or []
        if not all_results and data.get('old_result'):
            all_results = data.get('old_result', [])

        target_clean = external_name.lower().replace(' ', '').replace('-', '')
        matched_item = None

        for item in all_results:
            m_name = str(item.get('market_name', '')).lower().replace(' ', '').replace('-', '')
            if m_name == target_clean or target_clean in m_name or m_name in target_clean:
                matched_item = item
                break

        if not matched_item:
            return {
                "success": True,
                "available": False,
                "result_value": None,
                "response_status": 200,
                "error": f"Market '{external_name}' not found in webhook results for specified date"
            }

        aankdo_open = str(matched_item.get('aankdo_open') or '').strip()
        figure_open = str(matched_item.get('figure_open') or '').strip()
        aankdo_close = str(matched_item.get('aankdo_close') or '').strip()
        figure_close = str(matched_item.get('figure_close') or '').strip()
        jodi = str(matched_item.get('jodi') or '').strip()
        if not jodi and figure_open and figure_close:
            jodi = f"{figure_open}{figure_close}"

        if result_type in ['OPEN', 'FIRST']:
            # Must have 3-digit aankdo_open and 1-digit figure_open (e.g. 150-6)
            if re.match(r'^\d{3}$', aankdo_open) and re.match(r'^\d$', figure_open):
                candidate = f"{aankdo_open}-{figure_open}"
                return {
                    "success": True,
                    "available": True,
                    "result_value": candidate,
                    "response_status": 200,
                    "error": None
                }
            return {
                "success": True,
                "available": False,
                "result_value": None,
                "response_status": 200,
                "error": "OPEN result not declared yet by market provider"
            }
        else:
            # CLOSE must have 3-digit aankdo_open, 2-digit jodi, and 3-digit aankdo_close (e.g. 227-18-440)
            if re.match(r'^\d{3}$', aankdo_open) and re.match(r'^\d{2}$', jodi) and re.match(r'^\d{3}$', aankdo_close):
                candidate = f"{aankdo_open}-{jodi}-{aankdo_close}"
                return {
                    "success": True,
                    "available": True,
                    "result_value": candidate,
                    "response_status": 200,
                    "error": None
                }
            return {
                "success": True,
                "available": False,
                "result_value": None,
                "response_status": 200,
                "error": "CLOSE result not declared yet by market provider"
            }

    # =========================================================================
    # Main Fetch Method (Orchestrates Webhook vs Legacy)
    # =========================================================================

    def fetch_result(self, external_name: str, result_date_str: str, result_type: str) -> dict:
        """
        Fetch result for a market on a specific date and type (OPEN/CLOSE).
        Checks local response cache before making external HTTP requests.
        """
        if not self.api_url and not self.webhook_data_url or 'example.com' in self.api_url:
            logger.info(f"API client in mock/dev mode for market='{external_name}' date='{result_date_str}' type='{result_type}'")
            return self._mock_response(external_name, result_date_str, result_type)

        clean_market_code = external_name.lower().replace(' ', '').replace('-', '')
        cache_key = f"matka_api_cache_{clean_market_code}_{result_date_str}_{result_type.upper()}"
        cached_res = cache.get(cache_key)
        if cached_res:
            logger.info(f"Returning cached Matka API result for market={clean_market_code}, type={result_type}")
            return cached_res

        # 1. Primary: Matka Webhook API Flow
        if self.is_webhook_mode():
            logger.info(f"Fetching from Matka Webhook API for market={clean_market_code}, date={result_date_str}, type={result_type}")
            data, status_code, err = self.fetch_webhook_market_data(external_name, result_date_str)
            if not data:
                res_dict = {
                    "success": False,
                    "available": False,
                    "result_value": None,
                    "response_status": status_code,
                    "error": err
                }
                return res_dict

            res_dict = self._extract_result_from_webhook_data(data, external_name, result_type)
            if res_dict.get('available'):
                cache.set(cache_key, res_dict, timeout=45)
            else:
                cache.set(cache_key, res_dict, timeout=5)
            return res_dict

        # 2. Legacy / Fallback: GET Request Flow
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

        try:
            response = self.session.get(
                self.api_url,
                headers=headers,
                params=params,
                timeout=self.timeout
            )
            status_code = response.status_code

            if status_code == 429:
                return {
                    "success": False,
                    "available": False,
                    "result_value": None,
                    "response_status": 429,
                    "error": "Rate limited by Matka API. Retrying shortly."
                }

            if status_code == 200:
                data, json_error = self._parse_response_json(response)
                if not data:
                    return {
                        "success": False,
                        "available": False,
                        "result_value": None,
                        "response_status": status_code,
                        "error": json_error or "Invalid JSON response from Matka API"
                    }

                msg = str(data.get('message', '')).lower()
                if 'rate_limited' in msg or '10 sec gap' in msg or 'flood' in msg:
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
                    if res_dict.get('available'):
                        cache.set(cache_key, res_dict, timeout=45)
                    return res_dict

                # Legacy Fallback: Query market=all
                fallback_res = self._fetch_all_markets_fallback(external_name, result_date_str, result_type, headers)
                if fallback_res.get('available'):
                    cache.set(cache_key, fallback_res, timeout=45)
                    return fallback_res

                msg_str = data.get('message') or "Result not declared yet"
                your_ip = data.get('your_ip')
                allowed_ip = data.get('allowed_ip')
                if your_ip and allowed_ip:
                    msg_str = f"{msg_str} (Your Server IP: {your_ip}, Whitelisted IP: {allowed_ip})"

                is_auth_or_config_err = not api_status and any(
                    k in msg_str.lower() for k in ['ip', 'domain', 'key', 'whitelist', 'invalid', 'denied', 'unauthorized']
                )

                res_dict = {
                    "success": False if is_auth_or_config_err else True,
                    "available": False,
                    "result_value": None,
                    "response_status": status_code,
                    "error": f"Matka API: {msg_str}"
                }
                if not is_auth_or_config_err:
                    cache.set(cache_key, res_dict, timeout=5)
                return res_dict

            return {
                "success": False,
                "available": False,
                "result_value": None,
                "response_status": status_code,
                "error": f"HTTP {status_code} error from Matka API"
            }

        except requests.exceptions.Timeout:
            return {
                "success": False,
                "available": False,
                "result_value": None,
                "response_status": None,
                "error": "Matka API connection/read timeout"
            }
        except requests.exceptions.RequestException as req_err:
            return {
                "success": False,
                "available": False,
                "result_value": None,
                "response_status": None,
                "error": f"Connection error: {str(req_err)}"
            }

    def _fetch_all_markets_fallback(self, external_name: str, result_date_str: str, result_type: str, headers: dict) -> dict:
        """Fallback search querying legacy market=all."""
        all_cache_key = f"matka_api_cache_all_{result_date_str}"
        all_data = cache.get(all_cache_key)

        if not all_data:
            self._enforce_rate_limit()
            params = {'market': 'all', 'domain_key': self.api_key}
            if self.api_domain:
                params['domain'] = self.api_domain

            try:
                resp = self.session.get(self.api_url, headers=headers, params=params, timeout=self.timeout)
                if resp.status_code == 200:
                    data, _ = self._parse_response_json(resp)
                    if data and data.get('status') and isinstance(data.get('data'), list):
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
            if len(parts) >= 2:
                p0 = parts[0].strip()
                p1 = parts[1].strip()
                if re.match(r'^\d{3}$', p0) and p1 and re.match(r'^\d$', p1[0]):
                    return f"{p0}-{p1[0]}"
            elif len(parts) == 1:
                candidate = parts[0].strip()
                if re.match(r'^\d{3}-\d$', candidate):
                    return candidate
            return None
        else:
            if len(parts) == 3:
                p0 = parts[0].strip()
                p1 = parts[1].strip()
                p2 = parts[2].strip()
                if re.match(r'^\d{3}$', p0) and re.match(r'^\d{2}$', p1) and re.match(r'^\d{3}$', p2):
                    return f"{p0}-{p1}-{p2}"
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
