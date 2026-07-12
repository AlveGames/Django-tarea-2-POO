from django import template

register = template.Library()

@register.filter(name='has_group')
def has_group(user, group_name):
    """
    Uso en template:
        {% load security_tags %}
        {% if user|has_group:'Vendedor' %} ... {% endif %}
    """
    if not user.is_authenticated:
        return False
    if user.is_superuser:      # el superusuario ve todo
        return True
    return user.groups.filter(name=group_name).exists()


@register.filter(name='humanize_slug')
def humanize_slug(value):
    """Convierte 'brand_list' o 'brand-list' en 'Brand List' para usar como
    título de página de respaldo en el topbar cuando la vista no define uno."""
    if not value:
        return ''
    return value.replace('_', ' ').replace('-', ' ').title()