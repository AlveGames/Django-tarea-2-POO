from django.db import models
from shared.validators import validate_cedula_ec 

class Brand(models.Model):
    """Marcas de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Brand Name')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Brand'
        verbose_name_plural = 'Brands'
        ordering = ['name']
    def __str__(self): return self.name

class ProductGroup(models.Model):
    """Grupos/categorías de productos."""
    name = models.CharField(max_length=100, unique=True, verbose_name='Group Name')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product Group'
        verbose_name_plural = 'Product Groups'
        ordering = ['name']
    def __str__(self): return self.name

class Supplier(models.Model):
    """Proveedores. M2M con Product."""
    name = models.CharField(max_length=200, verbose_name='Company Name')
    contact_name = models.CharField(max_length=200, blank=True, null=True)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Supplier'
        verbose_name_plural = 'Suppliers'
        ordering = ['name']
    def __str__(self): return self.name

class Product(models.Model):
    """Productos. FK a Brand/Group, M2M a Supplier."""
    name = models.CharField(max_length=200, verbose_name='Product Name')
    description = models.TextField(blank=True, null=True)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name='products')
    group = models.ForeignKey(ProductGroup, on_delete=models.PROTECT, related_name='products')
    suppliers = models.ManyToManyField(Supplier, related_name='products', blank=True)
    image = models.ImageField(upload_to='products/', blank=True, null=True, verbose_name='Image')
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    stock = models.IntegerField(default=0)
    applies_iva = models.BooleanField(default=True, verbose_name='Aplica IVA')
    discount = models.DecimalField(max_digits=5, decimal_places=2, default=0, verbose_name='Descuento %')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        verbose_name = 'Product'
        verbose_name_plural = 'Products'
        ordering = ['name']
        permissions = [
            ('export_product', 'Can export product'),
            ('print_product', 'Can print product'),
        ]
    def __str__(self): return f'{self.name} ({self.brand.name})'
    @property
    def balance(self):
        """Valor total en inventario: precio unitario × stock."""
        return (self.unit_price * self.stock).quantize(self.unit_price)
    @property
    def final_price(self):
        """Precio de venta aplicando el descuento porcentual, si tiene."""
        if self.discount > 0:
            return (self.unit_price * (1 - self.discount / 100)).quantize(self.unit_price)
        return self.unit_price

class Customer(models.Model):
    """Clientes. OneToOne con CustomerProfile."""
    dni = models.CharField(max_length=13, unique=True, verbose_name='DNI/RUC', validators=[validate_cedula_ec])
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True, null=True)
    address = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    class Meta:
        ordering = ['last_name', 'first_name']
    def __str__(self): return f'{self.last_name}, {self.first_name}'
    @property
    def full_name(self): return f'{self.first_name} {self.last_name}'

class CustomerProfile(models.Model):
    """Perfil extendido. OneToOne con Customer."""
    TAXPAYER = [('final','Final Consumer'),('ruc','RUC'),('rise','RISE')]
    PAYMENT = [('cash','Cash'),('credit_15','15 days'),('credit_30','30 days'),('credit_60','60 days')]
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, related_name='profile')
    taxpayer_type = models.CharField(max_length=10, choices=TAXPAYER, default='final')
    payment_terms = models.CharField(max_length=15, choices=PAYMENT, default='cash')
    credit_limit = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    notes = models.TextField(blank=True, null=True)
    class Meta: verbose_name = 'Customer Profile'
    def __str__(self): return f'Profile: {self.customer}'

class Invoice(models.Model):
    """Cabecera de factura."""
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    invoice_date = models.DateTimeField(auto_now_add=True)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    subtotal_iva = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Subtotal gravado (IVA)')
    subtotal_0 = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='Subtotal tarifa 0%')
    iva_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name='IVA 15%')
    is_active = models.BooleanField(default=True)
    tipo_pago = models.CharField(
        max_length=10,
        choices=[("CONTADO", "CONTADO"), ("CREDITO", "CREDITO")],
        default="CONTADO"
    )
    saldo = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    estado = models.CharField(
        max_length=15,
        choices=[("PENDIENTE", "PENDIENTE"), ("PAGADA", "PAGADA")],
        default="PENDIENTE"
    )
    # Facturación electrónica simulada (estilo SRI Ecuador)
    numero_autorizacion = models.CharField(max_length=49, blank=True)
    clave_acceso = models.CharField(max_length=49, blank=True)
    xml_generado = models.BooleanField(default=False)
    class Meta:
        ordering = ['-invoice_date']
        permissions = [
            ('export_invoice', 'Can export invoice'),
            ('print_invoice', 'Can print invoice'),
        ]
    def __str__(self): return f'Invoice #{self.id} - {self.customer}'

class InvoiceDetail(models.Model):
    """Líneas de factura."""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='details')
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name='invoice_details')
    quantity = models.IntegerField(default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    applies_iva = models.BooleanField(default=True, verbose_name='Aplica IVA')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    def __str__(self): return f'{self.product.name} x {self.quantity}'
    def save(self, *args, **kwargs):
        self.subtotal = self.quantity * self.unit_price
        super().save(*args, **kwargs)
