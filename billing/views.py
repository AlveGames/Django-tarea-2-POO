import io
import json
from datetime import timedelta
from django.core.mail import EmailMultiAlternatives
from django.core.paginator import Paginator
from django.db.models import Sum
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.views.decorators.http import require_POST
from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.template.loader import render_to_string
from django.urls import reverse, reverse_lazy
from django.contrib.auth import login
from django.http import Http404, HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from .models import *
from .forms import SignUpForm, BrandForm, CustomerForm, ProductForm, InvoiceForm, InvoiceDetailFormSet
from .utils import generar_factura_electronica, generar_qr, generar_xml
from shared.mixins import ExportMixin
from shared.decorators import audit_action
from decimal import Decimal
from purchasing.models import Purchase

_MESES_ES = [
    'enero', 'febrero', 'marzo', 'abril', 'mayo', 'junio',
    'julio', 'agosto', 'septiembre', 'octubre', 'noviembre', 'diciembre',
]


def get_notifications(user):
    """Calcula las notificaciones del topbar según el rol del usuario.

    Cada preocupación se codifica una sola vez, en el bloque del rol al que
    pertenece "de forma nativa" (Vendedor u Analista de Compras); Administrador
    ve la unión de todo porque también satisface esos `or is_admin`, sin
    duplicar notificaciones.
    """
    notifications = []

    is_admin = user.is_superuser or user.groups.filter(name='Administrador').exists()
    is_vendedor = user.groups.filter(name='Vendedor').exists()
    is_analista = user.groups.filter(name='Analista de Compras').exists()

    if not (is_admin or is_vendedor or is_analista):
        return notifications

    hoy = timezone.localdate()

    # === ADMINISTRADOR (exclusivo) ===
    if is_admin:
        from django.contrib.auth.models import User as AuthUser
        nuevos_usuarios = AuthUser.objects.filter(date_joined__date=hoy).count()
        if nuevos_usuarios > 0:
            notifications.append({
                'tipo': 'info',
                'icono': 'bi-person-plus',
                'mensaje': f'{nuevos_usuarios} nuevo(s) usuario(s) registrado(s) hoy',
                'url': reverse('security:user_list'),
            })

    # === VENDEDOR (y Administrador) ===
    if is_vendedor or is_admin:
        facturas_credito_pendientes = Invoice.objects.filter(
            tipo_pago='CREDITO', estado='PENDIENTE'
        ).count()
        if facturas_credito_pendientes > 0:
            notifications.append({
                'tipo': 'info',
                'icono': 'bi-receipt',
                'mensaje': f'{facturas_credito_pendientes} factura(s) a crédito pendientes de pago',
                'url': reverse('creditos_ventas:factura_list') + '?estado=PENDIENTE',
            })

        from creditos_ventas.models import CuotaVenta
        cuotas_venta_vencidas = CuotaVenta.objects.filter(
            estado='PENDIENTE',
            fecha_vencimiento__lt=hoy,
        ).count()
        if cuotas_venta_vencidas > 0:
            notifications.append({
                'tipo': 'danger',
                'icono': 'bi-calendar-x',
                'mensaje': f'{cuotas_venta_vencidas} cuota(s) de crédito de ventas vencidas',
                'url': reverse('creditos_ventas:cuotas_pendientes'),
            })

    # === ANALISTA DE COMPRAS (y Administrador) ===
    if is_analista or is_admin:
        productos_bajo_stock = Product.objects.filter(stock__lt=5, is_active=True)
        for p in productos_bajo_stock:
            notifications.append({
                'tipo': 'warning',
                'icono': 'bi-box-seam',
                'mensaje': f'Stock bajo: {p.name} ({p.stock} unidades)',
                'url': reverse('billing:product_list'),
            })

        from creditos_compras.models import CuotaCompra
        cuotas_compra_vencidas = CuotaCompra.objects.filter(
            estado='PENDIENTE',
            fecha_vencimiento__lt=hoy,
        ).count()
        if cuotas_compra_vencidas > 0:
            notifications.append({
                'tipo': 'danger',
                'icono': 'bi-cart-x',
                'mensaje': f'{cuotas_compra_vencidas} cuota(s) de crédito de compras vencidas',
                'url': reverse('creditos_compras:cuotas_pendientes'),
            })

    return notifications


def _notification_key(notif):
    """Identificador estable de una notificación para llevar el control de leídas."""
    return f"{notif['tipo']}|{notif['mensaje']}"


def get_unread_notifications_count(user, request):
    """Notificaciones vigentes que el usuario todavía no marcó como leídas en esta sesión."""
    notifications = get_notifications(user)
    leidas = set(request.session.get('notif_leidas', []))
    return sum(1 for n in notifications if _notification_key(n) not in leidas)


@login_required
@require_POST
def marcar_notificaciones_leidas(request):
    """Guarda en la sesión las notificaciones vigentes como leídas (oculta el badge)."""
    notifications = get_notifications(request.user)
    request.session['notif_leidas'] = [_notification_key(n) for n in notifications]
    return JsonResponse({'status': 'ok'})


# === HOME ===
@login_required
def home(request):
    hoy = timezone.localdate()
    today_display = f'{hoy.day} de {_MESES_ES[hoy.month - 1]} de {hoy.year}'

    user = request.user
    is_admin = user.is_superuser or user.groups.filter(name='Administrador').exists()
    is_analista = user.groups.filter(name='Analista de Compras').exists()
    is_vendedor = user.groups.filter(name='Vendedor').exists()
    is_gerente = user.groups.filter(name='Gerente').exists()

    # Solo se consultan los conteos de las cards que el rol del usuario puede ver
    ve_gestion = is_admin or is_analista or is_gerente
    ve_ventas = is_admin or is_vendedor or is_gerente
    ve_compras = is_admin or is_analista or is_gerente

    total_brands = Brand.objects.count() if ve_gestion else 0
    total_products = Product.objects.count() if ve_gestion else 0
    total_customers = Customer.objects.count() if ve_ventas else 0
    total_invoices = Invoice.objects.count() if ve_ventas else 0
    creditos_ventas_pendientes = (
        Invoice.objects.filter(tipo_pago='CREDITO', estado='PENDIENTE').count() if ve_ventas else 0
    )
    total_purchases = Purchase.objects.count() if ve_compras else 0

    hace_7_dias = hoy - timedelta(days=6)
    ventas_labels = []
    ventas_data = []
    for i in range(7):
        dia = hace_7_dias + timedelta(days=i)
        total_dia = Invoice.objects.filter(invoice_date__date=dia).aggregate(t=Sum('total'))['t'] or Decimal('0')
        ventas_labels.append(dia.strftime('%d/%m'))
        ventas_data.append(float(total_dia))

    context = {
        'total_brands': total_brands,
        'total_products': total_products,
        'total_customers': total_customers,
        'total_invoices': total_invoices,
        'total_purchases': total_purchases,
        'creditos_ventas_pendientes': creditos_ventas_pendientes,
        'recent_invoices': Invoice.objects.all()[:5],
        'low_stock': Product.objects.filter(stock__lte=5, is_active=True),
        'today_display': today_display,
        'ventas_labels': ventas_labels,
        'ventas_data': ventas_data,
        'resumen_labels': [_('Facturas'), _('Compras'), _('Productos'), _('Clientes'), _('Marcas')],
        'resumen_data': [total_invoices, total_purchases, total_products, total_customers, total_brands],
        'notifications': get_notifications(request.user),
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
@permission_required('billing.add_brand', raise_exception=True)
def brand_create(request):
    if request.method == 'POST':
        form = BrandForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand created!')
            return redirect('billing:brand_list')
    else: form = BrandForm()
    return render(request, 'billing/brand_form.html', {'form': form, 'title': 'Crear Marca'})

@login_required
@audit_action('UPDATE_BRAND')
@permission_required('billing.change_brand', raise_exception=True)
def brand_update(request, pk):
    brand = get_object_or_404(Brand, pk=pk)
    if request.method == 'POST':
        form = BrandForm(request.POST, instance=brand)
        if form.is_valid():
            form.save()
            messages.success(request, 'Brand updated!')
            return redirect('billing:brand_list')
    else: form = BrandForm(instance=brand)
    return render(request, 'billing/brand_form.html', {'form': form, 'title': 'Editar Marca'})

@login_required
@audit_action('DELETE_BRAND')
@permission_required('billing.delete_brand', raise_exception=True)
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

class ProductGroupCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.add_productgroup'
    raise_exception = True

class ProductGroupUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = ProductGroup; fields = ['name','is_active']; template_name = 'billing/productgroup_form.html'; success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.change_productgroup'
    raise_exception = True

class ProductGroupDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = ProductGroup; template_name = 'billing/productgroup_confirm_delete.html'; success_url = reverse_lazy('billing:productgroup_list')
    permission_required = 'billing.delete_productgroup'
    raise_exception = True

# === SUPPLIER (CBV) ===
class SupplierListView(LoginRequiredMixin, ListView):
    model = Supplier; template_name = 'billing/supplier_list.html'; context_object_name = 'items'

class SupplierCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Supplier; fields = ['name','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.add_supplier'
    raise_exception = True

class SupplierUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Supplier; fields = ['name','contact_name','email','phone','address','is_active']; template_name = 'billing/supplier_form.html'; success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.change_supplier'
    raise_exception = True

class SupplierDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Supplier; template_name = 'billing/supplier_confirm_delete.html'; success_url = reverse_lazy('billing:supplier_list')
    permission_required = 'billing.delete_supplier'
    raise_exception = True

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

class ProductCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.add_product'
    raise_exception = True

class ProductUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Product
    form_class = ProductForm
    template_name = 'billing/product_form.html'
    success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.change_product'
    raise_exception = True

class ProductDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Product; template_name = 'billing/product_confirm_delete.html'; success_url = reverse_lazy('billing:product_list')
    permission_required = 'billing.delete_product'
    raise_exception = True

# === CUSTOMER (CBV) ===
class CustomerListView(LoginRequiredMixin, ListView):
    model = Customer; template_name = 'billing/customer_list.html'; context_object_name = 'items'; paginate_by = 10

class CustomerCreateView(LoginRequiredMixin, PermissionRequiredMixin, CreateView):
    model = Customer; fields = ['dni','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.add_customer'
    raise_exception = True

class CustomerUpdateView(LoginRequiredMixin, PermissionRequiredMixin, UpdateView):
    model = Customer; fields = ['dni','first_name','last_name','email','phone','address','is_active']; template_name = 'billing/customer_form.html'; success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.change_customer'
    raise_exception = True

class CustomerDeleteView(LoginRequiredMixin, PermissionRequiredMixin, DeleteView):
    model = Customer; template_name = 'billing/customer_confirm_delete.html'; success_url = reverse_lazy('billing:customer_list')
    permission_required = 'billing.delete_customer'
    raise_exception = True


@login_required
@permission_required('billing.add_customer', raise_exception=True)
def crear_cliente_ajax(request):
    """Crea un Customer vía AJAX desde el modal del formulario de factura."""
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            cliente = form.save()
            return JsonResponse({
                'success': True,
                'id': cliente.id,
                'nombre': str(cliente),
            })
        return JsonResponse({
            'success': False,
            'errors': form.errors.as_json(),
        })
    return JsonResponse({'success': False})


# === INVOICE (FBV) ===
@login_required
def invoice_list(request):
    invoices = Invoice.objects.select_related('customer').all()
    paginator = Paginator(invoices, 10)
    page_obj = paginator.get_page(request.GET.get('page'))
    return render(request, 'billing/invoice_list.html', {
        'items': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
    })

def _build_invoice_pdf(invoice):
    """Genera el PDF de una factura en memoria y devuelve los bytes."""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import (
        Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle, HRFlowable,
    )

    purple = colors.HexColor('#4A00E0')
    dark = colors.HexColor('#343a40')
    light = colors.HexColor('#f8f9fa')
    grey = colors.HexColor('#dee2e6')

    styles = getSampleStyleSheet()
    brand_style = ParagraphStyle(
        'Brand', parent=styles['Title'], textColor=purple, fontSize=22, spaceAfter=0,
    )
    info_style = ParagraphStyle('Info', parent=styles['Normal'], fontSize=10, leading=14)
    footer_style = ParagraphStyle(
        'Footer', parent=styles['Normal'], fontSize=8, textColor=colors.grey, alignment=1,
    )

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=letter,
        leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.5 * cm, bottomMargin=1.5 * cm,
    )

    elements = [
        Paragraph('TecnoStock', brand_style),
        Paragraph('Sistema de Ventas y Facturación', info_style),
        Spacer(1, 12),
        HRFlowable(width='100%', color=grey, thickness=1),
        Spacer(1, 12),
        Paragraph(f'<b>Factura #{invoice.id}</b>', styles['Heading2']),
        Paragraph(f'<b>Fecha:</b> {invoice.invoice_date.strftime("%d/%m/%Y")}', info_style),
        Paragraph(f'<b>Cliente:</b> {invoice.customer}', info_style),
        Paragraph(f'<b>DNI/RUC:</b> {invoice.customer.dni}', info_style),
    ]
    if invoice.numero_autorizacion:
        elements.append(Paragraph(f'<b>Número de autorización:</b> {invoice.numero_autorizacion}', info_style))
    elements.append(Spacer(1, 16))

    data = [['Producto', 'Cantidad', 'Precio Unit.', 'Subtotal']]
    for detail in invoice.details.all():
        data.append([
            detail.product.name,
            str(detail.quantity),
            f'${detail.unit_price}',
            f'${detail.subtotal}',
        ])

    table = Table(data, colWidths=[8 * cm, 2.5 * cm, 3 * cm, 3 * cm])
    style_cmds = [
        ('BACKGROUND', (0, 0), (-1, 0), dark),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ('GRID', (0, 0), (-1, -1), 0.4, grey),
    ]
    for i in range(2, len(data), 2):
        style_cmds.append(('BACKGROUND', (0, i), (-1, i), light))
    table.setStyle(TableStyle(style_cmds))
    elements.append(table)
    elements.append(Spacer(1, 16))

    totals = Table(
        [
            ['Subtotal:', f'${invoice.subtotal}'],
            ['IVA (15%):', f'${invoice.tax}'],
            ['TOTAL:', f'${invoice.total}'],
        ],
        colWidths=[13.5 * cm, 3 * cm],
    )
    totals.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, 1), 'Helvetica'),
        ('FONTNAME', (0, 2), (-1, 2), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 10),
        ('FONTSIZE', (0, 2), (-1, 2), 12),
        ('LINEABOVE', (0, 2), (-1, 2), 0.75, dark),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(totals)
    elements.append(Spacer(1, 40))
    elements.append(HRFlowable(width='100%', color=grey, thickness=1))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(
        'TecnoStock &middot; Quito, Ecuador &middot; contacto@tecnostock.com &middot; +593 2 000 0000',
        footer_style,
    ))

    def _draw_sri_seal(canvas, doc_):
        """Dibuja el QR y el sello 'DOCUMENTO AUTORIZADO POR EL SRI' en la
        esquina inferior derecha de cada página."""
        canvas.saveState()
        qr_bytes = generar_qr(invoice)
        qr_reader = ImageReader(io.BytesIO(qr_bytes))
        qr_size = 2.5 * cm
        x = letter[0] - 2 * cm - qr_size
        y = 1.4 * cm
        canvas.drawImage(qr_reader, x, y, width=qr_size, height=qr_size, mask='auto')
        canvas.setFont('Helvetica-Bold', 6.5)
        canvas.setFillColor(colors.HexColor('#198754'))
        canvas.drawCentredString(x + qr_size / 2, y - 0.3 * cm, 'DOCUMENTO AUTORIZADO POR EL SRI')
        canvas.restoreState()

    if invoice.numero_autorizacion:
        doc.build(elements, onFirstPage=_draw_sri_seal, onLaterPages=_draw_sri_seal)
    else:
        doc.build(elements)

    pdf = buffer.getvalue()
    buffer.close()
    return pdf


def send_invoice_email(invoice):
    """Envía la factura en PDF al correo del cliente, si tiene uno registrado."""
    if not invoice.customer.email:
        return

    html_message = render_to_string('emails/factura.html', {'invoice': invoice})
    pdf = _build_invoice_pdf(invoice)

    email = EmailMultiAlternatives(
        subject=f'TecnoStock - Factura #{invoice.id}',
        body=f'Adjuntamos el detalle de su factura #{invoice.id}. Total: ${invoice.total}',
        from_email=None,
        to=[invoice.customer.email],
    )
    email.attach_alternative(html_message, 'text/html')
    email.attach(f'factura_{invoice.id}.pdf', pdf, 'application/pdf')
    if invoice.xml_generado:
        xml = generar_xml(invoice)
        email.attach(f'factura_{invoice.id}.xml', xml, 'application/xml')
    email.send(fail_silently=True)


@login_required
@permission_required('billing.add_invoice', raise_exception=True)
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

                generar_factura_electronica(invoice)
                send_invoice_email(invoice)

                messages.success(request, f'Invoice #{invoice.id} created! Total: ${invoice.total}')
                return redirect('billing:invoice_list')
    else:
        form = InvoiceForm()
        formset = InvoiceDetailFormSet()
    return render(request, 'billing/invoice_form.html', {
        'form': form,
        'formset': formset,
        'customer_form': CustomerForm(),
        'title': 'Crear Factura',
    })

@login_required
def invoice_detail(request, pk):
    invoice = get_object_or_404(
        Invoice.objects.select_related('customer').prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'billing/invoice_detail.html', {'invoice': invoice})

@login_required
def descargar_xml(request, pk):
    factura = get_object_or_404(Invoice, pk=pk)
    if not factura.xml_generado:
        messages.error(request, 'Esta factura no tiene un XML de facturación electrónica generado.')
        return redirect('billing:invoice_detail', pk=pk)
    xml = generar_xml(factura)
    response = HttpResponse(xml, content_type='application/xml')
    response['Content-Disposition'] = f'attachment; filename="factura_{pk}.xml"'
    return response

@login_required
def invoice_qr(request, pk):
    factura = get_object_or_404(
        Invoice.objects.select_related('customer'), pk=pk
    )
    if not factura.numero_autorizacion:
        raise Http404
    qr_png = generar_qr(factura)
    return HttpResponse(qr_png, content_type='image/png')

@login_required
@permission_required('billing.delete_invoice', raise_exception=True)
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
