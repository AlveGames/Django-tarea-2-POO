import random
import string
import qrcode
import io
from datetime import datetime


def generar_numero_autorizacion():
    # 49 dígitos simulados
    fecha = datetime.now().strftime('%Y%m%d')
    resto = ''.join([str(random.randint(0, 9)) for _ in range(41)])
    return fecha + resto


def generar_qr(factura):
    datos = f"""TecnoStock
Factura: {factura.id:09d}
Cliente: {factura.customer}
Fecha: {factura.invoice_date.strftime('%d/%m/%Y')}
Total: ${factura.total}
Autorización: {factura.numero_autorizacion}"""

    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(datos)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return buffer.getvalue()


def generar_xml(factura):
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<factura version="1.0.0">
    <infoTributaria>
        <ambiente>1</ambiente>
        <tipoEmision>1</tipoEmision>
        <razonSocial>TecnoStock</razonSocial>
        <ruc>1234567890001</ruc>
        <claveAcceso>{factura.clave_acceso}</claveAcceso>
        <codDoc>01</codDoc>
        <estab>001</estab>
        <ptoEmi>001</ptoEmi>
        <secuencial>{factura.id:09d}</secuencial>
    </infoTributaria>
    <infoFactura>
        <fechaEmision>{factura.invoice_date.strftime('%d/%m/%Y')}</fechaEmision>
        <razonSocialComprador>{factura.customer}</razonSocialComprador>
        <identificacionComprador>{factura.customer.dni}</identificacionComprador>
        <totalSinImpuestos>{factura.subtotal}</totalSinImpuestos>
        <totalImpuesto>{factura.tax}</totalImpuesto>
        <importeTotal>{factura.total}</importeTotal>
    </infoFactura>
    <detalles>
        {''.join([f"""
        <detalle>
            <descripcion>{d.product.name}</descripcion>
            <cantidad>{d.quantity}</cantidad>
            <precioUnitario>{d.unit_price}</precioUnitario>
            <subtotal>{d.subtotal}</subtotal>
        </detalle>""" for d in factura.details.all()])}
    </detalles>
    <autorizacion>
        <numeroAutorizacion>{factura.numero_autorizacion}</numeroAutorizacion>
        <fechaAutorizacion>{datetime.now().strftime('%d/%m/%Y %H:%M:%S')}</fechaAutorizacion>
        <estado>AUTORIZADO</estado>
    </autorizacion>
</factura>"""
    return xml


def generar_factura_electronica(factura):
    """Simula la autorización del SRI: genera número de autorización y clave
    de acceso, y los persiste en la factura. Se llama una sola vez al crear
    la factura; generar_qr()/generar_xml() se pueden invocar luego cuantas
    veces haga falta (PDF, correo, descarga) porque son puros/sin estado."""
    factura.numero_autorizacion = generar_numero_autorizacion()
    factura.clave_acceso = generar_numero_autorizacion()
    factura.xml_generado = True
    factura.save(update_fields=['numero_autorizacion', 'clave_acceso', 'xml_generado'])
    return factura
