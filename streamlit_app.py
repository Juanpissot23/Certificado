import streamlit as st
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import io
import psycopg2
from datetime import datetime

# ========== CONFIGURA TU CONEXIÓN ==========
DB_PARAMS = {
    "database": st.secrets["database"],
    "user": st.secrets["user"],
    "password": st.secrets["password"],
    "host": st.secrets["host"],
    "port": st.secrets["port"]
}

# ========== FUNCIONES AUXILIARES ==========
def extraer_numero_categoria(categoria_str):
    try:
        return str(int(str(categoria_str).split('.')[0]))
    except:
        return '-'

def ajustar_texto(canvas, texto, x, y, ancho_max, fuente="Helvetica", tamaño_base=9, tamaño_min=6):
    tamaño = tamaño_base
    canvas.setFont(fuente, tamaño)
    while canvas.stringWidth(texto, fuente, tamaño) > ancho_max and tamaño > tamaño_min:
        tamaño -= 0.5
        canvas.setFont(fuente, tamaño)
    if canvas.stringWidth(texto, fuente, tamaño) > ancho_max:
        while canvas.stringWidth(texto + "...", fuente, tamaño) > ancho_max and len(texto) > 0:
            texto = texto[:-1]
        texto = texto + "..."
    canvas.drawString(x, y, texto)

def formatear_fecha(fecha):
    if fecha is None:
        return "-"
    if isinstance(fecha, (datetime, )):
        return fecha.strftime('%d/%m/%Y')
    try:
        return datetime.strptime(str(fecha)[:10], '%Y-%m-%d').strftime('%d/%m/%Y')
    except:
        return str(fecha)

def generar_pdf_certificado(num_manifiesto, plantilla_path):
    # Conecta a la base de datos
    try:
        conn = psycopg2.connect(**DB_PARAMS)
        cur = conn.cursor()
        query = """
        SELECT
            razon_social,
            nit,
            telefono,
            direccion,
            correo,
            num_manifiesto,
            num_certificado,
            fecha_recepcion,
            fecha_expedicion,
            categoria,
            subcategoria,
            elemento,
            cantidad,
            peso_neto
        FROM ingresos_insumos
        WHERE num_manifiesto = %s
        ORDER BY categoria, subcategoria, elemento
        """
        cur.execute(query, (num_manifiesto,))
        rows = cur.fetchall()
        if not rows:
            return None  # No hay datos para ese manifiesto

        # Datos generales (de la primera fila)
        razon_social, nit, telefono, direccion, correo, num_manifiesto, num_certificado, fecha_recoleccion, fecha_expedicion, *_ = rows[0]
        fecha_recoleccion_f = formatear_fecha(fecha_recoleccion)
        fecha_expedicion_f = formatear_fecha(fecha_expedicion)

        # Elementos y totales
        elementos = []
        total_cantidad = 0
        total_peso = 0
        for row in rows:
            categoria = extraer_numero_categoria(row[9])
            subcategoria = row[10]
            elemento = row[11]
            cantidad = row[12] if row[12] else 0
            peso_neto = row[13] if row[13] else 0
            elementos.append([categoria, subcategoria, elemento, cantidad, peso_neto])
            total_cantidad += cantidad
            total_peso += peso_neto

        # --- Crear PDF temporal con los datos ---
        packet = io.BytesIO()
        c = canvas.Canvas(packet, pagesize=A4)

        fuente = "Helvetica"

        # === DATOS DEL CERTIFICADO (posiciones calibradas) ===
        c.setFont(fuente, 9)
        c.drawString(115, 528, str(num_manifiesto))           # No. de manifiesto
        c.drawString(400, 528, str(num_certificado))          # No. de certificado

        c.setFont(fuente, 9)
        c.drawString(115, 612, str(razon_social))             # Razón social
        c.drawString(115, 598, str(nit))                      # NIT
        c.drawString(115, 584, str(telefono))                 # Teléfono
        c.drawString(115, 570, str(direccion))                # Dirección
        c.drawString(115, 556, str(correo))                   # E-mail
        c.drawString(115, 513, str(fecha_recoleccion_f))      # Fecha recolección
        c.drawString(500, 513, str(fecha_expedicion_f))       # Fecha de expedición

        # === TABLA DE ELEMENTOS ===
        y_start = 460
        row_height = 16
        for elem in elementos:
            c.setFont(fuente, 9)
        for elem in elementos:
            c.drawString(42, y_start, str(elem[0]))                         # Categoría (solo número)
            ajustar_texto(c, str(elem[1]), 71, y_start, 45)    # Subcategoría
            ajustar_texto(c, str(elem[2]), 115, y_start, 150)      # Elemento ajustado (ancho 150)
            c.setFont("Helvetica", 9)
            c.drawString(272, y_start, str(elem[3]))                        # Cantidad
            c.drawString(303, y_start, str(elem[4]))                        # Peso neto
            y_start -= row_height
            if y_start < 120:
                break

        # === TOTALES EN BLANCO ===
        c.setFont(fuente, 9)
        c.setFillColorRGB(1, 1, 1) # Blanco
        c.drawString(270, 77, str(total_cantidad))
        c.drawString(303, 77, str(total_peso))
        c.setFillColorRGB(0, 0, 0) # Retorna a negro

        c.save()
        packet.seek(0)
        overlay_pdf = PdfReader(packet)

        # --- Leer la plantilla PDF proporcionada ---
        template_pdf = PdfReader(open(plantilla_path, "rb"))
        output = PdfWriter()

        # --- Fusionar los datos sobre la plantilla (solo primera página) ---
        page = template_pdf.pages[0]
        page.merge_page(overlay_pdf.pages[0])
        output.add_page(page)

        # --- Guardar el PDF final en memoria ---
        output_bytes = io.BytesIO()
        output.write(output_bytes)
        output_bytes.seek(0)
        return output_bytes

    except Exception as e:
        st.error(f"Error al generar PDF: {e}")
        return None
    finally:
        try:
            cur.close()
            conn.close()
        except:
            pass

# ========== INTERFAZ STREAMLIT ==========

st.set_page_config(page_title="Certificado PDF por Manifiesto", page_icon="📄")
st.title("Descargar Certificado PDF por Manifiesto")

# Puedes dejar la plantilla PDF en el mismo directorio del script
TEMPLATE_PATH = "PDF-CERTIFICADOS-COMPLETO-test.pdf"

num_manifiesto = st.text_input("Ingrese el número de manifiesto:")

if st.button("Generar y descargar PDF"):
    if num_manifiesto:
        pdf_bytes = generar_pdf_certificado(num_manifiesto, TEMPLATE_PATH)
        if pdf_bytes:
            st.success("¡PDF generado exitosamente!")
            st.download_button(
                label="Descargar PDF Certificado",
                data=pdf_bytes,
                file_name=f"Certificado_Manifiesto_{num_manifiesto}.pdf",
                mime="application/pdf"
            )
        else:
            st.error("No se encontraron datos para ese manifiesto.")
    else:
        st.warning("Por favor, ingrese el número de manifiesto.")
