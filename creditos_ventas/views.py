import calendar
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from billing.models import Invoice
from shared.mixins import ExportMixin
from .forms import FacturaVentaForm, GenerarCuotasForm, PagoCuotaForm, PagoMultipleCuotasForm
from .models import CuotaVenta, PagoCuotaVenta


def add_months(source_date, months):
    """Suma `months` meses a `source_date`, ajustando el día si el mes destino es más corto."""
    month = source_date.month - 1 + months
    year = source_date.year + month // 12
    month = month % 12 + 1
    day = min(source_date.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


# === FACTURA (CBV) ===

class FacturaVentaListView(LoginRequiredMixin, ExportMixin, ListView):
    model = Invoice
    template_name = 'creditos_ventas/factura_list.html'
    context_object_name = 'facturas'
    export_title = 'Facturas'
    paginate_by = 10

    def get_export_fields(self):
        return [
            ('Número', lambda obj: f'#{obj.pk}'),
            ('Fecha', lambda obj: obj.invoice_date.strftime('%d/%m/%Y')),
            ('Cliente', 'customer__full_name'),
            ('Total', 'total'),
            ('Tipo Pago', 'tipo_pago'),
            ('Saldo', 'saldo'),
            ('Estado', 'estado'),
        ]

    def get_queryset(self):
        qs = Invoice.objects.select_related('customer').order_by('-invoice_date')
        p = self.request.GET

        cliente = p.get('cliente', '').strip()
        tipo_pago = p.get('tipo_pago', '')
        estado = p.get('estado', '')
        fecha_desde = p.get('fecha_desde', '')
        fecha_hasta = p.get('fecha_hasta', '')

        if cliente:
            qs = qs.filter(
                Q(customer__first_name__icontains=cliente) |
                Q(customer__last_name__icontains=cliente)
            )
        if tipo_pago:
            qs = qs.filter(tipo_pago=tipo_pago)
        if estado:
            qs = qs.filter(estado=estado)
        if fecha_desde:
            qs = qs.filter(invoice_date__date__gte=fecha_desde)
        if fecha_hasta:
            qs = qs.filter(invoice_date__date__lte=fecha_hasta)

        return qs.distinct()

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['filters'] = self.request.GET
        return ctx


class FacturaVentaDetailView(LoginRequiredMixin, DetailView):
    model = Invoice
    template_name = 'creditos_ventas/factura_detail.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cuotas'] = self.object.cuotas.all().order_by('numero')
        context['total_pagado'] = self.object.total - self.object.saldo
        return context


class FacturaVentaCreateView(LoginRequiredMixin, CreateView):
    model = Invoice
    form_class = FacturaVentaForm
    template_name = 'creditos_ventas/factura_form.html'

    def form_valid(self, form):
        invoice = form.save(commit=False)
        if invoice.tipo_pago == 'CONTADO':
            invoice.estado = 'PAGADA'
            invoice.saldo = 0
        else:
            invoice.estado = 'PENDIENTE'
            invoice.saldo = invoice.total
        invoice.save()
        self.object = invoice

        messages.success(self.request, f'Factura #{invoice.pk} creada correctamente.')
        if invoice.tipo_pago == 'CREDITO':
            numero_cuotas = form.cleaned_data.get('numero_cuotas') or ''
            url = reverse('creditos_ventas:generar_cuotas', kwargs={'pk': invoice.pk})
            return redirect(f'{url}?numero_cuotas={numero_cuotas}')
        return redirect('creditos_ventas:factura_list')


class FacturaVentaUpdateView(LoginRequiredMixin, UpdateView):
    model = Invoice
    form_class = FacturaVentaForm
    template_name = 'creditos_ventas/factura_form.html'
    success_url = reverse_lazy('creditos_ventas:factura_list')

    def dispatch(self, request, *args, **kwargs):
        self.object = self.get_object()
        if self.object.estado == 'PAGADA':
            messages.error(request, 'No se puede modificar una factura pagada.')
            return redirect('creditos_ventas:factura_list')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        initial['numero_cuotas'] = self.object.cuotas.count()
        return initial

    def _regenerar_cuotas(self, invoice, numero_cuotas_nuevo):
        """Ajusta las cuotas de `invoice` al nuevo número solicitado.

        Solo se eliminan/regeneran las cuotas PENDIENTES sin pagos. Las que ya
        tienen pagos registrados se conservan tal cual y se avisa al usuario.
        """
        numero_cuotas_actual = invoice.cuotas.count()
        if not numero_cuotas_nuevo or numero_cuotas_nuevo == numero_cuotas_actual:
            return

        cuotas_con_pagos = invoice.cuotas.filter(pagocuotaventa__isnull=False).distinct()
        cuotas_sin_pagos = invoice.cuotas.filter(pagocuotaventa__isnull=True)
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

        monto_restante = invoice.total - kept_valor_total
        valor_base = (monto_restante / nuevas_a_crear).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        fecha_base = invoice.invoice_date.date()

        acumulado = Decimal('0.00')
        for i in range(1, nuevas_a_crear + 1):
            numero = max_numero_kept + i
            if i == nuevas_a_crear:
                valor = monto_restante - acumulado
            else:
                valor = valor_base
                acumulado += valor
            CuotaVenta.objects.create(
                factura=invoice,
                numero=numero,
                fecha_vencimiento=add_months(fecha_base, numero),
                valor=valor,
                saldo=valor,
            )

        messages.success(self.request, 'Las cuotas se regeneraron con el nuevo número.')

    def form_valid(self, form):
        invoice = form.save(commit=False)

        if invoice.tipo_pago == 'CONTADO':
            invoice.estado = 'PAGADA'
            invoice.saldo = 0
            invoice.save()
        else:
            invoice.save()
            numero_cuotas_nuevo = form.cleaned_data.get('numero_cuotas')
            self._regenerar_cuotas(invoice, numero_cuotas_nuevo)

            if invoice.cuotas.exists():
                invoice.estado = 'PENDIENTE' if invoice.cuotas.exclude(estado='PAGADA').exists() else 'PAGADA'
                invoice.saldo = sum((c.saldo for c in invoice.cuotas.all()), Decimal('0.00'))
            else:
                invoice.estado = 'PENDIENTE'
                invoice.saldo = invoice.total
            invoice.save()

        self.object = invoice
        messages.success(self.request, f'Factura #{invoice.pk} actualizada correctamente.')
        return redirect(self.success_url)


class FacturaVentaDeleteView(LoginRequiredMixin, DeleteView):
    model = Invoice
    template_name = 'creditos_ventas/factura_confirm_delete.html'
    success_url = reverse_lazy('creditos_ventas:factura_list')

    def post(self, request, *args, **kwargs):
        # Django 6's BaseDeleteView.post() llama a form_valid() -> object.delete()
        # directamente, sin pasar por delete(). Lo redirigimos para que nuestra
        # lógica de borrado en cascada sí se ejecute.
        invoice = self.get_object()

        if invoice.estado == 'PAGADA':
            PagoCuotaVenta.objects.filter(cuota__factura=invoice).delete()
            invoice.cuotas.all().delete()
            self.object = invoice
            return super().post(request, *args, **kwargs)

        tiene_pagos = PagoCuotaVenta.objects.filter(
            cuota__factura=invoice
        ).exists()

        if tiene_pagos:
            messages.error(request, 'No se puede eliminar una factura con pagos parciales registrados.')
            return redirect('creditos_ventas:factura_list')

        invoice.cuotas.all().delete()

        self.object = invoice
        return super().post(request, *args, **kwargs)


# === CUOTAS (CBV) ===

class GenerarCuotasView(LoginRequiredMixin, View):

    def get_initial(self):
        initial = {}
        numero_cuotas = self.request.GET.get('numero_cuotas', '')
        if numero_cuotas:
            initial['numero_cuotas'] = numero_cuotas
        return initial

    def get(self, request, pk):
        factura = get_object_or_404(Invoice, pk=pk)
        if factura.cuotas.exists():
            messages.warning(request, 'Esta factura ya tiene cuotas generadas.')
            return redirect('creditos_ventas:cuota_list', pk=factura.pk)
        form = GenerarCuotasForm(initial=self.get_initial())
        return render(request, 'creditos_ventas/generar_cuotas.html', {'form': form, 'factura': factura})

    def post(self, request, pk):
        factura = get_object_or_404(Invoice, pk=pk)
        if factura.cuotas.exists():
            messages.warning(request, 'Esta factura ya tiene cuotas generadas.')
            return redirect('creditos_ventas:cuota_list', pk=factura.pk)

        form = GenerarCuotasForm(request.POST)
        if not form.is_valid():
            return render(request, 'creditos_ventas/generar_cuotas.html', {'form': form, 'factura': factura})

        numero_cuotas = form.cleaned_data['numero_cuotas']
        total = factura.total
        valor_base = (total / numero_cuotas).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        fecha_base = factura.invoice_date.date()

        acumulado = Decimal('0.00')
        for i in range(1, numero_cuotas + 1):
            if i == numero_cuotas:
                valor = total - acumulado
            else:
                valor = valor_base
                acumulado += valor
            CuotaVenta.objects.create(
                factura=factura,
                numero=i,
                fecha_vencimiento=add_months(fecha_base, i),
                valor=valor,
                saldo=valor,
            )

        messages.success(request, f'{numero_cuotas} cuotas generadas correctamente.')
        return redirect('creditos_ventas:cuota_list', pk=factura.pk)


class CuotaVentaListView(LoginRequiredMixin, ExportMixin, ListView):
    model = CuotaVenta
    template_name = 'creditos_ventas/cuota_list.html'
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
        self.factura = get_object_or_404(Invoice, pk=self.kwargs['pk'])
        self.export_title = f'Cuotas - Factura #{self.factura.pk}'
        return CuotaVenta.objects.filter(factura=self.factura).order_by('numero')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['factura'] = self.factura
        total = self.factura.cuotas.count()
        pagadas = self.factura.cuotas.filter(estado='PAGADA').count()
        ctx['total_cuotas'] = total
        ctx['cuotas_pagadas'] = pagadas
        ctx['progreso_pct'] = int((pagadas / total) * 100) if total else 0
        return ctx


class CuotasPendientesView(LoginRequiredMixin, ListView):
    model = CuotaVenta
    template_name = 'creditos_ventas/cuotas_pendientes.html'
    context_object_name = 'cuotas'
    paginate_by = 10

    def get_queryset(self):
        return (
            CuotaVenta.objects
            .filter(estado='PENDIENTE')
            .select_related('factura', 'factura__customer')
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

class RegistrarPagoView(LoginRequiredMixin, CreateView):
    model = PagoCuotaVenta
    form_class = PagoCuotaForm
    template_name = 'creditos_ventas/registrar_pago.html'

    def dispatch(self, request, *args, **kwargs):
        self.cuota = get_object_or_404(CuotaVenta, pk=self.kwargs['pk'])
        if self.cuota.estado == 'PAGADA':
            messages.error(request, 'Esta cuota ya está completamente pagada.')
            return redirect('creditos_ventas:cuota_list', pk=self.cuota.factura.pk)
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

        factura = self.cuota.factura
        if not factura.cuotas.exclude(estado='PAGADA').exists():
            factura.estado = 'PAGADA'
            factura.saldo = 0
        else:
            factura.saldo = sum((c.saldo for c in factura.cuotas.all()), Decimal('0.00'))
        factura.save()

        messages.success(self.request, 'Pago registrado correctamente.')
        return redirect('creditos_ventas:recibo_pago', pk=pago.pk)


class ReciboPagoView(LoginRequiredMixin, DetailView):
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/recibo_pago.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pago = self.object
        context['cuota'] = pago.cuota
        context['factura'] = pago.cuota.factura
        return context


class ReciboMultiplePagosView(LoginRequiredMixin, View):
    template_name = 'creditos_ventas/recibo_multiple_pagos.html'

    def get(self, request, pk):
        factura = get_object_or_404(Invoice, pk=pk)
        ids = [i for i in request.GET.get('ids', '').split(',') if i]
        pagos = PagoCuotaVenta.objects.filter(
            pk__in=ids, cuota__factura=factura
        ).select_related('cuota').order_by('cuota__numero')

        if not pagos.exists():
            messages.error(request, 'No se encontraron pagos para mostrar.')
            return redirect('creditos_ventas:cuota_list', pk=factura.pk)

        total = sum((p.valor for p in pagos), Decimal('0.00'))
        return render(request, self.template_name, {
            'factura': factura,
            'pagos': pagos,
            'total': total,
        })


class HistorialPagosView(LoginRequiredMixin, ListView):
    model = PagoCuotaVenta
    template_name = 'creditos_ventas/historial_pagos.html'
    context_object_name = 'pagos'

    def get_queryset(self):
        self.cuota = get_object_or_404(CuotaVenta, pk=self.kwargs['pk'])
        return PagoCuotaVenta.objects.filter(cuota=self.cuota).order_by('-fecha')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['cuota'] = self.cuota
        return ctx


class PagarMultipleCuotasView(LoginRequiredMixin, View):
    template_name = 'creditos_ventas/pagar_multiple_cuotas.html'

    def get(self, request, pk):
        return redirect('creditos_ventas:cuota_list', pk=pk)

    def _get_cuotas_seleccionadas(self, request, factura):
        cuota_ids = request.POST.getlist('cuotas')
        return CuotaVenta.objects.filter(
            pk__in=cuota_ids, factura=factura, estado='PENDIENTE'
        ).order_by('numero')

    def post(self, request, pk):
        factura = get_object_or_404(Invoice, pk=pk)
        cuotas = self._get_cuotas_seleccionadas(request, factura)

        if not cuotas.exists():
            messages.error(request, 'Debe seleccionar al menos una cuota pendiente.')
            return redirect('creditos_ventas:cuota_list', pk=factura.pk)

        total = sum((c.saldo for c in cuotas), Decimal('0.00'))

        if 'confirmar' not in request.POST:
            form = PagoMultipleCuotasForm(initial={'fecha': date.today()})
            return render(request, self.template_name, {
                'factura': factura,
                'cuotas': cuotas,
                'total': total,
                'form': form,
            })

        form = PagoMultipleCuotasForm(request.POST)
        if not form.is_valid():
            return render(request, self.template_name, {
                'factura': factura,
                'cuotas': cuotas,
                'total': total,
                'form': form,
            })

        fecha = form.cleaned_data['fecha']
        observacion = form.cleaned_data['observacion']

        pagos_creados = []
        for cuota in cuotas:
            pago = PagoCuotaVenta.objects.create(
                cuota=cuota,
                fecha=fecha,
                valor=cuota.saldo,
                observacion=observacion,
            )
            pagos_creados.append(pago.pk)
            cuota.saldo = 0
            cuota.estado = 'PAGADA'
            cuota.save()

        if not factura.cuotas.exclude(estado='PAGADA').exists():
            factura.estado = 'PAGADA'
            factura.saldo = 0
        else:
            factura.saldo = sum((c.saldo for c in factura.cuotas.all()), Decimal('0.00'))
        factura.save()

        messages.success(request, f'{cuotas.count()} cuota(s) pagadas correctamente.')
        url = reverse('creditos_ventas:recibo_multiple', kwargs={'pk': factura.pk})
        ids_str = ','.join(str(pago_pk) for pago_pk in pagos_creados)
        return redirect(f'{url}?ids={ids_str}')
