import json
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth import login
from django.http import JsonResponse
from .models import *
from .forms import SignUpForm, BrandForm, ProductForm, InvoiceForm, InvoiceDetailFormSet
from shared.mixins import StaffRequiredMixin, ExportMixin
from shared.decorators import audit_action
from decimal import Decimal

# === HOME ===
@login_required
def home(request):
    context = {
        'total_brands': Brand.objects.count(),
        'total_products': Product.objects.count(),
        'total_customers': Customer.objects.count(),
        'total_invoices': Invoice.objects.count(),
        'recent_invoices': Invoice.objects.all()[:5],
        'low_stock': Product.objects.filter(stock__lte=5, is_active=True),
    }
    return render(request, 'billing/home.html', context)

# === REGISTRO ===
class SignUpView(CreateView):
    form_class = SignUpForm
    template_name = 'registration/signup.html'
    success_url = reverse_lazy('billing:brand_list')
    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)
        return response

# === BRAND (FBV) ===
@login_required
@audit_action('LIST_BRANDS')
def brand_list(request):
    brands = Brand.objects.all()
    return render(request, 'billing/brand_list.html', {'brands': brands})

@login_required
@audit_action('CREATE_BRAND')
def brand_create(request):
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand created!')
            return redirect('billing:brand_list')
    else: form = BrandForm()
    return render(request, 'billing/brand_form.html', {'form': form, 'title': 'Create Brand'})

@login_required
@audit_action('UPDATE_BRAND')
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand updated!')
            return redirect('billing:brand_list')
    else: form = BrandForm(instance=brand)
    return render(request, 'billing/brand_form.html', {'form': form, 'title': 'Edit Brand'})

@login_required
@audit_action('DELETE_BRAND')
def brand_delete(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        brand.delete()
        messages.success(request, 'Brand deleted!')
        return redirect('billing:brand_list')
    return render(request, 'billing/brand_confirm_delete.html', {'object': brand})

# === PRODUCTGROUP (CBV) ===
class ProductGroupListView(LoginRequiredMixin, ListView):
    model = ProductGroup; template_name = 'billing/productgroup_list.html'; context_object_name = 'items'

class ProductGroupCreateView(LoginRequiredMixin, CreateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')

class ProductGroupUpdateView(LoginRequiredMixin, UpdateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')

class ProductGroupDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = ProductGroup; template_name = 'billing/productgroup_confirm_delete.html'; success_url = reverse_lazy('billing:productgroup_list'); staff_redirect_url = '/groups/'

# === SUPPLIER (CBV) ===
class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier; template_name = 'billing/supplier_list.html'; context_object_name = 'items'

class SupplierCreateView(LoginRequiredMixin, CreateView):
    model = Supplier; fields = ['name','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')

class SupplierUpdateView(LoginRequiredMixin, UpdateView):
    model = Supplier; fields = ['name','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')

class SupplierDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Supplier; template_name = 'billing/supplier_confirm_delete.html'; success_url = reverse_lazy('billing:supplier_list'); staff_redirect_url = '/suppliers/'

# ------------------------------------------------------------------ #
#  Configuración de columnas para Product                             #
# ------------------------------------------------------------------ #

ALL_PRODUCT_COLUMNS = [
    {
        'key': 'image', 'label': 'Image', 'default': True,
        'exportable': False,
    },
    {
        'key': 'name', 'label': 'Name', 'default': True,
        'exportable': True, 'accessor': 'name',
    },
    {
        'key': 'description', 'label': 'Description', 'default': False,
        'exportable': True, 'accessor': 'description',
    },
    {
        'key': 'brand', 'label': 'Brand', 'default': True,
        'exportable': True, 'accessor': 'brand__name',
    },
    {
        'key': 'group', 'label': 'Category', 'default': True,
        'exportable': True, 'accessor': 'group__name',
    },
    {
        'key': 'suppliers', 'label': 'Suppliers', 'default': True,
        'exportable': True,
        'accessor': lambda obj: ', '.join(s.name for s in obj.suppliers.all()),
    },
    {
        'key': 'unit_price', 'label': 'Price', 'default': True,
        'exportable': True, 'accessor': 'unit_price',
    },
    {
        'key': 'discount', 'label': 'Discount', 'default': True,
        'exportable': True,
        'accessor': lambda obj: f"{obj.discount}%" if obj.discount else '0%',
    },
    {
        'key': 'stock', 'label': 'Stock', 'default': True,
        'exportable': True, 'accessor': 'stock',
    },
    {
        'key': 'is_active', 'label': 'Status', 'default': True,
        'exportable': True,
        'accessor': lambda obj: 'Yes' if obj.is_active else 'No',
    },
    {
        'key': 'created_at', 'label': 'Created', 'default': False,
        'exportable': True,
        'accessor': lambda obj: obj.created_at.strftime('%Y-%m-%d'),
    },
    {
        'key': 'balance', 'label': 'Balance', 'default': True,
        'exportable': True,
        'accessor': lambda obj: f"{obj.balance:.2f}",
    },
]

DEFAULT_PRODUCT_COLUMNS = [c['key'] for c in ALL_PRODUCT_COLUMNS if c['default']]

# === PRODUCT (CBV) ===
class ProductListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Product
    template_name = 'billing/product_list.html'
    context_object_name = 'items'
    paginate_by = 10
    export_title = 'Products'

    def _get_active_col_keys(self):
        """Devuelve las claves de columnas activas: GET ?cols > sesión > defecto."""
        valid = {c['key'] for c in ALL_PRODUCT_COLUMNS}

        cols_param = self.request.GET.get('cols', '').strip()
        if cols_param:
            keys = [k.strip() for k in cols_param.split(',') if k.strip() in valid]
            if keys:
                return keys

        stored = self.request.session.get('product_columns', [])
        keys = [k for k in stored if k in valid]
        if keys:
            return keys

        return DEFAULT_PRODUCT_COLUMNS[:]

    def get_export_fields(self):
        active_set = set(self._get_active_col_keys())
        return [
            (col['label'], col['accessor'])
            for col in ALL_PRODUCT_COLUMNS
            if col['key'] in active_set and col.get('exportable', True)
        ]

    def get_queryset(self):
        qs = Product.objects.select_related('brand', 'group').prefetch_related('suppliers')
        p = self.request.GET

        name = p.get('name', '').strip()
        brand = p.get('brand', '')
        group = p.get('group', '')
        supplier = p.get('supplier', '')
        price_min = p.get('price_min', '')
        price_max = p.get('price_max', '')
        stock_min = p.get('stock_min', '')
        stock_max = p.get('stock_max', '')
        is_active = p.get('is_active', '')

        if name:
            qs = qs.filter(name__icontains=name)
        if brand:
            qs = qs.filter(brand_id=brand)
        if group:
            qs = qs.filter(group_id=group)
        if supplier:
            qs = qs.filter(suppliers__id=supplier)
        if price_min:
            qs = qs.filter(unit_price__gte=price_min)
        if price_max:
            qs = qs.filter(unit_price__lte=price_max)
        if stock_min:
            qs = qs.filter(stock__gte=stock_min)
        if stock_max:
            qs = qs.filter(stock__lte=stock_max)
        if is_active == '1':
            qs = qs.filter(is_active=True)
        elif is_active == '0':
            qs = qs.filter(is_active=False)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['brands'] = Brand.objects.order_by('name')
        ctx['groups'] = ProductGroup.objects.order_by('name')
        ctx['suppliers'] = Supplier.objects.order_by('name')
        ctx['filters'] = self.request.GET

        active_keys = self._get_active_col_keys()
        ctx['all_columns'] = ALL_PRODUCT_COLUMNS
        ctx['active_column_keys'] = active_keys
        ctx['default_column_keys'] = DEFAULT_PRODUCT_COLUMNS
        ctx['all_columns_json'] = [
            {'key': c['key'], 'label': c['label']} for c in ALL_PRODUCT_COLUMNS
        ]
        return ctx


@login_required
def product_columns_save(request):
    """Guarda la selección de columnas del usuario en la sesión."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({'error': 'Invalid JSON'}, status=400)

    valid_keys = {c['key'] for c in ALL_PRODUCT_COLUMNS}
    cols = [k for k in data.get('columns', []) if k in valid_keys]

    if not cols:
        cols = DEFAULT_PRODUCT_COLUMNS[:]

    request.session['product_columns'] = cols
    return JsonResponse({'status': 'ok', 'columns': cols})


@login_required
def product_price(request, pk):
    """Devuelve el precio de un producto como JSON.

    Por defecto (uso en el formset de Invoice) devuelve final_price, el
    precio de venta con descuento aplicado. Con ?context=purchase (uso en
    el formset de Purchase) devuelve unit_price, el precio original sin
    descuento, ya que las compras no aplican el descuento de venta.
    """
    product = get_object_or_404(Product, pk=pk)
    if request.GET.get('context') == 'purchase':
        price = product.unit_price
    else:
        price = product.final_price
    return JsonResponse({
        'price': str(price),
        'applies_iva': product.applies_iva,
    })


@login_required
def products_by_supplier(request):
    """Devuelve los productos activos de un proveedor como JSON."""
    supplier_id = request.GET.get('supplier_id')
    products = Product.objects.none()
    if supplier_id:
        products = Product.objects.filter(
            suppliers__id=supplier_id, is_active=True
        ).order_by('name')

    data = [
        {
            'id': p.id,
            'name': p.name,
            'price': float(p.unit_price),
            'applies_iva': p.applies_iva,
        }
        for p in products
    ]
    return JsonResponse(data, safe=False)


class ProductDetailView(LoginRequiredMixin, DetailView):
    model = Product
    template_name = 'billing/product_detail.html'
    context_object_name = 'product'

class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

class ProductUpdateView(LoginRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')

class ProductDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Product; template_name = 'billing/product_confirm_delete.html'; success_url = reverse_lazy('billing:product_list'); staff_redirect_url = '/products/'

# === CUSTOMER (CBV) ===
class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer; template_name = 'billing/customer_list.html'; context_object_name = 'items'

class CustomerCreateView(LoginRequiredMixin, CreateView):
    model = Customer; fields = ['dni','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')

class CustomerUpdateView(LoginRequiredMixin, UpdateView):
    model = Customer; fields = ['dni','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')

class CustomerDeleteView(LoginRequiredMixin, StaffRequiredMixin, DeleteView):
    model = Customer; template_name = 'billing/customer_confirm_delete.html'; success_url = reverse_lazy('billing:customer_list'); staff_redirect_url = '/customers/'

# === INVOICE (FBV) ===
@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related('customer').all()
    return render(request, 'billing/invoice_list.html', {'items': invoices})

@login_required
def invoice_create(request):
    if request.method == 'POST':
        form = InvoiceForm(request.POST)
        formset = InvoiceDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():

            # Validate stock before persisting anything
            stock_errors = []
            for detail_form in formset:
                cd = detail_form.cleaned_data
                if not cd or cd.get('DELETE', False):
                    continue
                product = cd.get('product')
                quantity = cd.get('quantity') or 0
                if product and quantity > product.stock:
                    stock_errors.append(
                        f'Stock insuficiente para "{product.name}": '
                        f'solicitado {quantity}, disponible {product.stock}.'
                    )

            if stock_errors:
                for msg in stock_errors:
                    messages.error(request, msg)
            else:
                invoice = form.save(commit=False)
                invoice.save()
                formset.instance = invoice
                formset.save()

                # Deduct stock for each line
                for detail in invoice.details.all():
                    detail.product.stock -= detail.quantity
                    detail.product.save(update_fields=['stock'])

                details = invoice.details.all()
                subtotal_iva = sum(d.subtotal for d in details if d.applies_iva)
                subtotal_0 = sum(d.subtotal for d in details if not d.applies_iva)
                iva_amount = subtotal_iva * Decimal('0.15')

                invoice.subtotal_iva = subtotal_iva
                invoice.subtotal_0 = subtotal_0
                invoice.iva_amount = iva_amount
                invoice.subtotal = subtotal_iva + subtotal_0
                invoice.tax = iva_amount
                invoice.total = invoice.subtotal + invoice.tax
                invoice.save()
                messages.success(request, f'Invoice #{invoice.id} created! Total: ${invoice.total}')
                return redirect('billing:invoice_list')
    else:
        form = InvoiceForm()
        formset = InvoiceDetailFormSet()
    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Create Invoice',
    })

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})

@login_required
def invoice_delete(request, pk):
    invoice = get_object_or_404(Invoice, pk=pk)
    if request.method == 'POST':
        from creditos_ventas.models import PagoCuotaVenta

        if invoice.estado == 'PAGADA':
            PagoCuotaVenta.objects.filter(cuota__factura=invoice).delete()
            invoice.cuotas.all().delete()
            invoice_id = invoice.id
            invoice.delete()
            messages.success(request, f'Invoice #{invoice_id} deleted!')
            return redirect('billing:invoice_list')

        tiene_pagos = PagoCuotaVenta.objects.filter(
            cuota__factura=invoice
        ).exists()

        if tiene_pagos:
            messages.error(request, 'No se puede eliminar una factura con pagos parciales registrados.')
            return redirect('billing:invoice_list')

        invoice.cuotas.all().delete()

        invoice_id = invoice.id
        invoice.delete()
        messages.success(request, f'Invoice #{invoice_id} deleted!')
        return redirect('billing:invoice_list')
    return render(request, 'billing/invoice_confirm_delete.html', {'object': invoice})
