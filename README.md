# 🖥️ TecnoStock — Sistema de Ventas y Facturación
de Eyser Rocha

Proyecto académico desarrollado en **Django 6** para la materia de Programación Orientada a Objetos (POO). Aplica los principios de POO (herencia, mixins, encapsulamiento) sobre un sistema real de gestión comercial.

---

## 📖 Descripción del proyecto

**TecnoStock** es un sistema web de ventas y facturación pensado para una tienda de tecnología. Permite administrar el catálogo de productos, los clientes, las compras a proveedores y la emisión de facturas, todo desde una interfaz web con autenticación de usuarios.

El proyecto está organizado en tres apps de Django:

- 🧾 **`billing`** — Núcleo del sistema: marcas, categorías, proveedores, productos, clientes y facturación (Invoice / InvoiceDetail). Incluye exportación de reportes a PDF/Excel y manejo de imágenes de productos.
- 📦 **`purchasing`** — Gestión de compras a proveedores (Purchase / PurchaseDetail). Cada compra registrada incrementa automáticamente el stock de los productos.
- 🧰 **`shared`** — Código reutilizable entre apps: mixins (`StaffRequiredMixin`, `ExportMixin`), decoradores (`audit_action` para auditoría de acciones) y validadores personalizados (por ejemplo, validación de cédula/RUC ecuatoriano).

### Funcionalidades principales
- 🔐 Autenticación y registro de usuarios (login, signup, permisos de staff).
- 🛒 CRUD completo de marcas, categorías, proveedores, productos y clientes.
- 🖼️ Carga de imágenes de producto.
- 🧮 Facturación con formularios dinámicos (formsets): agregar/eliminar productos por fila, autocompletado de precio y cálculo de subtotales en tiempo real con JavaScript.
- 📊 Filtros y paginación en los listados.
- 📄 Exportación de reportes a **PDF** (ReportLab) y **Excel** (OpenPyXL).
- 📈 Control de stock automático al facturar (resta) y al comprar a proveedores (suma).

### 🔗 Relación entre `billing` y `purchasing`

La app `purchasing` **no duplica** los modelos de proveedores ni productos: los importa directamente desde `billing`.

```python
from billing.models import Supplier, Product
```

Esto significa que:
- Los **proveedores** (`Supplier`) son los mismos que se usan en ventas.
- Los **productos** (`Product`) son los mismos que se venden a los clientes.
- Un solo lugar centraliza proveedores y productos, evitando datos duplicados.
- Al registrar una **compra**, el stock del producto **sube** automáticamente.
- Al registrar una **venta** (factura), el stock del producto **baja** automáticamente.

**Flujo típico de una compra:**
1. Se selecciona el proveedor al que se le compra.
2. Se ingresa el número de documento (factura del proveedor).
3. Se agregan los productos comprados con cantidad y costo unitario.
4. El sistema calcula subtotal, IVA (15%) y total automáticamente.
5. El stock de cada producto se actualiza sumando la cantidad comprada.

---

## 🛠️ Tecnologías usadas

| Tecnología | Uso en el proyecto |
|---|---|
| 🐍 **Python** | Lenguaje base del proyecto. |
| 🎯 **Django 6** | Framework web principal (modelos, vistas, formularios, ORM, admin). |
| 🗄️ **SQLite** | Base de datos relacional por defecto, usada en desarrollo (`db.sqlite3`). |
| 🎨 **Bootstrap 5** | Estilos y componentes de interfaz (cargado vía CDN en `base.html`). |
| 🖼️ **Pillow** | Procesamiento de imágenes, requerido por los `ImageField` (imagen de productos). |
| 📄 **ReportLab** | Generación de reportes en formato PDF. |
| 📊 **OpenPyXL** | Generación de reportes en formato Excel (`.xlsx`). |

---

## 🗂️ Modelos del sistema

### App `billing`

| Modelo | Descripción | Relaciones |
|---|---|---|
| **Brand** | Marca comercial de un producto (ej. Samsung, HP). | 1 marca → N productos. |
| **ProductGroup** | Categoría o grupo de productos (ej. Laptops, Salud). | 1 categoría → N productos. |
| **Supplier** | Proveedor que abastece productos. | M2M con `Product`; 1 proveedor → N compras. |
| **Product** | Producto del catálogo (precio, stock, imagen, etc.). | FK a `Brand` y `ProductGroup`; M2M a `Supplier`. |
| **Customer** | Cliente que realiza compras (con validación de cédula/RUC). | 1 cliente → N facturas; O2O con `CustomerProfile`. |
| **CustomerProfile** | Datos adicionales del cliente (tipo de contribuyente, forma de pago, límite de crédito). | O2O con `Customer`. |
| **Invoice** | Cabecera de una factura (subtotal, impuesto, total). | FK a `Customer`; 1 factura → N `InvoiceDetail`. |
| **InvoiceDetail** | Línea de detalle de una factura (producto, cantidad, precio). | FK a `Invoice` y a `Product`. |

### App `purchasing`

| Modelo | Descripción | Relaciones |
|---|---|---|
| **Purchase** | Cabecera de una compra a un proveedor. | FK a `Supplier` (de `billing`); 1 compra → N `PurchaseDetail`. |
| **PurchaseDetail** | Línea de detalle de una compra (producto, cantidad, costo). | FK a `Purchase` y a `Product` (de `billing`). |

> 💡 Tanto `InvoiceDetail` como `PurchaseDetail` calculan automáticamente su `subtotal` (`cantidad × precio`) al guardarse, y las vistas actualizan el `subtotal`, `tax` y `total` de la cabecera correspondiente.

---

## 🚀 Comandos para crear un proyecto Django desde 0

Pasos completos para levantar un proyecto Django como este, desde cero:

```bash
# 1. Crear la carpeta del proyecto y entrar en ella
mkdir mi_proyecto && cd mi_proyecto

# 2. Crear un entorno virtual
python -m venv venv

# 3. Activar el entorno virtual
# En Windows (PowerShell):
venv\Scripts\Activate
# En Windows (cmd):
venv\Scripts\activate.bat
# En Linux / Mac:
source venv/bin/activate

# 4. Instalar Django (y otras dependencias que se vayan a usar)
pip install django pillow reportlab openpyxl ipython django-extensions

# 5. Crear el proyecto Django (el "." lo crea en la carpeta actual)
django-admin startproject config .

# 6. Crear una app dentro del proyecto
python manage.py startapp billing

# 7. Registrar la app en INSTALLED_APPS (config/settings.py)
#    INSTALLED_APPS = [..., 'billing']

# 8. Crear los modelos en billing/models.py

# 9. Generar las migraciones a partir de los modelos
python manage.py makemigrations

# 10. Aplicar las migraciones a la base de datos
python manage.py migrate

# 11. Crear un superusuario para acceder al panel de administración
python manage.py createsuperuser

# 12. Levantar el servidor de desarrollo
python manage.py runserver
```

Con esto el proyecto queda disponible en `http://127.0.0.1:8000/` y el panel de administración en `http://127.0.0.1:8000/admin/`.

---

## 🔄 Comandos ORM más usados (CRUD)

tambien se puede usar `python manage.py shell_plus --print-sql` si se tiene django extensions
Ejemplos usando el modelo `Product` desde `python manage.py shell`:


### 🟢 Create (crear)
```python
from billing.models import Product, Brand, ProductGroup

brand = Brand.objects.get(name="Samsung")
group = ProductGroup.objects.get(name="Laptops")

# Crear y guardar en un solo paso
Product.objects.create(
    name="Laptop Galaxy Book",
    brand=brand,
    group=group,
    unit_price=899.99,
    stock=10,
)

# Crear con save() explícito
product = Product(name="Mouse inalámbrico", brand=brand, group=group, unit_price=15.50, stock=50)
product.save()
```

### 🔵 Read (leer)
```python
Product.objects.all()                          # Todos los productos
Product.objects.get(pk=1)                       # Un solo registro (por PK)
Product.objects.filter(stock__lte=5)            # Productos con poco stock
Product.objects.filter(brand__name="Samsung")   # Filtro por relación FK
Product.objects.exclude(is_active=False)        # Excluir inactivos
Product.objects.order_by('-unit_price')         # Ordenar (descendente)
Product.objects.first()                         # Primer resultado
Product.objects.count()                         # Cantidad de registros
```

### 🟡 Update (actualizar)
```python
# Actualizar una instancia puntual
product = Product.objects.get(pk=1)
product.stock -= 3
product.save()

# Actualizar en masa (sin traer los objetos a Python)
Product.objects.filter(brand=brand).update(is_active=True)
```

### 🔴 Delete (eliminar)
```python
# Eliminar una instancia puntual
product = Product.objects.get(pk=1)
product.delete()

# Eliminar en masa según un filtro
Product.objects.filter(stock=0, is_active=False).delete()
```

---

## 🧩 Tipos de campos Django

| Campo | ¿Para qué sirve? | Ejemplo en el proyecto |
|---|---|---|
| **CharField** | Texto corto de longitud limitada (`max_length` obligatorio). Se usa para nombres, títulos, códigos. | `name = models.CharField(max_length=200)` en `Product`. |
| **TextField** | Texto largo sin límite fijo de longitud. Ideal para descripciones o notas. | `description = models.TextField(blank=True, null=True)` en `Product`. |
| **DecimalField** | Números decimales exactos (sin errores de redondeo), ideales para dinero. Requiere `max_digits` y `decimal_places`. | `unit_price = models.DecimalField(max_digits=12, decimal_places=2)` en `Product`. |
| **IntegerField** | Números enteros positivos o negativos. | `stock = models.IntegerField(default=0)` en `Product`. |
| **BooleanField** | Valor verdadero/falso (`True`/`False`). Útil para banderas de estado. | `is_active = models.BooleanField(default=True)` en varios modelos. |
| **EmailField** | Como `CharField`, pero valida que el texto tenga formato de correo electrónico. | `email = models.EmailField(blank=True, null=True)` en `Customer`. |
| **ForeignKey** | Relación **muchos a uno**: liga un registro con otro modelo (clave foránea). | `brand = models.ForeignKey(Brand, on_delete=models.PROTECT)` en `Product`. |

---

## ▶️ Cómo correr este proyecto

```bash
# 1. Clonar el repositorio
git clone https://github.com/AlveGames/Django-tarea-2-POO.git
cd Django-tarea-2-POO

# 2. Crear y activar un entorno virtual
python -m venv venv
venv\Scripts\Activate.ps1      # Windows (PowerShell)
# source venv/bin/activate     # Linux / Mac

# 3. Instalar las dependencias del proyecto
pip install -r requirements.txt

# 4. Aplicar las migraciones a la base de datos
python manage.py migrate

# 5. (Opcional) Crear un superusuario para el panel de administración
python manage.py createsuperuser

# 6. Levantar el servidor de desarrollo
python manage.py runserver
```

Luego abre el navegador en 👉 `http://127.0.0.1:8000/`

> ⚠️ El sistema requiere iniciar sesión para acceder a la mayoría de las vistas. Usa el superusuario creado en el paso 5, o regístrate desde la opción **Sign Up**.

---

### 🧭 Apps del proyecto (resumen rápido)

| App | Función |
|---|---|
| `billing` | Ventas, facturación, clientes, productos, proveedores |
| `purchasing` | Compras a proveedores, reabastecimiento de inventario |
| `shared` | Mixins, decoradores y validadores reutilizables |
