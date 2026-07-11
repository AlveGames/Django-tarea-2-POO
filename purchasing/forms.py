from django import forms
from django.forms import inlineformset_factory
from billing.models import Supplier
from .models import Purchase, PurchaseDetail

class PurchaseFilterForm(forms.Form):
    supplier = forms.ModelChoiceField(
        queryset=Supplier.objects.order_by('name'),
        required=False,
        empty_label='All suppliers',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    date_from = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    date_to = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
    )
    min_total = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
    )
    max_total = forms.DecimalField(
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': '0.00'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        date_from = cleaned_data.get('date_from')
        date_to = cleaned_data.get('date_to')
        if date_from and date_to and date_from > date_to:
            raise forms.ValidationError('"Date from" must not be later than "Date to".')

        min_total = cleaned_data.get('min_total')
        max_total = cleaned_data.get('max_total')
        if min_total is not None and max_total is not None and min_total > max_total:
            raise forms.ValidationError('"Min total" must not be greater than "Max total".')
        return cleaned_data

class PurchaseForm(forms.ModelForm):
    class Meta:
        model = Purchase
        fields = ['supplier', 'document_number']
        widgets = {
            'supplier': forms.Select(attrs={'class': 'form-select'}),
            'document_number': forms.TextInput(attrs={'class': 'form-control'}),
        }

PurchaseDetailFormSet = inlineformset_factory(
    Purchase,
    PurchaseDetail,
    fields=['product', 'quantity', 'unit_cost'],
    extra=3,
    can_delete=True,
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_cost': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    }
)