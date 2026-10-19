from datetime import datetime, date
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Q, Sum, F
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Market, Result, FetchAttempt, FetchStatus, ResultType, DailyAPIHit
from .serializers import MarketSerializer, ResultSerializer, MarketDayResultsSerializer
from .forms import MarketForm, ManualResultForm
from .tasks import fetch_market_result_task
from .services.result_api import is_market_name_match, normalize_market_name


def get_current_app_date():
    """Helper to get current date in configured application timezone"""
    current_tz = timezone.get_current_timezone()
    return timezone.now().astimezone(current_tz).date()


def record_api_hit(endpoint_name):
    """Atomically increment the API hit count for today's date"""
    try:
        today = get_current_app_date()
        updated = DailyAPIHit.objects.filter(endpoint=endpoint_name, hit_date=today).update(
            count=F('count') + 1,
            last_hit_at=timezone.now()
        )
        if not updated:
            DailyAPIHit.objects.get_or_create(
                endpoint=endpoint_name,
                hit_date=today,
                defaults={'count': 1}
            )
    except Exception:
        pass



def build_daily_market_results(target_date):
    """
    Constructs normalized result data structure for a given date across all active markets.
    """
    markets = Market.objects.filter(is_active=True).order_by('name')
    results = Result.objects.filter(result_date=target_date).select_related('market')
    attempts = FetchAttempt.objects.filter(result_date=target_date).select_related('market')

    results_map = {(r.market_id, r.result_type): r.result_value for r in results}
    attempts_map = {(a.market_id, a.result_type): a.status for a in attempts}

    output = []
    for m in markets:
        open_val = results_map.get((m.id, ResultType.OPEN))
        close_val = results_map.get((m.id, ResultType.CLOSE))

        open_st = attempts_map.get((m.id, ResultType.OPEN), FetchStatus.WAITING)
        close_st = attempts_map.get((m.id, ResultType.CLOSE), FetchStatus.WAITING)

        if open_val:
            open_st = FetchStatus.SUCCESS
        if close_val:
            close_st = FetchStatus.SUCCESS

        output.append({
            "market_id": m.id,
            "market": m.name,
            "slug": m.slug,
            "external_name": m.external_name,
            "open_time": m.open_time.strftime('%H:%M'),
            "close_time": m.close_time.strftime('%H:%M'),
            "open": open_val,
            "open_status": open_st,
            "close": close_val,
            "close_status": close_st,
        })
    return output


# ==========================================
# PUBLIC DJANGO TEMPLATE VIEWS
# ==========================================

class HomeView(View):
    def get(self, request):
        today = get_current_app_date()
        daily_results = build_daily_market_results(today)
        
        q = request.GET.get('q', '').strip()
        if q:
            daily_results = [r for r in daily_results if q.lower() in r['market'].lower()]

        context = {
            'today_date': today,
            'daily_results': daily_results,
            'search_query': q,
            'active_tab': 'home',
        }
        return render(request, 'home.html', context)


class MarketListView(View):
    def get(self, request):
        q = request.GET.get('q', '').strip()
        markets = Market.objects.filter(is_active=True)
        if q:
            markets = markets.filter(Q(name__icontains=q) | Q(external_name__icontains=q))

        paginator = Paginator(markets.order_by('name'), 12)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'page_obj': page_obj,
            'search_query': q,
            'active_tab': 'markets',
        }
        return render(request, 'markets.html', context)


class TodayResultsView(View):
    def get(self, request):
        today = get_current_app_date()
        daily_results = build_daily_market_results(today)
        context = {
            'target_date': today,
            'is_today': True,
            'daily_results': daily_results,
            'active_tab': 'today',
        }
        return render(request, 'results.html', context)


class DateResultsView(View):
    def get(self, request, date_str=None):
        query_date_str = request.GET.get('date') or date_str
        today = get_current_app_date()

        if query_date_str:
            try:
                target_date = datetime.strptime(query_date_str, '%Y-%m-%d').date()
            except ValueError:
                target_date = today
        else:
            target_date = today

        daily_results = build_daily_market_results(target_date)
        context = {
            'target_date': target_date,
            'is_today': (target_date == today),
            'daily_results': daily_results,
            'active_tab': 'results',
        }
        return render(request, 'results.html', context)


class MarketDetailView(View):
    def get(self, request, slug):
        market = get_object_or_404(Market, slug=slug, is_active=True)
        results = Result.objects.filter(market=market).order_by('-result_date', 'result_type')

        history_dict = {}
        for r in results:
            d_str = str(r.result_date)
            if d_str not in history_dict:
                history_dict[d_str] = {'date': r.result_date, 'open': None, 'close': None}
            if r.result_type == ResultType.OPEN:
                history_dict[d_str]['open'] = r.result_value
            elif r.result_type == ResultType.CLOSE:
                history_dict[d_str]['close'] = r.result_value

        history_list = list(history_dict.values())
        paginator = Paginator(history_list, 15)
        page_number = request.GET.get('page')
        page_obj = paginator.get_page(page_number)

        context = {
            'market': market,
            'page_obj': page_obj,
            'active_tab': 'markets',
        }
        return render(request, 'market_detail.html', context)


# ==========================================
# CUSTOM ADMIN DASHBOARD & MANAGEMENT VIEWS
# ==========================================

class StaffRequiredMixin(UserPassesTestMixin):
    def test_func(self):
        return self.request.user.is_authenticated and self.request.user.is_staff


class DashboardView(StaffRequiredMixin, View):
    def get(self, request):
        today = get_current_app_date()
        markets = Market.objects.all().order_by('name')
        recent_results = Result.objects.select_related('market').order_by('-fetched_at')[:15]
        recent_attempts = FetchAttempt.objects.select_related('market').order_by('-updated_at')[:20]

        today_hits = DailyAPIHit.objects.filter(endpoint='/api/results/all/', hit_date=today).aggregate(total=Sum('count'))['total'] or 0
        total_hits = DailyAPIHit.objects.filter(endpoint='/api/results/all/').aggregate(total=Sum('count'))['total'] or 0

        stats = {
            'total_markets': markets.count(),
            'active_markets': markets.filter(is_active=True).count(),
            'today_success': Result.objects.filter(result_date=today).count(),
            'failed_attempts': FetchAttempt.objects.filter(result_date=today, status=FetchStatus.FAILED).count(),
            'today_api_hits': today_hits,
            'total_api_hits': total_hits,
        }

        context = {
            'markets': markets,
            'recent_results': recent_results,
            'recent_attempts': recent_attempts,
            'stats': stats,
            'today_date': today,
            'active_tab': 'dashboard',
        }
        return render(request, 'dashboard/index.html', context)


class MarketCreateView(StaffRequiredMixin, View):
    def get(self, request):
        form = MarketForm()
        return render(request, 'dashboard/market_form.html', {'form': form, 'title': 'Add New Market'})

    def post(self, request):
        form = MarketForm(request.POST)
        if form.is_valid():
            market = form.save()
            messages.success(request, f"Market '{market.name}' created successfully!")
            return redirect('markets:dashboard')
        return render(request, 'dashboard/market_form.html', {'form': form, 'title': 'Add New Market'})


class MarketUpdateView(StaffRequiredMixin, View):
    def get(self, request, pk):
        market = get_object_or_404(Market, pk=pk)
        form = MarketForm(instance=market)
        return render(request, 'dashboard/market_form.html', {'form': form, 'market': market, 'title': f'Edit Market: {market.name}'})

    def post(self, request, pk):
        market = get_object_or_404(Market, pk=pk)
        form = MarketForm(request.POST, instance=market)
        if form.is_valid():
            form.save()
            messages.success(request, f"Market '{market.name}' updated successfully!")
            return redirect('markets:dashboard')
        return render(request, 'dashboard/market_form.html', {'form': form, 'market': market, 'title': f'Edit Market: {market.name}'})


class MarketToggleActiveView(StaffRequiredMixin, View):
    def post(self, request, pk):
        market = get_object_or_404(Market, pk=pk)
        market.is_active = not market.is_active
        market.save()
        status_str = "activated" if market.is_active else "deactivated"
        messages.info(request, f"Market '{market.name}' has been {status_str}.")
        return redirect('markets:dashboard')


class MarketDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        market = get_object_or_404(Market, pk=pk)
        market_name = market.name
        market.delete()
        messages.success(request, f"Market '{market_name}' was deleted successfully.")
        return redirect('markets:dashboard')


class ManualResultCreateView(StaffRequiredMixin, View):
    def get(self, request):
        today = get_current_app_date()
        date_param = request.GET.get('date')
        market_id = request.GET.get('market')
        result_type = request.GET.get('type')

        target_date = today
        if date_param:
            try:
                target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                pass

        initial = {'result_date': target_date}
        if market_id:
            initial['market'] = market_id
        if result_type:
            initial['result_type'] = result_type

        # Check if an existing result matches the initial criteria to pre-fill
        existing_result = None
        if market_id and result_type:
            existing_result = Result.objects.filter(
                market_id=market_id,
                result_date=target_date,
                result_type=result_type
            ).first()
            if existing_result:
                initial['result_value'] = existing_result.result_value

        form = ManualResultForm(initial=initial)
        context = {
            'form': form,
            'title': 'Manually Add / Edit Result',
            'target_date': target_date,
            'existing_result': existing_result,
            'active_tab': 'dashboard',
        }
        return render(request, 'dashboard/result_form.html', context)

    def post(self, request):
        form = ManualResultForm(request.POST)
        if form.is_valid():
            market = form.cleaned_data['market']
            result_date = form.cleaned_data['result_date']
            result_type = form.cleaned_data['result_type']
            result_value = form.cleaned_data['result_value']

            res_obj, created = Result.objects.update_or_create(
                market=market,
                result_date=result_date,
                result_type=result_type,
                defaults={
                    'result_value': result_value,
                    'source': 'Manual',
                    'fetched_at': timezone.now()
                }
            )

            FetchAttempt.objects.update_or_create(
                market=market,
                result_date=result_date,
                result_type=result_type,
                defaults={
                    'status': FetchStatus.SUCCESS,
                    'last_attempt_at': timezone.now(),
                    'error_message': None
                }
            )

            action_str = "created" if created else "updated"
            messages.success(request, f"Manual result for {market.name} [{result_date} {result_type}] successfully {action_str}: {result_value}")
            return redirect(f"{redirect('markets:result_manage').url}?date={result_date}")
        
        return render(request, 'dashboard/result_form.html', {
            'form': form,
            'title': 'Manually Add / Edit Result',
            'active_tab': 'dashboard',
        })


class ManualResultDeleteView(StaffRequiredMixin, View):
    def post(self, request, pk):
        result = get_object_or_404(Result, pk=pk)
        market_name = result.market.name
        result_date = result.result_date
        result_type = result.result_type

        # Update fetch attempt status back to WAITING or NOT_AVAILABLE
        FetchAttempt.objects.filter(
            market=result.market,
            result_date=result_date,
            result_type=result_type
        ).update(
            status=FetchStatus.WAITING,
            error_message="Manual result was removed by administrator."
        )

        result.delete()
        messages.info(request, f"Manual result for {market_name} [{result_date} {result_type}] was deleted.")
        return redirect(f"{redirect('markets:result_manage').url}?date={result_date}")


class DateResultManageView(StaffRequiredMixin, View):
    """
    Dedicated Date-wise Result Management view allowing admins to select any date
    and quickly add, edit, or delete Open/Close results across all active markets.
    """
    def get(self, request):
        today = get_current_app_date()
        date_str = request.GET.get('date')

        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                target_date = today
        else:
            target_date = today

        from datetime import timedelta
        prev_date = target_date - timedelta(days=1)
        next_date = target_date + timedelta(days=1)

        markets = Market.objects.filter(is_active=True).order_by('name')
        results = Result.objects.filter(result_date=target_date).select_related('market')
        attempts = FetchAttempt.objects.filter(result_date=target_date).select_related('market')

        results_map = {(r.market_id, r.result_type): r for r in results}
        attempts_map = {(a.market_id, a.result_type): a for a in attempts}

        market_rows = []
        for m in markets:
            open_res = results_map.get((m.id, ResultType.OPEN))
            close_res = results_map.get((m.id, ResultType.CLOSE))
            open_att = attempts_map.get((m.id, ResultType.OPEN))
            close_att = attempts_map.get((m.id, ResultType.CLOSE))

            market_rows.append({
                'market': m,
                'open_result': open_res,
                'close_result': close_res,
                'open_attempt': open_att,
                'close_attempt': close_att,
            })

        context = {
            'target_date': target_date,
            'today_date': today,
            'prev_date': prev_date,
            'next_date': next_date,
            'is_today': (target_date == today),
            'market_rows': market_rows,
            'result_types': ResultType,
            'active_tab': 'dashboard',
        }
        return render(request, 'dashboard/result_manage.html', context)

    def post(self, request):
        """Quick inline form submission from Date Management page"""
        market_id = request.POST.get('market_id')
        date_str = request.POST.get('result_date')
        result_type = request.POST.get('result_type')
        result_value = (request.POST.get('result_value') or '').strip()

        if not market_id or not date_str or not result_type:
            messages.error(request, "Missing required parameters for result declaration.")
            return redirect('markets:result_manage')

        market = get_object_or_404(Market, pk=market_id)
        try:
            result_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        except ValueError:
            messages.error(request, "Invalid date format.")
            return redirect('markets:result_manage')

        if not result_value:
            # If value is empty, treat as delete request if existing
            existing = Result.objects.filter(market=market, result_date=result_date, result_type=result_type).first()
            if existing:
                existing.delete()
                FetchAttempt.objects.filter(market=market, result_date=result_date, result_type=result_type).update(
                    status=FetchStatus.WAITING,
                    error_message="Manual result cleared by admin."
                )
                messages.info(request, f"Cleared {result_type} result for {market.name} [{result_date}].")
            return redirect(f"{redirect('markets:result_manage').url}?date={result_date}")

        # Basic Format Validation check for quick inline entry
        import re
        if result_type == ResultType.OPEN and not re.match(r'^\d{3}-\d$', result_value):
            messages.error(request, f"Invalid Open Result format '{result_value}'. Must be like '170-8'.")
            return redirect(f"{redirect('markets:result_manage').url}?date={result_date}")
        elif result_type == ResultType.CLOSE and not re.match(r'^\d{3}-\d{2}-\d{3}$', result_value):
            messages.error(request, f"Invalid Close Result format '{result_value}'. Must be like '170-89-450'.")
            return redirect(f"{redirect('markets:result_manage').url}?date={result_date}")

        # Save Result
        res_obj, created = Result.objects.update_or_create(
            market=market,
            result_date=result_date,
            result_type=result_type,
            defaults={
                'result_value': result_value,
                'source': 'Manual',
                'fetched_at': timezone.now()
            }
        )

        FetchAttempt.objects.update_or_create(
            market=market,
            result_date=result_date,
            result_type=result_type,
            defaults={
                'status': FetchStatus.SUCCESS,
                'last_attempt_at': timezone.now(),
                'error_message': None
            }
        )

        action = "added" if created else "updated"
        messages.success(request, f"Successfully {action} {result_type} result for {market.name} [{result_date}]: {result_value}")
        return redirect(f"{redirect('markets:result_manage').url}?date={result_date}")


class TriggerFetchView(StaffRequiredMixin, View):
    def post(self, request, pk):
        market = get_object_or_404(Market, pk=pk)
        result_type = request.POST.get('result_type', ResultType.OPEN)
        date_str = request.POST.get('result_date')
        
        today = get_current_app_date()
        target_date = today
        if date_str:
            try:
                target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        fetch_market_result_task.delay(market.id, str(target_date), result_type)
        messages.success(request, f"Triggered background fetch for {market.name} [{target_date} {result_type}]. Check status table below.")
        
        redirect_to_manage = request.POST.get('redirect_to_manage')
        if redirect_to_manage:
            return redirect(f"{redirect('markets:result_manage').url}?date={target_date}")
        return redirect('markets:dashboard')



# ==========================================
# REST API VIEWS (DRF)
# ==========================================

class APIMatkaResultsAllView(APIView):
    """
    GET /api/results/all/
    Public API returning all active market results formatted according to Matka response standard.
    """
    def get(self, request):
        record_api_hit('/api/results/all/')
        date_param = request.GET.get('date')
        market_param = request.GET.get('market')

        if not date_param:
            target_date = get_current_app_date()
        else:
            try:
                target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                return Response({
                    "status": False,
                    "message": "Invalid date format. Use YYYY-MM-DD",
                    "data": []
                }, status=status.HTTP_400_BAD_REQUEST)

        markets = Market.objects.filter(is_active=True).order_by('name')

        if market_param and market_param.lower() != 'all':
            norm_q = normalize_market_name(market_param)
            # Pass 1: Prioritize exact normalized match
            exact_matches = [
                m for m in markets
                if norm_q in (
                    normalize_market_name(m.name),
                    normalize_market_name(m.external_name),
                    normalize_market_name(m.slug)
                )
            ]
            if exact_matches:
                markets = exact_matches
            else:
                # Pass 2: Collision-safe token match (preventing SRIDEVI vs SRIDEVI NIGHT collision)
                filtered_markets = [
                    m for m in markets
                    if is_market_name_match(market_param, m.name) or is_market_name_match(market_param, m.external_name)
                ]
                markets = filtered_markets

        results = Result.objects.filter(result_date=target_date).select_related('market')
        results_map = {(r.market_id, r.result_type): r.result_value for r in results}

        data_list = []
        for m in markets:
            open_val = results_map.get((m.id, ResultType.OPEN))
            close_val = results_map.get((m.id, ResultType.CLOSE))

            formatted_result = format_matka_result_string(open_val, close_val)

            open_time_str = datetime.combine(target_date, m.open_time).strftime('%I:%M %p')
            close_time_str = datetime.combine(target_date, m.close_time).strftime('%I:%M %p')

            data_list.append({
                "name": m.name,
                "result": formatted_result,
                "date": str(target_date),
                "open_time": open_time_str,
                "close_time": close_time_str,
            })

        return Response({
            "status": True,
            "message": "success",
            "market": market_param or "all",
            "date": str(target_date),
            "count": len(data_list),
            "data": data_list
        })


def format_matka_result_string(open_val, close_val):
    """
    Constructs the Matka result string:
    - If only open result is available: "124-7"
    - If full open + close result is available: "124-79-450"
    - If no result is available: "***-**-***"
    """
    if not open_val and not close_val:
        return "***-**-***"

    if close_val and len(close_val.split('-')) == 3:
        return close_val

    if open_val:
        first_parts = open_val.split('-')
        if len(first_parts) == 3:
            return open_val
        
        open_pana = first_parts[0]
        open_digit = first_parts[1][0] if len(first_parts) > 1 and first_parts[1] else ''

        if not close_val:
            return f"{open_pana}-{open_digit}" if open_digit else open_pana

        second_parts = close_val.split('-')
        if len(second_parts) == 3:
            return close_val
        elif len(second_parts) == 2:
            close_digit = second_parts[1][0] if len(second_parts) > 1 and second_parts[1] else second_parts[0][0]
            close_pana = second_parts[0] if len(second_parts[0]) == 3 else second_parts[1]
            jodi = f"{open_digit}{close_digit}"
            return f"{open_pana}-{jodi}-{close_pana}"
        else:
            close_pana = close_val
            jodi = f"{open_digit}*" if open_digit else "**"
            return f"{open_pana}-{jodi}-{close_pana}"

    if close_val:
        return close_val

    return "***-**-***"


class APITodayResultsView(APIView):
    """GET /api/results/today/"""
    def get(self, request):
        today = get_current_app_date()
        daily_results = build_daily_market_results(today)
        return Response({
            "date": str(today),
            "results": daily_results
        })


class APIDateResultsView(APIView):
    """GET /api/results/?date=YYYY-MM-DD"""
    def get(self, request):
        date_param = request.GET.get('date')
        if not date_param:
            target_date = get_current_app_date()
        else:
            try:
                target_date = datetime.strptime(date_param, '%Y-%m-%d').date()
            except ValueError:
                return Response({"error": "Invalid date format. Use YYYY-MM-DD"}, status=status.HTTP_400_BAD_REQUEST)

        daily_results = build_daily_market_results(target_date)
        return Response({
            "date": str(target_date),
            "results": daily_results
        })


class APIMarketListView(APIView):
    """GET /api/markets/"""
    def get(self, request):
        markets = Market.objects.filter(is_active=True).order_by('name')
        serializer = MarketSerializer(markets, many=True)
        return Response({"markets": serializer.data})


class APIMarketResultsView(APIView):
    """GET /api/markets/<slug>/results/"""
    def get(self, request, slug):
        market = get_object_or_404(Market, slug=slug, is_active=True)
        results = Result.objects.filter(market=market).order_by('-result_date')
        serializer = ResultSerializer(results, many=True)
        return Response({
            "market": market.name,
            "slug": market.slug,
            "results": serializer.data
        })
