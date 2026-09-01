from datetime import datetime, date
from django.shortcuts import render, get_object_or_404, redirect
from django.views import View
from django.core.paginator import Paginator
from django.utils import timezone
from django.db.models import Q
from django.contrib.auth.mixins import UserPassesTestMixin
from django.contrib import messages
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from .models import Market, Result, FetchAttempt, FetchStatus, ResultType
from .serializers import MarketSerializer, ResultSerializer, MarketDayResultsSerializer
from .forms import MarketForm, ManualResultForm
from .tasks import fetch_market_result_task


def get_current_app_date():
    """Helper to get current date in configured application timezone"""
    current_tz = timezone.get_current_timezone()
    return timezone.now().astimezone(current_tz).date()


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

        stats = {
            'total_markets': markets.count(),
            'active_markets': markets.filter(is_active=True).count(),
            'today_success': Result.objects.filter(result_date=today).count(),
            'failed_attempts': FetchAttempt.objects.filter(result_date=today, status=FetchStatus.FAILED).count(),
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
        form = ManualResultForm(initial={'result_date': get_current_app_date()})
        return render(request, 'dashboard/result_form.html', {'form': form, 'title': 'Manually Add/Edit Result'})

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
            messages.success(request, f"Result for {market.name} [{result_date} {result_type}] successfully {action_str}: {result_value}")
            return redirect('markets:dashboard')
        return render(request, 'dashboard/result_form.html', {'form': form, 'title': 'Manually Add/Edit Result'})


class TriggerFetchView(StaffRequiredMixin, View):
    def post(self, request, pk):
        market = get_object_or_404(Market, pk=pk)
        result_type = request.POST.get('result_type', ResultType.OPEN)
        today = get_current_app_date()

        fetch_market_result_task.delay(market.id, str(today), result_type)
        messages.success(request, f"Triggered background fetch for {market.name} [{today} {result_type}]. Check status table below.")
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
            clean_q = market_param.lower().replace(' ', '').replace('-', '')
            filtered_markets = []
            for m in markets:
                clean_m = m.name.lower().replace(' ', '').replace('-', '')
                clean_ext = m.external_name.lower().replace(' ', '').replace('-', '')
                clean_slug = m.slug.lower().replace('-', '')
                if clean_q in clean_m or clean_q in clean_ext or clean_q in clean_slug:
                    filtered_markets.append(m)
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
