import json
import os
from google import genai
from google.genai import types
from pypdf import PdfReader
from supabase import Client, create_client

# 1. Credenciales de Supabase
SUPABASE_URL = "https://zezkvwiuhyojyaflvksc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inplemt2d2l1aHlvanlhZmx2a3NjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY1MDAyOTEsImV4cCI6MjEwMjA3NjI5MX0.32qTftolofuty8CnzllX8BMwObdmwIpXebEPEdfD-nw"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# 2. Configurar cliente de Gemini AI
GEMINI_API_KEY = "AQ.Ab8RN6JjPCgRre0p0lYK8BtiKd7fSFPBjc_OjWaWkgHvdkV-pg"
client_ai = genai.Client(api_key=GEMINI_API_KEY)

# Alias de modelo recomendado para estabilidad futura
MODEL_NAME = "gemini-flash-latest"


def extraer_texto_pdf(ruta_pdf):
  reader = PdfReader(ruta_pdf)
  texto = ""
  for page in reader.pages:
    texto += page.extract_text() or ""
  return texto


def subir_pdf_a_storage(ruta_pdf):
  nombre_archivo = os.path.basename(ruta_pdf)
  bucket_name = "emos_bucket"

  with open(ruta_pdf, "rb") as f:
    supabase.storage.from_(bucket_name).upload(
        path=nombre_archivo,
        file=f,
        file_options={"x-upsert": "true", "content-type": "application/pdf"},
    )

  url_publica = supabase.storage.from_(bucket_name).get_public_url(
      nombre_archivo
  )
  return url_publica


def procesar_con_ia(texto_pdf):
  prompt = f"""
    Eres un asistente médico ocupacional experto. Analiza el siguiente texto de un Examen Médico Ocupacional (EMO)
    y extrae la información en un objeto JSON estrictamente válido que coincida con las columnas de la base de datos.
    
    Estructura JSON requerida (las fechas deben estar en formato YYYY-MM-DD):
    {{
        "trabajador_nombre": "Apellidos y nombres completos",
        "empresa_nombre": "Nombre de la empresa",
        "puesto_trabajo": "Puesto de trabajo del trabajador",
        "tipo_examen": "Preocupacional, Periódico, o Retiro",
        "fecha_examen": "YYYY-MM-DD",
        "aptitud": "APTO, APTO CON RESTRICCION, o NO APTO",
        "restricciones": "Restricciones médicas si las hubiera (o null si no hay)",
        "observaciones": "Resumen de diagnósticos y hallazgos médicos encontrados",
        "recomendaciones": "Recomendaciones o controles indicados",
        "medico_nombre": "Nombre del médico evaluador (o null si no consta)",
        "medico_cmp": "Número de colegiatura CMP del médico (o null si no consta)"
    }}

    Texto a analizar:
    {texto_pdf}
    """

  response = client_ai.models.generate_content(
      model=MODEL_NAME,
      contents=prompt,
      config=types.GenerateContentConfig(
          response_mime_type="application/json",
      ),
  )

  return json.loads(response.text)


if __name__ == "__main__":
  archivo_pdf = "examen_prueba.pdf"

  if os.path.exists(archivo_pdf):
    print(f"📄 1. Leyendo archivo local: {archivo_pdf}...")
    texto = extraer_texto_pdf(archivo_pdf)

    print("☁️ 2. Subiendo archivo PDF a Supabase Storage...")
    try:
      pdf_url = subir_pdf_a_storage(archivo_pdf)
      print(f"   └─ URL generada: {pdf_url}")
    except Exception as e:
      print(f"   ⚠️ No se pudo subir el PDF al Storage: {e}")
      pdf_url = None

    print("🤖 3. Analizando documento con Gemini AI...")
    datos_extraidos = procesar_con_ia(texto)

    # Añadir la URL del PDF a los datos
    datos_extraidos["pdf_url"] = pdf_url

    print("\n🔍 Datos listos para insertar:")
    print(json.dumps(datos_extraidos, indent=2, ensure_ascii=False))

    print("\n💾 4. Guardando en la base de datos de Supabase...")
    res = supabase.table("emos").insert(datos_extraidos).execute()
    print(
        "\n🚀 ¡ÉXITO TOTAL! El Examen Médico Ocupacional fue procesado y"
        " registrado correctamente en la base de datos."
    )
  else:
    print(f"⚠️ No se encontró el archivo '{archivo_pdf}'.")