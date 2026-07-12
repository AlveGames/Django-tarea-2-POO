import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from purchasing.models import Purchase
from shared.mixins import ExportMixin
from .forms import CompraCreditoForm, GenerarCuotasCompraForm, PagoCuotaCompraForm, PagoMultipleCuotasCompraForm
from .models import CuotaCompra, PagoCuotaCompra


def add_months(source_date, months):
    """Suma `months` meses a `source_date`, ajustando el día si el mes destino es más corto."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# === COMPRA (CBV) ===

class CompraListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Purchase
    template_name = 'creditos_compras/compra_list.html'
    context_object_name = 'compras'
    export_title = 'Compras'
    paginate_by = 10

    def get_export_fields(self):
        return [
            ('Número', lambda obj: f'#{obj.pk}'),
            ('Fecha', lambda obj: obj.purchase_date.strftime('%d/%m/%Y')),
            ('Proveedor', 'supplier__name'),
            ('Total', 'total'),
            ('Tipo Pago', 'tipo_pago'),
            ('Saldo', 'saldo'),
            ('Estado', 'estado'),
        ]

    def get_queryset(self):
        qs = Purchase.objects.select_related('supplier').order_by('-purchase_date')
        p = self.request.GET

        proveedor = p.get('proveedor', '').strip()
        tipo_pago = p.get('tipo_pago', '')
        estado = p.get('estado', '')
        fecha_desde = p.get('fecha_desde', '')
        fecha_hasta = p.get('fecha_hasta', '')

        if proveedor:
            qs = qs.filter(Q(supplier__name__icontains=proveedor))
        if tipo_pago:
            qs = qs.filter(tipo_pago=tipo_pago)
        if estado:
            qs = qs.filter(estado=estado)
        if fecha_desde:
            qs = qs.filter(purchase_date__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(purchase_date__date__lte=fecha_hasta)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filters'] = self.request.GET
        return ctx


class CompraDetailView(LoginRequiredMixin, DetailView):
    model = Purchase
    context_object_name = 'compra'
    template_name = 'creditos_compras/compra_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cuotas'] = self.object.cuotas.all().order_by('numero')
        context['total_pagado'] = self.object.total - self.object.saldo
        return context


class CompraCreateView(LoginRequiredMixin, CreateView):
    model = Purchase
    form_class = CompraCreditoForm
    template_name = 'creditos_compras/compra_form.html'

    def form_valid(self, form):
        compra = form.save(commit=False)
        if compra.tipo_pago == 'CONTADO':
            compra.estado = 'PAGADA'
            compra.saldo = 0
        else:
            compra.estado = 'PENDIENTE'
            compra.saldo = compra.total
        compra.save()
        self.object = compra

        messages.success(self.request, f'Compra #{compra.pk} creada correctamente.')
        if compra.tipo_pago == 'CREDITO':
            numero_cuotas = form.cleaned_data.get('numero_cuotas') or ''
            url = reverse('creditos_compras:generar_cuotas', kwargs={'pk': compra.pk})
            return redirect(f'{url}?numero_cuotas={numero_cuotas}')
        return redirect('creditos_compras:compra_list')


class CompraUpdateView(LoginRequiredMixin, UpdateView):
    model = Purchase
    form_class = CompraCreditoForm
    template_name = 'creditos_compras/compra_form.html'
    success_url = reverse_lazy('creditos_compras:compra_list')

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado == 'PAGADA':
            messages.error(request, 'No se puede modificar una compra pagada.')
            return redirect('creditos_compras:compra_list')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['numero_cuotas'] = self.object.cuotas.count()
        return initial

    def _regenerar_cuotas(self, compra, numero_cuotas_nuevo):
        """Ajusta las cuotas de `compra` al nuevo número solicitado.

        Solo se eliminan/regeneran las cuotas PENDIENTES sin pagos. Las que ya
        tienen pagos registrados se conservan tal cual y se avisa al usuario.
        """
        numero_cuotas_actual = compra.cuotas.count()
        if not numero_cuotas_nuevo or numero_cuotas_nuevo == numero_cuotas_actual:
            return

        cuotas_con_pagos = compra.cuotas.filter(pagocuotacompra__isnull=False).distinct()
        cuotas_sin_pagos = compra.cuotas.filter(pagocuotacompra__isnull=True)
        kept_count = cuotas_con_pagos.count()

        if cuotas_con_pagos.exists():
            messages.warning(
                self.request,
                'Algunas cuotas ya tienen pagos registrados y no se modificaron.'
            )

        nuevas_a_crear = numero_cuotas_nuevo - kept_count
        if nuevas_a_crear < 1:
            messages.warning(
                self.request,
                f'No se pudo ajustar a {numero_cuotas_nuevo} cuotas: ya existen '
                f'{kept_count} cuotas con pagos registrados.'
            )
            return

        kept_valor_total = sum((c.valor for c in cuotas_con_pagos), Decimal('0.00'))
        max_numero_kept = cuotas_con_pagos.aggregate(m=Max('numero'))['m'] or 0

        cuotas_sin_pagos.delete()

        monto_restante = compra.total - kept_valor_total
        valor_base = (monto_restante / nuevas_a_crear).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        fecha_base = compra.purchase_date.date()

        acumulado = Decimal('0.00')
        for i in range(1, nuevas_a_crear + 1):
            numero = max_numero_kept + i
            if i == nuevas_a_crear:
                valor = monto_restante - acumulado
            else:
                valor = valor_base
                acumulado += valor
            CuotaCompra.objects.create(
                compra=compra,
                numero=numero,
                fecha_vencimiento=add_months(fecha_base, numero),
                valor=valor,
                saldo=valor,
            )

        messages.success(self.request, 'Las cuotas se regeneraron con el nuevo número.')

    def _redistribuir_cuotas_pendientes(self, compra):
        """Si el total de la compra cambió, redistribuye el saldo restante
        (total - pagado) entre las cuotas PENDIENTES que aún no tienen pagos.
        """
        cuotas_pendientes = list(
            compra.cuotas.filter(estado='PENDIENTE', pagocuotacompra__isnull=True).order_by('numero')
        )
        if not cuotas_pendientes:
            return

        pagado = compra.cuotas.filter(estado='PAGADA').aggregate(total=Sum('valor'))['total'] or Decimal('0.00')
        saldo_restante = compra.total - pagado
        valor_base = (saldo_restante / len(cuotas_pendientes)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        acumulado = Decimal('0.00')
        for i, cuota in enumerate(cuotas_pendientes, start=1):
            if i == len(cuotas_pendientes):
                valor = saldo_restante - acumulado
            else:
                valor = valor_base
                acumulado += valor
            cuota.valor = valor
            cuota.saldo = valor
            cuota.save()

    def form_valid(self, form):
        compra = form.save(commit=False)

        total_pagado = PagoCuotaCompra.objects.filter(
            cuota__compra=compra
        ).aggregate(total=Sum('valor'))['total'] or Decimal('0.00')

        if compra.total < total_pagado:
            form.add_error(
                'total',
                f'El total no puede ser menor a lo ya pagado (${total_pagado}). '
                f'Ya se han registrado ${total_pagado} en pagos.'
            )
            return self.form_invalid(form)

        if compra.tipo_pago == 'CONTADO':
            compra.estado = 'PAGADA'
            compra.saldo = 0
            compra.save()
        else:
            compra.save()
            numero_cuotas_nuevo = form.cleaned_data.get('numero_cuotas')
            self._regenerar_cuotas(compra, numero_cuotas_nuevo)
            self._redistribuir_cuotas_pendientes(compra)

            if compra.cuotas.exists():
                compra.estado = 'PENDIENTE' if compra.cuotas.exclude(estado='PAGADA').exists() else 'PAGADA'
                compra.saldo = sum((c.saldo for c in compra.cuotas.all()), Decimal('0.00'))
            else:
                compra.estado = 'PENDIENTE'
                compra.saldo = compra.total
            compra.save()

        self.object = compra
        messages.success(self.request, f'Compra #{compra.pk} actualizada correctamente.')
        return redirect(self.success_url)


class CompraDeleteView(LoginRequiredMixin, DeleteView):
    model = Purchase
    template_name = 'creditos_compras/compra_confirm_delete.html'
    success_url = reverse_lazy('creditos_compras:compra_list')

    def post(self, request, *args, **kwargs):
        # Django 6's BaseDeleteView.post() llama a form_valid() -> object.delete()
        # directamente, sin pasar por delete(). Lo redirigimos para que nuestra
        # lógica de borrado en cascada sí se ejecute.
        compra = self.get_object()

        if compra.estado == 'PAGADA':
            PagoCuotaCompra.objects.filter(cuota__compra=compra).delete()
            compra.cuotas.all().delete()
            self.object = compra
            return super().post(request, *args, **kwargs)

        tiene_pagos = PagoCuotaCompra.objects.filter(
            cuota__compra=compra
        ).exists()

        if tiene_pagos:
            messages.error(request, 'No se puede eliminar una compra con pagos parciales registrados.')
            return redirect('creditos_compras:compra_list')

        compra.cuotas.all().delete()

        self.object = compra
        return super().post(request, *args, **kwargs)


# === CUOTAS (CBV) ===

class GenerarCuotasCompraView(LoginRequiredMixin, View):

    def get_initial(self):
        initial = {}
        numero_cuotas = self.request.GET.get('numero_cuotas', '')
        if numero_cuotas:
            initial['numero_cuotas'] = numero_cuotas
        return initial

    def get(self, request, pk):
        compra = get_object_or_404(Purchase, pk=pk)
        if compra.cuotas.exists():
            messages.warning(request, 'Esta compra ya tiene cuotas generadas.')
            return redirect('creditos_compras:cuota_list', pk=compra.pk)
        form = GenerarCuotasCompraForm(initial=self.get_initial())
        return render(request, 'creditos_compras/generar_cuotas.html', {'form': form, 'compra': compra})

    def post(self, request, pk):
        compra = get_object_or_404(Purchase, pk=pk)
        if compra.cuotas.exists():
            messages.warning(request, 'Esta compra ya tiene cuotas generadas.')
            return redirect('creditos_compras:cuota_list', pk=compra.pk)

        form = GenerarCuotasCompraForm(request.POST)
        if not form.is_valid():
            return render(request, 'creditos_compras/generar_cuotas.html', {'form': form, 'compra': compra})

        numero_cuotas = form.cleaned_data['numero_cuotas']
        total = compra.total
        valor_base = (total / numero_cuotas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        fecha_base = compra.purchase_date.date()

        acumulado = Decimal('0.00')
        for i in range(1, numero_cuotas + 1):
            if i == numero_cuotas:
                valor = total - acumulado
            else:
                valor = valor_base
                acumulado += valor
            CuotaCompra.objects.create(
                compra=compra,
                numero=i,
                fecha_vencimiento=add_months(fecha_base, i),
                valor=valor,
                saldo=valor,
            )

        messages.success(request, f'{numero_cuotas} cuotas generadas correctamente.')
        return redirect('creditos_compras:cuota_list', pk=compra.pk)


class CuotaCompraListView(LoginRequiredMixin, ExportMixin, ListView):
    model = CuotaCompra
    template_name = 'creditos_compras/cuota_list.html'
    context_object_name = 'cuotas'
    paginate_by = 10

    def get_export_fields(self):
        return [
            ('Número', 'numero'),
            ('Fecha Vencimiento', lambda obj: obj.fecha_vencimiento.strftime('%d/%m/%Y')),
            ('Valor', 'valor'),
            ('Saldo', 'saldo'),
            ('Estado', 'estado'),
        ]

    def get_queryset(self):
        self.compra = get_object_or_404(Purchase, pk=self.kwargs['pk'])
        self.export_title = f'Cuotas - Compra #{self.compra.pk}'
        return CuotaCompra.objects.filter(compra=self.compra).order_by('numero')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['compra'] = self.compra
        total = self.compra.cuotas.count()
        pagadas = self.compra.cuotas.filter(estado='PAGADA').count()
        ctx['total_cuotas'] = total
        ctx['cuotas_pagadas'] = pagadas
        ctx['progreso_pct'] = int((pagadas / total) * 100) if total else 0
        return ctx


class CuotasCompraPendientesView(LoginRequiredMixin, ListView):
    model = CuotaCompra
    template_name = 'creditos_compras/cuotas_pendientes.html'
    context_object_name = 'cuotas'
    paginate_by = 10

    def get_queryset(self):
        return (
            CuotaCompra.objects
            .filter(estado='PENDIENTE')
            .select_related('compra', 'compra__supplier')
            .order_by('fecha_vencimiento')
        )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        hoy = timezone.localdate()
        ctx['hoy'] = hoy
        for cuota in ctx['cuotas']:
            cuota.dias_diff = (cuota.fecha_vencimiento - hoy).days
            cuota.dias_abs = abs(cuota.dias_diff)
        return ctx


# === PAGOS (CBV) ===

class RegistrarPagoCompraView(LoginRequiredMixin, CreateView):
    model = PagoCuotaCompra
    form_class = PagoCuotaCompraForm
    template_name = 'creditos_compras/registrar_pago.html'

    def dispatch(self, request, *args, **kwargs):
        self.cuota = get_object_or_404(CuotaCompra, pk=self.kwargs['pk'])
        if self.cuota.estado == 'PAGADA':
            messages.error(request, 'Esta cuota ya está completamente pagada.')
            return redirect('creditos_compras:cuota_list', pk=self.cuota.compra.pk)
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['cuota'] = self.cuota
        return kwargs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuota'] = self.cuota
        return ctx

    def form_valid(self, form):
        valor = form.cleaned_data['valor']
        if valor <= 0:
            form.add_error('valor', 'El valor del pago debe ser mayor a cero.')
            return self.form_invalid(form)
        if valor > self.cuota.saldo:
            form.add_error('valor', 'El pago supera el saldo de la cuota.')
            return self.form_invalid(form)

        pago = form.save(commit=False)
        pago.cuota = self.cuota
        pago.save()
        self.object = pago

        self.cuota.saldo -= valor
        if self.cuota.saldo <= 0:
            self.cuota.saldo = 0
            self.cuota.estado = 'PAGADA'
        self.cuota.save()

        compra = self.cuota.compra
        if not compra.cuotas.exclude(estado='PAGADA').exists():
            compra.estado = 'PAGADA'
            compra.saldo = 0
        else:
            compra.saldo = sum((c.saldo for c in compra.cuotas.all()), Decimal('0.00'))
        compra.save()

        messages.success(self.request, 'Pago registrado correctamente.')
        return redirect('creditos_compras:recibo_pago', pk=pago.pk)


class ReciboPagoCompraView(LoginRequiredMixin, DetailView):
    model = PagoCuotaCompra
    template_name = 'creditos_compras/recibo_pago.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pago = self.object
        context['cuota'] = pago.cuota
        context['compra'] = pago.cuota.compra
        return context


class ReciboMultiplePagosCompraView(LoginRequiredMixin, View):
    template_name = 'creditos_compras/recibo_multiple_pagos.html'

    def get(self, request, pk):
        compra = get_object_or_404(Purchase, pk=pk)
        ids = [i for i in request.GET.get('ids', '').split(',') if i]
        pagos = PagoCuotaCompra.objects.filter(
            pk__in=ids, cuota__compra=compra
        ).select_related('cuota').order_by('cuota__numero')

        if not pagos.exists():
            messages.error(request, 'No se encontraron pagos para mostrar.')
            return redirect('creditos_compras:cuota_list', pk=compra.pk)

        total = sum((p.valor for p in pagos), Decimal('0.00'))
        return render(request, self.template_name, {
            'compra': compra,
            'pagos': pagos,
            'total': total,
        })


class HistorialPagosCompraView(LoginRequiredMixin, ListView):
    model = PagoCuotaCompra
    template_name = 'creditos_compras/historial_pagos.html'
    context_object_name = 'pagos'

    def get_queryset(self):
        self.cuota = get_object_or_404(CuotaCompra, pk=self.kwargs['pk'])
        return PagoCuotaCompra.objects.filter(cuota=self.cuota).order_by('-fecha')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuota'] = self.cuota
        return ctx


class PagarMultipleCuotasCompraView(LoginRequiredMixin, View):
    template_name = 'creditos_compras/pagar_multiple_cuotas.html'

    def get(self, request, pk):
        return redirect('creditos_compras:cuota_list', pk=pk)

    def _get_cuotas_seleccionadas(self, request, compra):
        cuota_ids = request.POST.getlist('cuotas')
        return CuotaCompra.objects.filter(
            pk__in=cuota_ids, compra=compra, estado='PENDIENTE'
        ).order_by('numero')

    def post(self, request, pk):
        compra = get_object_or_404(Purchase, pk=pk)
        cuotas = self._get_cuotas_seleccionadas(request, compra)

        if not cuotas.exists():
            messages.error(request, 'Debe seleccionar al menos una cuota pendiente.')
            return redirect('creditos_compras:cuota_list', pk=compra.pk)

        total = sum((c.saldo for c in cuotas), Decimal('0.00'))

        if 'confirmar' not in request.POST:
            form = PagoMultipleCuotasCompraForm(initial={'fecha': date.today()})
            return render(request, self.template_name, {
                'compra': compra,
                'cuotas': cuotas,
                'total': total,
                'form': form,
            })

        form = PagoMultipleCuotasCompraForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'compra': compra,
                'cuotas': cuotas,
                'total': total,
                'form': form,
            })

        fecha = form.cleaned_data['fecha']
        observacion = form.cleaned_data['observacion']

        pagos_creados = []
        for cuota in cuotas:
            pago = PagoCuotaCompra.objects.create(
                cuota=cuota,
                fecha=fecha,
                valor=cuota.saldo,
                observacion=observacion,
            )
            pagos_creados.append(pago.pk)
            cuota.saldo = 0
            cuota.estado = 'PAGADA'
            cuota.save()

        if not compra.cuotas.exclude(estado='PAGADA').exists():
            compra.estado = 'PAGADA'
            compra.saldo = 0
        else:
            compra.saldo = sum((c.saldo for c in compra.cuotas.all()), Decimal('0.00'))
        compra.save()

        messages.success(request, f'{cuotas.count()} cuota(s) pagadas correctamente.')
        url = reverse('creditos_compras:recibo_multiple', kwargs={'pk': compra.pk})
        ids_str = ','.join(str(pago_pk) for pago_pk in pagos_creados)
        return redirect(f'{url}?ids={ids_str}')
