from django import forms
from .models import Market, Result, ResultType


class MarketForm(forms.ModelForm):
    class Meta:
        model = Market
        fields = [
            'name',
            'external_name',
            'open_time',
            'close_time',
            'is_active',
        ]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control bg-dark border-secondary text-white',
                'placeholder': 'e.g. Market A'
            }),
            'external_name': forms.TextInput(attrs={
                'class': 'form-control bg-dark border-secondary text-white',
                'placeholder': 'e.g. market_a'
            }),
            'open_time': forms.TimeInput(attrs={
                'class': 'form-control bg-dark border-secondary text-white',
                'type': 'time'
            }),
            'close_time': forms.TimeInput(attrs={
                'class': 'form-control bg-dark border-secondary text-white',
                'type': 'time'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input bg-dark border-secondary'
            }),
        }


class ManualResultForm(forms.ModelForm):
    class Meta:
        model = Result
        fields = [
            'market',
            'result_date',
            'result_type',
            'result_value',
        ]
        widgets = {
            'market': forms.Select(attrs={
                'class': 'form-select bg-dark border-secondary text-white'
            }),
            'result_date': forms.DateInput(attrs={
                'class': 'form-control bg-dark border-secondary text-white',
                'type': 'date'
            }),
            'result_type': forms.Select(attrs={
                'class': 'form-select bg-dark border-secondary text-white'
            }),
            'result_value': forms.TextInput(attrs={
                'class': 'form-control bg-dark border-secondary text-white',
                'placeholder': 'e.g. 170-8 or 170-89-450'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['market'].queryset = Market.objects.all().order_by('name')
