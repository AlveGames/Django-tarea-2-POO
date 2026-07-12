from datetime import date

from django import forms
from billing.models import Invoice
from .models import PagoCuotaVenta


class FacturaVentaForm(forms.ModelForm):
    numero_cuotas = forms.IntegerField(
        required=False,
        min_value=1,
        label='Número de Cuotas',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        help_text='Solo aplica si el tipo de pago es CREDITO.',
    )

    class Meta:
        model = Invoice
        fields = ['customer', 'subtotal', 'tax', 'total', 'tipo_pago']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
            'subtotal': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tax': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'total': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'tipo_pago': forms.Select(attrs={'class': 'form-select'}),
        }


class GenerarCuotasForm(forms.Form):
    numero_cuotas = forms.IntegerField(
        min_value=1,
        label='Número de cuotas',
        widget=forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        error_messages={
            'min_value': 'El número de cuotas debe ser mayor a cero.',
            'required': 'Debe indicar el número de cuotas.',
            'invalid': 'Ingrese un número entero válido.',
        },
    )

    def clean_numero_cuotas(self):
        numero_cuotas = self.cleaned_data.get('numero_cuotas')
        if numero_cuotas is not None and numero_cuotas <= 0:
            raise forms.ValidationError('El número de cuotas debe ser mayor a cero.')
        return numero_cuotas


class PagoCuotaForm(forms.ModelForm):
    class Meta:
        model = PagoCuotaVenta
        fields = ['fecha', 'valor', 'observacion']
        widgets = {
            'fecha': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'valor': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'observacion': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
        }

    def __init__(self, *args, cuota=None, **kwargs):
        self.cuota = cuota
        super().__init__(*args, **kwargs)
        self.fields['fecha'].input_formats = ['%Y-%m-%d']

    def clean_valor(self):
        valor = self.cleaned_data.get('valor')
        if valor is None:
            return valor
        if valor < 0:
            raise forms.ValidationError('El valor del pago no puede ser negativo.')
        if valor == 0:
            raise forms.ValidationError('El valor del pago debe ser mayor a cero.')
        if self.cuota is not None and valor > self.cuota.saldo:
            raise forms.ValidationError('El pago supera el saldo de la cuota.')
        return valor

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if not fecha:
            return fecha

        hoy = date.today()
        if fecha < hoy:
            raise forms.ValidationError('La fecha del pago no puede ser anterior a hoy.')

        if self.cuota and fecha > self.cuota.fecha_vencimiento:
            raise forms.ValidationError(
                f'La fecha del pago no puede superar la fecha de vencimiento de la cuota ({self.cuota.fecha_vencimiento}).'
            )

        return fecha


class PagoMultipleCuotasForm(forms.Form):
    fecha = forms.DateField(
        widget=forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}, format='%Y-%m-%d'),
        input_formats=['%Y-%m-%d'],
    )
    observacion = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
    )

    def clean_fecha(self):
        fecha = self.cleaned_data.get('fecha')
        if fecha and fecha != date.today():
            raise forms.ValidationError('La fecha del pago debe ser la fecha de hoy.')
        return fecha
