from rest_framework import serializers
from .models import Market, Result, FetchAttempt


class MarketSerializer(serializers.ModelSerializer):
    class Meta:
        model = Market
        fields = [
            'id',
            'name',
            'slug',
            'external_name',
            'open_time',
            'close_time',
            'is_active',
        ]


class ResultSerializer(serializers.ModelSerializer):
    market_name = serializers.CharField(source='market.name', read_only=True)
    market_slug = serializers.CharField(source='market.slug', read_only=True)

    class Meta:
        model = Result
        fields = [
            'id',
            'market_name',
            'market_slug',
            'result_date',
            'result_type',
            'result_value',
            'source',
            'fetched_at',
        ]


class MarketDayResultsSerializer(serializers.Serializer):
    market = serializers.CharField()
    slug = serializers.CharField()
    open_time = serializers.CharField()
    close_time = serializers.CharField()
    open = serializers.CharField(allow_null=True)
    open_status = serializers.CharField()
    close = serializers.CharField(allow_null=True)
    close_status = serializers.CharField()
