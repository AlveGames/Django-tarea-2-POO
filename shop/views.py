import random
import string
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.generic import DetailView, ListView, TemplateView, UpdateView

from billing.models import Customer, Invoice, InvoiceDetail, Product, ProductGroup
from billing.views import send_invoice_email
from shared.decorators import group_required
from shared.mixins import GroupRequiredMixin
from .forms import CheckoutForm
from .models import PerfilCliente, ShopOrder, ShopOrderDetail

IVA_RATE = Decimal('0.15')

# Roles autorizados a comprar en la tienda: el Cliente y los roles internos
ROLES_TIENDA = ['Cliente', 'Administrador', 'Vendedor', 'Analista de Compras']


def _get_cart(request):
    return request.session.setdefault('cart', {})


def _save_cart(request, cart):
    request.session['cart'] = cart
    request.session.modified = True


def _cart_totals(cart):
    items = []
    subtotal = Decimal('0')
    subtotal_iva = Decimal('0')
    for product_id, item in cart.items():
        item_subtotal = Decimal(item['subtotal'])
        items.append({'product_id': product_id, **item})
        subtotal += item_subtotal
        if item.get('applies_iva'):
            subtotal_iva += item_subtotal

    iva_amount = (subtotal_iva * IVA_RATE).quantize(Decimal('0.01'))
    total = subtotal + iva_amount

    return {
        'items': items,
        'subtotal': subtotal,
        'subtotal_iva': subtotal_iva,
        'iva_amount': iva_amount,
        'total': total,
    }


def _generate_order_number():
    while True:
        suffix = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        order_number = f'SHP-{suffix}'
        if not ShopOrder.objects.filter(order_number=order_number).exists():
            return order_number


def crear_factura_desde_shop(shop_order):
    """Genera en billing la Invoice correspondiente a una ShopOrder pagada."""
    name_parts = shop_order.full_name.split()
    first_name = name_parts[0] if name_parts else shop_order.full_name
    last_name = ' '.join(name_parts[1:])

    customer, _created = Customer.objects.get_or_create(
        dni=shop_order.dni,
        defaults={
            'first_name': first_name,
            'last_name': last_name,
            'email': shop_order.email,
            'phone': shop_order.phone,
            'address': shop_order.address,
        },
    )

    invoice = Invoice.objects.create(
        customer=customer,
        subtotal=shop_order.subtotal,
        subtotal_iva=shop_order.subtotal_iva,
        subtotal_0=shop_order.subtotal - shop_order.subtotal_iva,
        tax=shop_order.iva_amount,
        iva_amount=shop_order.iva_amount,
        total=shop_order.total,
        tipo_pago='CONTADO',
        estado='PAGADA',
        saldo=0,
    )

    for detail in shop_order.details.all():
        InvoiceDetail.objects.create(
            invoice=invoice,
            product=detail.product,
            quantity=detail.quantity,
            unit_price=detail.unit_price,
            applies_iva=detail.product.applies_iva,
        )

    shop_order.invoice = invoice
    shop_order.save(update_fields=['invoice'])

    return invoice


class CatalogView(ListView):
    model = Product
    template_name = 'shop/catalog.html'
    context_object_name = 'products'
    paginate_by = 12

    def get_queryset(self):
        qs = Product.objects.filter(is_active=True).select_related('group', 'brand')
        group_id = self.request.GET.get('group')
        if group_id:
            qs = qs.filter(group_id=group_id)
        query = self.request.GET.get('q')
        if query:
            qs = qs.filter(name__icontains=query)
        return qs.order_by('name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['groups'] = ProductGroup.objects.filter(is_active=True).order_by('name')
        context['selected_group'] = self.request.GET.get('group', '')
        context['query'] = self.request.GET.get('q', '')
        return context


class CartView(GroupRequiredMixin, TemplateView):
    template_name = 'shop/cart.html'
    group_required = ROLES_TIENDA
    group_redirect_url = 'shop:catalog'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_cart_totals(_get_cart(self.request)))
        return context


@group_required(*ROLES_TIENDA, redirect_url='shop:catalog')
def add_to_cart(request, pk):
    product = get_object_or_404(Product, pk=pk, is_active=True)
    try:
        quantity = int(request.POST.get('quantity', 1))
    except (TypeError, ValueError):
        quantity = 1
    quantity = max(quantity, 1)

    cart = _get_cart(request)
    key = str(pk)

    if key in cart:
        cart[key]['quantity'] += quantity
    else:
        cart[key] = {
            'name': product.name,
            'original_price': str(product.unit_price),
            'discount': str(product.discount),
            'unit_price': str(product.final_price),
            'quantity': quantity,
            'applies_iva': product.applies_iva,
            'image': product.image.url if product.image else '',
        }

    cart[key]['subtotal'] = str(Decimal(cart[key]['unit_price']) * cart[key]['quantity'])
    _save_cart(request, cart)
    messages.success(request, f'"{product.name}" agregado al carrito.')
    return redirect('shop:catalog')


@group_required(*ROLES_TIENDA, redirect_url='shop:catalog')
def remove_from_cart(request, pk):
    cart = _get_cart(request)
    key = str(pk)
    if key in cart:
        del cart[key]
        _save_cart(request, cart)
        messages.success(request, 'Producto eliminado del carrito.')
    return redirect('shop:cart')


@group_required(*ROLES_TIENDA, redirect_url='shop:catalog')
def update_cart(request, pk):
    cart = _get_cart(request)
    key = str(pk)
    if key in cart and request.method == 'POST':
        try:
            quantity = int(request.POST.get('quantity', 1))
        except (TypeError, ValueError):
            quantity = 1

        if quantity <= 0:
            del cart[key]
            messages.success(request, 'Producto eliminado del carrito.')
        else:
            cart[key]['quantity'] = quantity
            cart[key]['subtotal'] = str(Decimal(cart[key]['unit_price']) * quantity)

        _save_cart(request, cart)
    return redirect('shop:cart')


class CheckoutView(GroupRequiredMixin, TemplateView):
    template_name = 'shop/checkout.html'
    group_required = ROLES_TIENDA
    group_redirect_url = 'shop:catalog'

    def get(self, request, *args, **kwargs):
        if not _get_cart(request):
            messages.info(request, 'Tu carrito está vacío.')
            return redirect('shop:catalog')
        return super().get(request, *args, **kwargs)

    def get_initial(self):
        initial = {}
        initial['full_name'] = self.request.user.get_full_name()
        initial['email'] = self.request.user.email
        try:
            perfil = self.request.user.perfil
            if perfil.first_name or perfil.last_name:
                initial['full_name'] = f'{perfil.first_name} {perfil.last_name}'.strip()
            initial['phone'] = perfil.phone
            initial['address'] = perfil.address
            initial['dni'] = perfil.dni
        except PerfilCliente.DoesNotExist:
            pass
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'form' not in context:
            context['form'] = CheckoutForm(initial=self.get_initial())
        context.update(_cart_totals(_get_cart(self.request)))
        return context


@group_required(*ROLES_TIENDA, redirect_url='shop:catalog')
def process_payment(request):
    if request.method != 'POST':
        return redirect('shop:checkout')

    cart = _get_cart(request)
    if not cart:
        messages.error(request, 'Tu carrito está vacío.')
        return redirect('shop:catalog')

    form = CheckoutForm(request.POST)
    if not form.is_valid():
        context = {'form': form}
        context.update(_cart_totals(cart))
        return render(request, 'shop/checkout.html', context)

    cd = form.cleaned_data
    payment_method = cd['payment_method']

    card_last4 = ''
    payment_reference = ''
    if payment_method == 'card':
        card_last4 = cd['card_number'].replace(' ', '')[-4:]
    elif payment_method == 'paypal':
        payment_reference = cd['paypal_email']
    elif payment_method == 'transfer':
        payment_reference = cd['bank_account']

    # Validar stock disponible antes de confirmar la orden
    stock_errors = []
    for product_id, item in cart.items():
        product = get_object_or_404(Product, pk=product_id)
        if item['quantity'] > product.stock:
            stock_errors.append(
                f'Stock insuficiente para "{product.name}": '
                f'solicitado {item["quantity"]}, disponible {product.stock}.'
            )
    if stock_errors:
        for msg in stock_errors:
            messages.error(request, msg)
        context = {'form': form}
        context.update(_cart_totals(cart))
        return render(request, 'shop/checkout.html', context)

    totals = _cart_totals(cart)

    order = ShopOrder.objects.create(
        user=request.user,
        full_name=cd['full_name'],
        email=cd['email'],
        phone=cd['phone'],
        address=cd['address'],
        dni=cd['dni'],
        order_number=_generate_order_number(),
        status='paid',
        payment_method=payment_method,
        card_last4=card_last4,
        payment_reference=payment_reference,
        payment_status='approved',
        subtotal=totals['subtotal'],
        subtotal_iva=totals['subtotal_iva'],
        iva_amount=totals['iva_amount'],
        total=totals['total'],
    )

    for product_id, item in cart.items():
        product = get_object_or_404(Product, pk=product_id)
        quantity = item['quantity']
        ShopOrderDetail.objects.create(
            order=order,
            product=product,
            quantity=quantity,
            original_price=Decimal(item['original_price']),
            discount=Decimal(item['discount']),
            unit_price=Decimal(item['unit_price']),
            subtotal=Decimal(item['subtotal']),
        )
        product.stock -= quantity
        product.save(update_fields=['stock'])

    request.session['cart'] = {}
    request.session.modified = True

    invoice = crear_factura_desde_shop(order)
    send_invoice_email(invoice)

    messages.success(request, f'¡Pago aprobado! Orden {order.order_number} creada.')
    return redirect('shop:receipt', pk=order.pk)


class OrderReceiptView(LoginRequiredMixin, DetailView):
    model = ShopOrder
    template_name = 'shop/receipt.html'
    context_object_name = 'order'

    def get_queryset(self):
        qs = ShopOrder.objects.prefetch_related('details__product')
        if not (self.request.user.is_staff or self.request.user.is_superuser):
            qs = qs.filter(user=self.request.user)
        return qs


class MisOrdenesView(LoginRequiredMixin, ListView):
    """Historial de órdenes de compra del cliente logueado."""
    model = ShopOrder
    template_name = 'shop/mis_ordenes.html'
    context_object_name = 'orders'
    paginate_by = 10

    def get_queryset(self):
        return ShopOrder.objects.filter(
            user=self.request.user
        ).prefetch_related('details__product').order_by('-created_at')


class PerfilView(LoginRequiredMixin, UpdateView):
    """Edición del perfil del cliente logueado (datos + avatar)."""
    model = PerfilCliente
    fields = ['first_name', 'last_name', 'phone', 'address', 'dni', 'avatar']
    template_name = 'shop/perfil.html'
    success_url = reverse_lazy('shop:perfil')

    def get_object(self):
        return self.request.user.perfil

    def form_valid(self, form):
        messages.success(self.request, 'Perfil actualizado correctamente.')
        return super().form_valid(form)
