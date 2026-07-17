from django.core.paginator import Paginator
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import F
from decimal import Decimal
from .models import Purchase, PurchaseDetail
from .forms import PurchaseForm, PurchaseDetailFormSet, PurchaseFilterForm
from billing.models import Product
from shared.decorators import registrar_actividad

@login_required
def purchase_list(request):
    purchases = Purchase.objects.select_related('supplier').all()

    filter_form = PurchaseFilterForm(request.GET or None)
    if filter_form.is_valid():
        cd = filter_form.cleaned_data
        if cd.get('supplier'):
            purchases = purchases.filter(supplier=cd['supplier'])
        if cd.get('date_from'):
            purchases = purchases.filter(purchase_date__date__gte=cd['date_from'])
        if cd.get('date_to'):
            purchases = purchases.filter(purchase_date__date__lte=cd['date_to'])
        if cd.get('min_total') is not None:
            purchases = purchases.filter(total__gte=cd['min_total'])
        if cd.get('max_total') is not None:
            purchases = purchases.filter(total__lte=cd['max_total'])

    paginator = Paginator(purchases, 10)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'purchasing/purchase_list.html', {
        'items': page_obj,
        'page_obj': page_obj,
        'is_paginated': page_obj.has_other_pages(),
        'filter_form': filter_form,
    })

@login_required
@permission_required('purchasing.add_purchase', raise_exception=True)
def purchase_create(request):
    if request.method == 'POST':
        form = PurchaseForm(request.POST)
        formset = PurchaseDetailFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            purchase = form.save(commit=False)
            purchase.save()
            formset.instance = purchase
            formset.save()
            for detail in purchase.details.all():
                Product.objects.filter(pk=detail.product.pk).update(
                    stock=F('stock') + detail.quantity
                )
            subtotal = sum(d.subtotal for d in purchase.details.all())
            purchase.subtotal = subtotal
            purchase.tax = subtotal * Decimal('0.15')
            purchase.total = purchase.subtotal + purchase.tax
            purchase.save()
            registrar_actividad(request.user, 'CREAR', 'Compras', f'Creó compra #{purchase.id}', request)
            messages.success(request, f'Purchase #{purchase.id} created! Total: ${purchase.total}')
            return redirect('purchasing:purchase_list')
    else:
        form = PurchaseForm()
        formset = PurchaseDetailFormSet()
    return render(request, 'purchasing/purchase_form.html', {
        'form': form,
        'formset': formset,
        'title': 'Crear Compra',
    })

@login_required
def purchase_detail(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related('details__product'),
        pk=pk
    )
    return render(request, 'purchasing/purchase_detail.html', {'purchase': purchase})

@login_required
@permission_required('purchasing.delete_purchase', raise_exception=True)
def purchase_delete(request, pk):
    purchase = get_object_or_404(Purchase, pk=pk)
    if request.method == 'POST':
        purchase_id = purchase.id
        purchase.delete()
        registrar_actividad(request.user, 'ELIMINAR', 'Compras', f'Eliminó compra #{purchase_id}', request)
        messages.success(request, f'Purchase #{purchase_id} deleted!')
        return redirect('purchasing:purchase_list')
    return render(request, 'purchasing/purchase_confirm_delete.html', {'object': purchase})