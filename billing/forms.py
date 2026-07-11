from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from .models import Brand, Product
from django.forms import inlineformset_factory
from .models import Invoice, InvoiceDetail

class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, widget=forms.EmailInput(attrs={'class':'form-control'}))
    first_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class':'form-control'}))
    last_name = forms.CharField(max_length=100, widget=forms.TextInput(attrs={'class':'form-control'}))
    class Meta:
        model = User
        fields = ['username','first_name','last_name','email','password1','password2']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for f in self.fields: self.fields[f].widget.attrs['class'] = 'form-control'

class BrandForm(forms.ModelForm):
    class Meta:
        model = Brand
        fields = ['name', 'description', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class':'form-control'}),
            'description': forms.Textarea(attrs={'class':'form-control','rows':3}),
            'is_active': forms.CheckboxInput(attrs={'class':'form-check-input'}),
        }

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ['customer']
        widgets = {
            'customer': forms.Select(attrs={'class': 'form-select'}),
        }

class ProductForm(forms.ModelForm):
    class Meta:
        model = Product
        fields = [
            'name', 'description', 'brand', 'group',
            'suppliers', 'image', 'unit_price', 'discount', 'stock', 'applies_iva', 'is_active',
        ]
        labels = {
            'name':        'Product Name',
            'description': 'Description',
            'brand':       'Brand',
            'group':       'Category / Group',
            'suppliers':   'Suppliers',
            'image':       'Product Image',
            'unit_price':  'Unit Price ($)',
            'discount':    'Discount (%)',
            'stock':       'Units in Stock',
            'applies_iva': 'Aplica IVA (15%)',
            'is_active':   'Active product',
        }
        help_texts = {
            'name':       'Full commercial name of the product.',
            'unit_price': 'Must be greater than zero.',
            'discount':   'Percentage discount applied to the unit price (0–100).',
            'stock':      'Current units available in inventory.',
            'image':      'Accepted: JPG, PNG, GIF · Max 2 MB.',
            'is_active':  'Uncheck to hide this product from orders.',
        }
        error_messages = {
            'name':       {'required': 'Product name is required.'},
            'brand':      {'required': 'Please select a brand.'},
            'group':      {'required': 'Please select a category.'},
            'unit_price': {
                'required': 'Unit price is required.',
                'invalid':  'Enter a valid numeric price.',
            },
            'stock': {
                'required': 'Stock quantity is required.',
                'invalid':  'Enter a valid integer.',
            },
        }
        widgets = {
            'name': forms.TextInput(attrs={
                'class':       'form-control form-control-lg',
                'placeholder': 'e.g. Laptop HP Pavilion 15',
                'autofocus':   True,
            }),
            'description': forms.Textarea(attrs={
                'class':       'form-control',
                'rows':        4,
                'placeholder': 'Brief description of the product (optional)…',
            }),
            'brand':     forms.Select(attrs={'class': 'form-select'}),
            'group':     forms.Select(attrs={'class': 'form-select'}),
            'suppliers': forms.CheckboxSelectMultiple(attrs={'class': 'form-check-input'}),
            'image':     forms.ClearableFileInput(attrs={
                'class':  'form-control',
                'accept': 'image/*',
            }),
            'unit_price': forms.NumberInput(attrs={
                'class':       'form-control form-control-lg text-end',
                'step':        '0.01',
                'min':         '0.01',
                'placeholder': '0.00',
            }),
            'discount': forms.NumberInput(attrs={
                'class':       'form-control text-end',
                'step':        '0.01',
                'min':         '0',
                'max':         '100',
                'placeholder': '0.00',
            }),
            'stock': forms.NumberInput(attrs={
                'class':       'form-control form-control-lg text-end',
                'min':         '0',
                'placeholder': '0',
            }),
            'applies_iva': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role':  'switch',
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role':  'switch',
            }),
        }

    def clean_unit_price(self):
        price = self.cleaned_data.get('unit_price')
        if price is not None and price <= 0:
            raise forms.ValidationError('El precio unitario debe ser mayor que cero.')
        return price

    def clean_stock(self):
        stock = self.cleaned_data.get('stock')
        if stock is not None and stock < 0:
            raise forms.ValidationError('El stock no puede ser negativo.')
        return stock

    def clean_discount(self):
        discount = self.cleaned_data.get('discount')
        if discount is not None and not (0 <= discount <= 100):
            raise forms.ValidationError('El descuento debe estar entre 0 y 100.')
        return discount


InvoiceDetailFormSet = inlineformset_factory(
    Invoice,
    InvoiceDetail,
    fields=['product', 'quantity', 'unit_price', 'applies_iva'],
    extra=3,
    can_delete=True,
    widgets={
        'product': forms.Select(attrs={'class': 'form-select'}),
        'quantity': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
        'applies_iva': forms.CheckboxInput(attrs={'class': 'form-check-input applies-iva-input'}),
    }
)