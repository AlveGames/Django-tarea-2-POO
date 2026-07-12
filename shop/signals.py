from django.contrib.auth.models import Group, User
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import PerfilCliente


@receiver(post_save, sender=User)
def crear_perfil(sender, instance, created, **kwargs):
    if created:
        PerfilCliente.objects.create(user=instance)


@receiver(post_save, sender=User)
def asignar_rol_cliente(sender, instance, created, **kwargs):
    """Todo usuario nuevo (no superusuario) arranca con el rol Cliente por
    defecto, sin importar desde dónde se creó (registro público, Django
    Admin, shell). Un administrador puede luego editarlo y asignarle otro rol."""
    if created and not instance.is_superuser:
        grupo_cliente, _ = Group.objects.get_or_create(name='Cliente')
        instance.groups.add(grupo_cliente)
