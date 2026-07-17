from django import forms


class CheckoutForm(forms.Form):
    PAYMENT_CHOICES = [
        ('card', 'Tarjeta de crédito/débito'),
        ('paypal', 'PayPal'),
        ('transfer', 'Transferencia bancaria'),
    ]

    # Datos personales
    full_name = forms.CharField(
        max_length=200,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Nombre completo'}),
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ejemplo.com'}),
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '09XXXXXXXX'}),
    )
    address = forms.CharField(
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Dirección de entrega'}),
    )
    dni = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cédula/RUC'}),
    )

    # Método de pago
    payment_method = forms.ChoiceField(
        choices=PAYMENT_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'payment-radio'}),
    )

    # Tarjeta
    card_number = forms.CharField(
        max_length=19, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '1234 5678 9012 3456', 'inputmode': 'numeric'}),
    )
    card_expiry = forms.CharField(
        max_length=5, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'MM/AA'}),
    )
    card_cvv = forms.CharField(
        max_length=4, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'CVV', 'inputmode': 'numeric'}),
    )

    # Transferencia bancaria
    bank_account = forms.CharField(
        max_length=30, required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de cuenta'}),
    )

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get('payment_method')

        if method == 'card':
            card_number = cleaned_data.get('card_number', '').replace(' ', '')
            if not card_number or len(card_number) < 12:
                self.add_error('card_number', 'Ingresa un número de tarjeta válido.')
            if not cleaned_data.get('card_expiry'):
                self.add_error('card_expiry', 'Ingresa la fecha de expiración.')
            if not cleaned_data.get('card_cvv'):
                self.add_error('card_cvv', 'Ingresa el CVV.')
        elif method == 'transfer':
            if not cleaned_data.get('bank_account'):
                self.add_error('bank_account', 'Ingresa el número de cuenta.')

        return cleaned_data
