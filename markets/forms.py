import re
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
                'placeholder': 'e.g. 234-9 or 234-99-289'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['market'].queryset = Market.objects.all().order_by('name')
        self.fields['market'].empty_label = "-- Select Market --"

    def clean(self):
        cleaned_data = super().clean()
        result_type = cleaned_data.get('result_type')
        result_value = (cleaned_data.get('result_value') or '').strip()
        cleaned_data['result_value'] = result_value

        if result_type and result_value:
            if result_type == ResultType.OPEN:
                if not re.match(r'^\d{3}-\d$', result_value):
                    self.add_error('result_value', "Open result must be formatted as '3 digits - 1 digit' (e.g. 170-8).")
            elif result_type == ResultType.CLOSE:
                if not re.match(r'^\d{3}-\d{2}-\d{3}$', result_value):
                    self.add_error('result_value', "Close result must be formatted as '3 digits - 2 digits - 3 digits' (e.g. 170-89-450).")

        return cleaned_data

