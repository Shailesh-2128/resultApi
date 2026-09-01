from django import forms
from .models import Market, Result


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
                'class': 'form-control theme-input',
                'placeholder': 'e.g. Market A'
            }),
            'external_name': forms.TextInput(attrs={
                'class': 'form-control theme-input',
                'placeholder': 'e.g. market_a'
            }),
            'open_time': forms.TimeInput(attrs={
                'class': 'form-control theme-input',
                'type': 'time'
            }),
            'close_time': forms.TimeInput(attrs={
                'class': 'form-control theme-input',
                'type': 'time'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input'
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
                'class': 'form-select theme-input'
            }),
            'result_date': forms.DateInput(attrs={
                'class': 'form-control theme-input',
                'type': 'date'
            }),
            'result_type': forms.Select(attrs={
                'class': 'form-select theme-input'
            }),
            'result_value': forms.TextInput(attrs={
                'class': 'form-control theme-input',
                'placeholder': 'e.g. 170-8 or 170-89-450'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['market'].queryset = Market.objects.all().order_by('name')
