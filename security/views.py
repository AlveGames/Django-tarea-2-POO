from django.shortcuts import render

# Create your views here.
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User, Group, Permission
from django.contrib.auth.views import LoginView, LogoutView
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse_lazy
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from shared.mixins import GroupRequiredMixin
from .forms import UserRegisterForm, UserUpdateForm, GroupForm, PermissionForm

# === MATRIZ DE PERMISOS POR MÓDULO (pantalla visual de roles) ===
MODULOS = {
    'Gestión': {
        'Marcas': ['view_brand', 'add_brand', 'change_brand', 'delete_brand'],
        'Grupos': ['view_productgroup', 'add_productgroup', 'change_productgroup', 'delete_productgroup'],
        'Proveedores': ['view_supplier', 'add_supplier', 'change_supplier', 'delete_supplier'],
        'Productos': ['view_product', 'add_product', 'change_product', 'delete_product'],
    },
    'Ventas': {
        'Clientes': ['view_customer', 'add_customer', 'change_customer', 'delete_customer'],
        'Facturas': ['view_invoice', 'add_invoice', 'change_invoice', 'delete_invoice'],
        'Créditos Ventas': ['view_cuotaventa', 'add_cuotaventa', 'change_cuotaventa', 'delete_cuotaventa'],
    },
    'Compras': {
        'Compras': ['view_purchase', 'add_purchase', 'change_purchase', 'delete_purchase'],
        'Créditos Compras': ['view_cuotacompra', 'add_cuotacompra', 'change_cuotacompra', 'delete_cuotacompra'],
    },
    'Seguridad': {
        'Usuarios': ['view_user', 'add_user', 'change_user', 'delete_user'],
        'Roles': ['view_group', 'add_group', 'change_group', 'delete_group'],
    },
}

# Acciones mostradas en la grilla de cada módulo: las 4 acciones reales
# de Django (view/add/change/delete). No hay permisos de exportar/imprimir.
ACCIONES = [
    ('view', 'Ver'),
    ('add', 'Crear'),
    ('change', 'Editar'),
    ('delete', 'Eliminar'),
]


def build_permissions_matrix(group=None):
    """Arma la matriz de módulos/submódulos con los Permission reales de Django
    y marca cuáles están activos para el rol dado (ninguno si es creación).

    También devuelve los ids de permisos que el rol ya tenía pero que no
    forman parte de la matriz visual, para preservarlos como inputs ocultos
    y que guardar el formulario no se los quite silenciosamente.
    """
    all_codenames = {
        codename
        for submodulos in MODULOS.values()
        for codenames in submodulos.values()
        for codename in codenames
    }
    perms_by_codename = {
        p.codename: p for p in Permission.objects.filter(codename__in=all_codenames)
    }

    active_ids = set(group.permissions.values_list('id', flat=True)) if group else set()

    modulos_ctx = []
    for modulo_name, submodulos in MODULOS.items():
        submodulos_ctx = []
        for submodulo_name, codenames in submodulos.items():
            acciones_ctx = []
            active_count = 0
            total_count = 0
            for prefix, label in ACCIONES:
                codename = next((c for c in codenames if c.startswith(prefix + '_')), None)
                perm = perms_by_codename.get(codename) if codename else None
                checked = bool(perm and perm.id in active_ids)
                if perm:
                    total_count += 1
                if checked:
                    active_count += 1
                acciones_ctx.append({
                    'label': label,
                    'permission': perm,
                    'checked': checked,
                })
            submodulos_ctx.append({
                'name': submodulo_name,
                'acciones': acciones_ctx,
                'active_count': active_count,
                'total_count': total_count,
            })
        modulos_ctx.append({'name': modulo_name, 'submodulos': submodulos_ctx})

    covered_ids = {p.id for p in perms_by_codename.values()}
    extra_ids = active_ids - covered_ids

    return modulos_ctx, extra_ids


# === MIXIN BASE: SOLO ADMINISTRADOR ===
class AdminOnlyMixin(LoginRequiredMixin, GroupRequiredMixin):
    """Combina login + rol Administrador (el superusuario siempre pasa)."""
    group_required = ['Administrador']
    group_redirect_url = '/'

# === AUTENTICACIÓN (CBV) ===
class RegisterView(CreateView):
    """Registro público. El rol se asigna después por un Administrador."""
    form_class = UserRegisterForm
    template_name = 'security/register.html'
    success_url = reverse_lazy('billing:home')

    def form_valid(self, form):
        response = super().form_valid(form)
        login(self.request, self.object)   # inicia sesión automáticamente

        grupo_cliente, _ = Group.objects.get_or_create(name='Cliente')
        self.object.groups.add(grupo_cliente)

        html_message = render_to_string('emails/bienvenida.html', {'username': self.object.username})
        send_mail(
            subject='Bienvenido a TecnoStock',
            message=f'Bienvenido a TecnoStock, {self.object.username}.',
            from_email=None,
            recipient_list=[self.object.email],
            html_message=html_message,
            fail_silently=True,
        )
        return response

class SecurityLoginView(LoginView):
    """Login con CBV. Reutiliza el template de la PARTE 9."""
    template_name = 'registration/login.html'

    def get_success_url(self):
        # Todos los usuarios caen siempre al catálogo tras iniciar sesión,
        # evitando que un login quede mostrando datos de una sesión previa
        # (ej. dashboard). El acceso al Panel de Gestión sigue disponible
        # desde el botón correspondiente en la navbar del shop.
        return reverse_lazy('shop:catalog')

class SecurityLogoutView(LogoutView):
    """Logout con CBV. Redirige según LOGOUT_REDIRECT_URL."""
    pass

# === USUARIOS (solo Administrador) ===
class UserListView(AdminOnlyMixin, ListView):
    model = User
    template_name = 'security/user_list.html'
    context_object_name = 'items'

class UserUpdateView(AdminOnlyMixin, UpdateView):
    model = User
    form_class = UserUpdateForm
    template_name = 'security/user_form.html'
    success_url = reverse_lazy('security:user_list')

    def form_valid(self, form):
        response = super().form_valid(form)
        # Si el usuario se queda sin ningún rol, asignar Cliente
        if not self.object.groups.exists():
            grupo_cliente, _ = Group.objects.get_or_create(name='Cliente')
            self.object.groups.add(grupo_cliente)
        return response

class UserDeleteView(AdminOnlyMixin, DeleteView):
    model = User
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:user_list')

# === ROLES / GROUP (solo Administrador) ===
class GroupListView(AdminOnlyMixin, ListView):
    model = Group
    template_name = 'security/group_list.html'
    context_object_name = 'items'

class GroupCreateView(AdminOnlyMixin, CreateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['all_groups'] = Group.objects.order_by('name')
        ctx['modulos'], ctx['extra_permission_ids'] = build_permissions_matrix(None)
        return ctx

class GroupUpdateView(AdminOnlyMixin, UpdateView):
    model = Group
    form_class = GroupForm
    template_name = 'security/group_form.html'
    success_url = reverse_lazy('security:group_list')

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx['all_groups'] = Group.objects.order_by('name')
        ctx['modulos'], ctx['extra_permission_ids'] = build_permissions_matrix(self.object)
        return ctx

class GroupDeleteView(AdminOnlyMixin, DeleteView):
    model = Group
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:group_list')

# === PERMISOS / PERMISSION (solo Administrador) ===
class PermissionListView(AdminOnlyMixin, ListView):
    model = Permission
    template_name = 'security/permission_list.html'
    context_object_name = 'items'
    queryset = Permission.objects.select_related('content_type')

class PermissionCreateView(AdminOnlyMixin, CreateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')

class PermissionUpdateView(AdminOnlyMixin, UpdateView):
    model = Permission
    form_class = PermissionForm
    template_name = 'security/permission_form.html'
    success_url = reverse_lazy('security:permission_list')

class PermissionDeleteView(AdminOnlyMixin, DeleteView):
    model = Permission
    template_name = 'security/confirm_delete.html'
    success_url = reverse_lazy('security:permission_list')