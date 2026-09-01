from django.contrib import admin
from django.utils.html import format_html
from .models import Market, Result, FetchAttempt, FetchStatus


@admin.register(Market)
class MarketAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'external_name',
        'slug',
        'open_time',
        'close_time',
        'is_active',
        'updated_at',
    )
    list_editable = ('open_time', 'close_time', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name', 'external_name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    ordering = ('name',)


@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = (
        'market',
        'result_date',
        'result_type',
        'result_value',
        'source',
        'fetched_at',
    )
    list_filter = ('result_date', 'result_type', 'market')
    search_fields = ('market__name', 'market__external_name', 'result_value')
    date_hierarchy = 'result_date'
    ordering = ('-result_date', 'market', 'result_type')
    raw_id_fields = ('market',)


@admin.register(FetchAttempt)
class FetchAttemptAdmin(admin.ModelAdmin):
    list_display = (
        'market',
        'result_date',
        'result_type',
        'status_badge',
        'attempt_count',
        'response_status',
        'last_attempt_at',
        'short_error_message',
    )
    list_filter = ('status', 'result_type', 'market', 'result_date')
    search_fields = ('market__name', 'error_message')
    date_hierarchy = 'result_date'
    ordering = ('-updated_at',)
    readonly_fields = (
        'market',
        'result_date',
        'result_type',
        'status',
        'attempt_count',
        'last_attempt_at',
        'next_attempt_at',
        'response_status',
        'error_message',
        'created_at',
        'updated_at',
    )

    def status_badge(self, obj):
        colors = {
            FetchStatus.SUCCESS: '#198754',      # Green
            FetchStatus.FETCHING: '#0dcaf0',     # Cyan
            FetchStatus.WAITING: '#6c757d',      # Grey
            FetchStatus.NOT_AVAILABLE: '#ffc107',# Yellow
            FetchStatus.FAILED: '#dc3545',       # Red
            FetchStatus.TIMEOUT: '#fd7e14',      # Orange
        }
        color = colors.get(obj.status, '#6c757d')
        return format_html(
            '<span style="background-color: {}; color: #fff; padding: 4px 8px; border-radius: 4px; font-weight: bold; font-size: 11px;">{}</span>',
            color,
            obj.get_status_display()
        )

    status_badge.short_description = 'Status'

    def short_error_message(self, obj):
        if not obj.error_message:
            return '-'
        return obj.error_message[:60] + ('...' if len(obj.error_message) > 60 else '')

    short_error_message.short_description = 'Error Summary'
