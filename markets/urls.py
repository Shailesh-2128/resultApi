from django.urls import path
from . import views

urlpatterns = [
    # Public UI pages
    path('', views.HomeView.as_view(), name='home'),
    path('markets/', views.MarketListView.as_view(), name='market_list'),
    path('results/today/', views.TodayResultsView.as_view(), name='today_results'),
    path('results/date/', views.DateResultsView.as_view(), name='date_results'),
    path('results/date/<str:date_str>/', views.DateResultsView.as_view(), name='date_results_specific'),
    path('market/<slug:slug>/', views.MarketDetailView.as_view(), name='market_detail'),

    # Admin Management Dashboard UI
    path('dashboard/', views.DashboardView.as_view(), name='dashboard'),
    path('dashboard/markets/add/', views.MarketCreateView.as_view(), name='market_create'),
    path('dashboard/markets/<int:pk>/edit/', views.MarketUpdateView.as_view(), name='market_update'),
    path('dashboard/markets/<int:pk>/toggle/', views.MarketToggleActiveView.as_view(), name='market_toggle'),
    path('dashboard/markets/<int:pk>/delete/', views.MarketDeleteView.as_view(), name='market_delete'),
    path('dashboard/results/add/', views.ManualResultCreateView.as_view(), name='result_create'),
    path('dashboard/results/manage/', views.DateResultManageView.as_view(), name='result_manage'),
    path('dashboard/results/delete/<int:pk>/', views.ManualResultDeleteView.as_view(), name='result_delete'),
    path('dashboard/markets/<int:pk>/fetch/', views.TriggerFetchView.as_view(), name='trigger_fetch'),

    # REST API endpoints (prefixed with api/ inside this router)
    path('api/results/all/', views.APIMatkaResultsAllView.as_view(), name='api_results_all'),
    path('api/results/today/', views.APITodayResultsView.as_view(), name='api_results_today'),
    path('api/results/', views.APIDateResultsView.as_view(), name='api_results_date'),
    path('api/markets/', views.APIMarketListView.as_view(), name='api_market_list'),
    path('api/markets/<slug:slug>/results/', views.APIMarketResultsView.as_view(), name='api_market_results'),
]
