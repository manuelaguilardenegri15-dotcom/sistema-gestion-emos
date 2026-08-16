from datetime import datetime, date, timedelta
import io
import json
import re
from google import genai
from google.genai import types
import pandas as pd
from pypdf import PdfReader
import streamlit as st
from supabase import Client, create_client

# ---------------------------------------------------------
# 1. CONFIGURACIÓN DE LA PÁGINA Y ESTILOS CSS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Portal SST | Gestión de EMOs",
    page_icon="🏥",
    layout="wide",
)

st.markdown(
    """
    <style>
    .main { background-color: #f8f9fa; }
    .metric-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.05);
        border-left: 5px solid #0d6efd;
        text-align: center;
    }
    .metric-card-green { border-left-color: #198754; }
    .metric-card-yellow { border-left-color: #ffc107; }
    .metric-card-red { border-left-color: #dc3545; }
    .metric-title { font-size: 0.85rem; color: #6c757d; font-weight: 600; text-transform: uppercase; margin-bottom: 5px; }
    .metric-value { font-size: 1.7rem; font-weight: 700; color: #212529; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { height: 45px; background-color: #ffffff; border-radius: 8px; padding-left: 16px; padding-right: 16px; font-weight: 600; }
    </style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------
# 2. CREDENCIALES Y CONEXIÓN
# ---------------------------------------------------------
def obtener_secreto(clave, valor_defecto):
    try:
        return st.secrets.get(clave, valor_defecto)
    except Exception:
        return valor_defecto

SUPABASE_URL = obtener_secreto("SUPABASE_URL", "https://zezkvwiuhyojyaflvksc.supabase.co")
SUPABASE_KEY = obtener_secreto("SUPABASE_KEY", "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inplemt2d2l1aHlvanlhZmx2a3NjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODY1MDAyOTEsImV4cCI6MjEwMjA3NjI5MX0.32qTftolofuty8CnzllX8BMwObdmwIpXebEPEdfD-nw")
GEMINI_API_KEY = obtener_secreto("GEMINI_API_KEY", "AQ.Ab8RN6JjPCgRre0p0lYK8BtiKd7fSFPBjc_OjWaWkgHvdkV-pg")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
client_ai = genai.Client(api_key=GEMINI_API_KEY)
MODEL_NAME = "gemini-flash-latest"

# ---------------------------------------------------------
# 3. FUNCIONES DE AUTENTICACIÓN Y BASE DE DATOS
# ---------------------------------------------------------
@st.cache_data(ttl=0)
def obtener_usuarios_tabla():
    try:
        res = supabase.table("usuarios").select("*").order("created_at", desc=True).execute()
        return res.data or []
    except Exception:
        return []

def obtener_usuarios_bd():
    data = obtener_usuarios_tabla()
    usuarios_dict = {}
    for u in data:
        usuarios_dict[u["username"].lower()] = {
            "password": u["password"],
            "nombre": u["nombre_completo"],
            "rol": u["rol"],
            "empresa": u["empresa_nombre"],
        }
    return usuarios_dict

if "autenticado" not in st.session_state:
    st.session_state.autenticado = False
    st.session_state.usuario_info = None

def iniciar_sesion(usuario, password):
    usuarios_bd = obtener_usuarios_bd()
    usuario_clean = usuario.strip().lower()
    if usuario_clean in usuarios_bd and usuarios_bd[usuario_clean]["password"] == password:
        st.session_state.autenticado = True
        st.session_state.usuario_info = usuarios_bd[usuario_clean]
        st.session_state.usuario_actual = usuario_clean
        return True
    return False

def cerrar_sesion():
    st.session_state.autenticado = False
    st.session_state.usuario_info = None
    st.cache_data.clear()
    st.rerun()

# --- PANTALLA DE LOGIN ---
if not st.session_state.autenticado:
    col_a, col_b, col_c = st.columns([1, 1.5, 1])
    with col_b:
        st.write("")
        st.write("")
        st.markdown("### 🏥 Portal de Gestión de Salud Ocupacional")
        st.markdown("##### Inicie sesión para acceder a la plataforma")

        with st.form("login_form"):
            usr_input = st.text_input("Usuario", placeholder="Ej. admin o empresa_abc")
            pwd_input = st.text_input("Contraseña", type="password")
            btn_submit = st.form_submit_button("🔑 Iniciar Sesión", type="primary", use_container_width=True)

            if btn_submit:
                if iniciar_sesion(usr_input, pwd_input):
                    st.success("Acceso concedido...")
                    st.rerun()
                else:
                    st.error("Usuario o contraseña incorrectos.")

        st.info("💡 **Acceso Demo Administrador:**\n* **Usuario:** admin | **Clave:** admin123")
    st.stop()

# ---------------------------------------------------------
# 4. FUNCIONES AUXILIARES Y BACKEND
# ---------------------------------------------------------
def normalizar_texto(texto):
    if not texto: return ""
    texto = str(texto).upper()
    texto = re.sub(r"[ÁÀÄÂ]", "A", texto)
    texto = re.sub(r"[ÉÈËÊ]", "E", texto)
    texto = re.sub(r"[ÍÌÏÎ]", "I", texto)
    texto = re.sub(r"[ÓÒÖÔ]", "O", texto)
    texto = re.sub(r"[ÚÙÜÛ]", "U", texto)
    return texto.strip()

def extraer_texto_pdf_stream(uploaded_file):
    reader = PdfReader(uploaded_file)
    texto = ""
    for page in reader.pages:
        texto += page.extract_text() or ""
    return texto

def subir_pdf_a_storage(uploaded_file):
    nombre_archivo = f"{int(datetime.now().timestamp())}_{uploaded_file.name}"
    bucket_name = "emos_bucket"
    file_bytes = uploaded_file.getvalue()
    supabase.storage.from_(bucket_name).upload(
        path=nombre_archivo,
        file=file_bytes,
        file_options={"x-upsert": "true", "content-type": "application/pdf"},
    )
    return supabase.storage.from_(bucket_name).get_public_url(nombre_archivo)

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
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return json.loads(response.text)

@st.cache_data(ttl=0)
def cargar_registros():
    res = supabase.table("emos").select("*").order("created_at", desc=True).execute()
    return res.data or []

def calcular_vigencia(fecha_str):
    if not fecha_str:
        return "SIN FECHA", "⚪"
    try:
        fecha_emo = datetime.strptime(str(fecha_str)[:10], "%Y-%m-%d").date()
        fecha_vencimiento = fecha_emo + timedelta(days=365)
        hoy = date.today()
        dias_restantes = (fecha_vencimiento - hoy).days

        if dias_restantes < 0:
            return "VENCIDO", "🔴"
        elif dias_restantes <= 30:
            return "POR VENCER (30d)", "🟡"
        else:
            return "VIGENTE", "🟢"
    except Exception:
        return "NO EVALUADO", "⚪"

# ---------------------------------------------------------
# 5. INTERFAZ PRINCIPAL Y NAVEGACIÓN
# ---------------------------------------------------------
user_info = st.session_state.usuario_info

col_title, col_user = st.columns([3, 1])
with col_title:
    st.title("🏥 Portal de Gestión de Salud Ocupacional")
with col_user:
    st.write("")
    st.markdown(f"👤 **{user_info['nombre']}**")
    texto_empresa = f"({user_info['empresa']})" if user_info['rol'] == 'empresa' else ""
    st.caption(f"Rol: {user_info['rol'].upper()} {texto_empresa}")
    if st.button("🚪 Cerrar Sesión"):
        cerrar_sesion()

st.write("---")

# Configuración de Pestañas según Rol
if user_info["rol"] == "admin":
    tab_dashboard, tab_subir, tab_editar, tab_usuarios = st.tabs(
        ["📊 Dashboard y Control", "📤 Cargar Nuevo EMO", "✏️ Editar/Eliminar EMOs", "👥 Gestión de Usuarios"]
    )
else:
    # La empresa cliente ve su Dashboard y la opción de Cargar sus propios EMOs
    tab_dashboard, tab_subir = st.tabs(["📊 Dashboard y Control", "📤 Cargar Nuevo EMO"])
    tab_editar = None
    tab_usuarios = None

# ---------------------------------------------------------
# VISTA 1: DASHBOARD Y CONTROL
# ---------------------------------------------------------
with tab_dashboard:
    registros = cargar_registros()

    if registros:
        df = pd.DataFrame(registros)

        # Filtrado Multi-empresa para usuarios con rol 'empresa'
        if user_info["rol"] == "empresa":
            empresa_target = normalizar_texto(user_info["empresa"])
            df["empresa_norm"] = df["empresa_nombre"].apply(normalizar_texto)
            df = df[df["empresa_norm"] == empresa_target]

        if not df.empty:
            df["aptitud_norm"] = df["aptitud"].apply(normalizar_texto)
            
            # Calcular vigencia de EMOs
            vigencias = [calcular_vigencia(f) for f in df.get("fecha_examen", [])]
            df["estado_vigencia"] = [v[0] for v in vigencias]
            df["icono_vigencia"] = [v[1] for v in vigencias]
            df["vigencia_label"] = df["icono_vigencia"] + " " + df["estado_vigencia"]

            # MÉTIRCAS CLAVE
            total_ex = len(df)
            aptos = len(df[df["aptitud_norm"] == "APTO"])
            aptos_rest = len(df[df["aptitud_norm"] == "APTO CON RESTRICCION"])
            no_aptos = len(df[df["aptitud_norm"] == "NO APTO"])
            vencidos = len(df[df["estado_vigencia"] == "VENCIDO"])

            col1, col2, col3, col4, col5 = st.columns(5)
            with col1:
                st.markdown(f'<div class="metric-card"><div class="metric-title">Total Exámenes</div><div class="metric-value">{total_ex}</div></div>', unsafe_allow_html=True)
            with col2:
                st.markdown(f'<div class="metric-card metric-card-green"><div class="metric-title">Aptos</div><div class="metric-value">{aptos}</div></div>', unsafe_allow_html=True)
            with col3:
                st.markdown(f'<div class="metric-card metric-card-yellow"><div class="metric-title">Aptos c/ Restricción</div><div class="metric-value">{aptos_rest}</div></div>', unsafe_allow_html=True)
            with col4:
                st.markdown(f'<div class="metric-card metric-card-red"><div class="metric-title">No Aptos</div><div class="metric-value">{no_aptos}</div></div>', unsafe_allow_html=True)
            with col5:
                st.markdown(f'<div class="metric-card metric-card-red"><div class="metric-title">Vencidos</div><div class="metric-value">{vencidos}</div></div>', unsafe_allow_html=True)

            st.write("")
            st.write("")

            # FILTROS Y BÚSQUEDA
            col_f1, col_f2, col_f3 = st.columns([2, 1, 1])
            with col_f1:
                busqueda = st.text_input("🔍 Buscar trabajador, empresa o puesto:", placeholder="Escribe para buscar...")
            with col_f2:
                filtro_aptitud = st.selectbox("Aptitud Médica:", ["TODOS", "APTO", "APTO CON RESTRICCION", "NO APTO"])
            with col_f3:
                filtro_vigencia = st.selectbox("Estado Vigencia:", ["TODOS", "VIGENTE", "POR VENCER (30d)", "VENCIDO"])

            df_filtrado = df.copy()
            if filtro_aptitud != "TODOS":
                df_filtrado = df_filtrado[df_filtrado["aptitud_norm"] == filtro_aptitud]
            if filtro_vigencia != "TODOS":
                df_filtrado = df_filtrado[df_filtrado["estado_vigencia"] == filtro_vigencia]

            if busqueda:
                df_filtrado = df_filtrado[
                    df_filtrado["trabajador_nombre"].str.contains(busqueda, case=False, na=False)
                    | df_filtrado["empresa_nombre"].str.contains(busqueda, case=False, na=False)
                    | df_filtrado["puesto_trabajo"].str.contains(busqueda, case=False, na=False)
                ]

            columnas_mostrar = ["trabajador_nombre", "empresa_nombre", "puesto_trabajo", "tipo_examen", "fecha_examen", "vigencia_label", "aptitud", "restricciones", "pdf_url"]

            st.dataframe(
                df_filtrado[columnas_mostrar],
                column_config={
                    "trabajador_nombre": st.column_config.TextColumn("Trabajador", width="medium"),
                    "empresa_nombre": st.column_config.TextColumn("Empresa"),
                    "puesto_trabajo": st.column_config.TextColumn("Puesto"),
                    "tipo_examen": st.column_config.TextColumn("Tipo"),
                    "fecha_examen": st.column_config.DateColumn("Fecha EMO", format="YYYY-MM-DD"),
                    "vigencia_label": st.column_config.TextColumn("Vigencia Anual"),
                    "aptitud": st.column_config.TextColumn("Aptitud Médica"),
                    "restricciones": st.column_config.TextColumn("Restricciones Médicas", width="medium"),
                    "pdf_url": st.column_config.LinkColumn("PDF Adjunto", display_text="📄 Abrir EMO"),
                },
                use_container_width=True,
                hide_index=True,
            )

            # EXPORTACIÓN A EXCEL / CSV
            st.write("")
            col_exp1, col_exp2 = st.columns([4, 1])
            with col_exp2:
               # Preparar los datos limpios
               df_excel = df_filtrado.drop(columns=["empresa_norm", "aptitud_norm", "icono_vigencia"], errors="ignore")
    
               # Crear buffer en memoria para Excel
               buffer = io.BytesIO()
               with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                 df_excel.to_excel(writer, index=False, sheet_name='Matriz_EMOs')
    
               buffer.seek(0)

               nombre_empresa_file = user_info['empresa'] if user_info['rol'] == 'empresa' else 'General'
    
               st.download_button(
                    label="📊 Descargar Matriz (Excel)",
                     data=buffer,
                     file_name=f"Matriz_EMOs_{nombre_empresa_file}.xlsx",
                     mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                     use_container_width=True
                )

        else:
            st.info(f"💡 No hay registros de exámenes médicos asociados a **{user_info['empresa']}**.")
    else:
        st.info("💡 No hay exámenes médicos registrados en la base de datos.")

# ---------------------------------------------------------
# VISTA 2: CARGAR NUEVO EMO (ADMIN Y EMPRESAS CLIENTES)
# ---------------------------------------------------------
if tab_subir:
    with tab_subir:
        st.subheader("📤 Registro e Ingreso de Exámenes Médicos Ocupacionales (EMOs)")
        
        if user_info["rol"] == "empresa":
            st.info(f"🏢 Los exámenes cargados se asociarán automáticamente a tu empresa: **{user_info['empresa']}**")

        modo_carga = st.radio(
            "Selecciona el método de carga:",
            ["✨ Extracción Automática con Gemini AI (Recomendado)", "✍️ Ingreso Manual (Para PDFs escaneados o borrosos)"],
            horizontal=True
        )

        st.divider()

        # MODO 1: AUTOMÁTICO CON GEMINI AI
        if "Gemini AI" in modo_carga:
            archivo_pdf = st.file_uploader("Selecciona el archivo PDF del EMO:", type=["pdf"])

            if archivo_pdf is not None:
                if st.button("✨ Procesar Documento con IA", type="primary"):
                    with st.spinner("⚙️ Extrayendo información y sincronizando con la nube..."):
                        try:
                            texto = extraer_texto_pdf_stream(archivo_pdf)
                            pdf_url = subir_pdf_a_storage(archivo_pdf)
                            datos_extraidos = procesar_con_ia(texto)
                            datos_extraidos["pdf_url"] = pdf_url

                            # Si quien sube es Rol Empresa, forzamos su nombre de empresa
                            if user_info["rol"] == "empresa":
                                datos_extraidos["empresa_nombre"] = user_info["empresa"]

                            supabase.table("emos").insert(datos_extraidos).execute()
                            st.cache_data.clear()

                            st.success("✅ Examen Médico procesado e insertado correctamente.")
                            st.balloons()
                            st.rerun()

                        except Exception as e:
                            st.error(f"Error en el procesamiento: {e}")

        # MODO 2: INGRESO MANUAL
        else:
            st.write("Completa los datos del trabajador y adjunta el PDF digitalizado.")
            with st.form("form_carga_manual"):
                col_m1, col_m2 = st.columns(2)
                with col_m1:
                    trabajador = st.text_input("Nombre Completo del Trabajador:*")
                    empresa_ingreso = st.text_input(
                        "Nombre de la Empresa:*",
                        value=user_info["empresa"] if user_info["rol"] == "empresa" else "",
                        disabled=(user_info["rol"] == "empresa")
                    )
                    puesto = st.text_input("Puesto de Trabajo:*")
                    tipo_examen = st.selectbox("Tipo de Examen:*", ["Preocupacional", "Periódico", "Retiro", "Ocupacional"])
                    fecha_ex = st.date_input("Fecha del Examen Médico:*", value=date.today())

                with col_m2:
                    aptitud = st.selectbox("Aptitud Médica:*", ["APTO", "APTO CON RESTRICCION", "NO APTO"])
                    restricciones = st.text_area("Restricciones Médicas (si aplica):", placeholder="Ej. Uso obligatorio de lentes correctores...")
                    observaciones = st.text_area("Observaciones / Hallazgos:", placeholder="Ej. Dislipidemia leve...")
                    medico_nombre = st.text_input("Nombre del Médico Evaluador:")
                    medico_cmp = st.text_input("N° Colegiatura CMP:")

                pdf_manual = st.file_uploader("Adjuntar documento PDF escaneado:*", type=["pdf"])
                btn_manual = st.form_submit_button("💾 Guardar EMO Manualmente", type="primary")

                if btn_manual:
                    if not trabajador or not puesto or not pdf_manual or (user_info["rol"] == "admin" and not empresa_ingreso):
                        st.error("Por favor completa los campos obligatorios (*) y adjunta el PDF.")
                    else:
                        try:
                            pdf_url = subir_pdf_a_storage(pdf_manual)
                            datos_manuales = {
                                "trabajador_nombre": trabajador.strip(),
                                "empresa_nombre": user_info["empresa"] if user_info["rol"] == "empresa" else empresa_ingreso.strip(),
                                "puesto_trabajo": puesto.strip(),
                                "tipo_examen": tipo_examen,
                                "fecha_examen": str(fecha_ex),
                                "aptitud": aptitud,
                                "restricciones": restricciones.strip() if restricciones else None,
                                "observaciones": observaciones.strip() if observaciones else None,
                                "medico_nombre": medico_nombre.strip() if medico_nombre else None,
                                "medico_cmp": medico_cmp.strip() if medico_cmp else None,
                                "pdf_url": pdf_url
                            }
                            supabase.table("emos").insert(datos_manuales).execute()
                            st.cache_data.clear()
                            st.success("✅ Examen Médico guardado exitosamente.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"Error al guardar registro manual: {err}")

# ---------------------------------------------------------
# VISTA 3: EDITAR O ELIMINAR REGISTROS (SOLO ADMIN)
# ---------------------------------------------------------
if tab_editar:
    with tab_editar:
        st.subheader("✏️ Edición y Eliminación de Registros de EMO")
        st.write("Permite corregir datos extraídos erróneamente o borrar registros duplicados.")

        registros_todos = cargar_registros()
        if registros_todos:
            opciones_emo = {f"{r['trabajador_nombre']} - {r['empresa_nombre']} ({r.get('fecha_examen', 'Sin fecha')}) [ID: {r['id']}]": r for r in registros_todos}
            seleccion_emo = st.selectbox("Selecciona el EMO a modificar o borrar:", list(opciones_emo.keys()))

            emo_obj = opciones_emo[seleccion_emo]

            col_ed1, col_ed2 = st.columns([2, 1])

            with col_ed1:
                st.markdown("##### 📝 Modificar Datos")
                with st.form("form_edicion"):
                    e_trabajador = st.text_input("Trabajador:", value=emo_obj.get("trabajador_nombre", ""))
                    e_empresa = st.text_input("Empresa:", value=emo_obj.get("empresa_nombre", ""))
                    e_puesto = st.text_input("Puesto:", value=emo_obj.get("puesto_trabajo", ""))
                    e_aptitud = st.selectbox("Aptitud:", ["APTO", "APTO CON RESTRICCION", "NO APTO"], index=["APTO", "APTO CON RESTRICCION", "NO APTO"].index(emo_obj.get("aptitud", "APTO")) if emo_obj.get("aptitud") in ["APTO", "APTO CON RESTRICCION", "NO APTO"] else 0)
                    e_restricciones = st.text_area("Restricciones:", value=emo_obj.get("restricciones") or "")
                    
                    btn_actualizar = st.form_submit_button("🔄 Actualizar Registro", type="primary")

                    if btn_actualizar:
                        try:
                            supabase.table("emos").update({
                                "trabajador_nombre": e_trabajador,
                                "empresa_nombre": e_empresa,
                                "puesto_trabajo": e_puesto,
                                "aptitud": e_aptitud,
                                "restricciones": e_restricciones
                            }).eq("id", emo_obj["id"]).execute()
                            st.cache_data.clear()
                            st.success("✅ Registro actualizado correctamente.")
                            st.rerun()
                        except Exception as err:
                            st.error(f"Error al actualizar: {err}")

            with col_ed2:
                st.markdown("##### 🗑️ Eliminar Registro")
                st.warning("⚠️ Esta acción es permanente y no se puede deshacer.")
                if st.button("🗑️ Eliminar este EMO", type="secondary"):
                    try:
                        supabase.table("emos").delete().eq("id", emo_obj["id"]).execute()
                        st.cache_data.clear()
                        st.success("🗑️ Registro eliminado correctamente.")
                        st.rerun()
                    except Exception as err:
                        st.error(f"Error al eliminar: {err}")
        else:
            st.info("No hay exámenes para editar.")

# ---------------------------------------------------------
# VISTA 4: GESTIÓN DE USUARIOS (SOLO ADMIN)
# ---------------------------------------------------------
if tab_usuarios:
    with tab_usuarios:
        col_reg, col_reset = st.columns([1, 1], gap="large")

        # Registrar Empresa Cliente
        with col_reg:
            st.subheader("➕ Registrar Nueva Empresa Cliente")
            with st.form("crear_usuario_form"):
                nuevo_usuario = st.text_input("Nombre de Usuario (Login):*", placeholder="Ej. empresa_abc")
                nueva_clave = st.text_input("Contraseña Inicial:*", type="password")
                nombre_completo = st.text_input("Nombre del Contacto:*", placeholder="Ej. Ing. Juan Pérez")
                empresa_asociada = st.text_input("Nombre de la Empresa:*", placeholder="Ej. CONSTRUCTORA ABC S.A.C.")

                btn_crear = st.form_submit_button("➕ Guardar Empresa", type="primary")

                if btn_crear:
                    if nuevo_usuario and nueva_clave and empresa_asociada:
                        try:
                            nuevo_registro = {
                                "username": nuevo_usuario.strip().lower(),
                                "password": nueva_clave.strip(),
                                "nombre_completo": nombre_completo.strip(),
                                "empresa_nombre": empresa_asociada.strip(),
                                "rol": "empresa",
                            }
                            supabase.table("usuarios").insert(nuevo_registro).execute()
                            st.cache_data.clear()
                            st.success(f"🎉 ¡Empresa '{empresa_asociada}' registrada con éxito!")
                            st.rerun()
                        except Exception as err:
                            st.error(f"Error al registrar usuario: {err}")
                    else:
                        st.warning("Completa los campos obligatorios.")

        # Cambiar Contraseña
        with col_reset:
            st.subheader("🔑 Cambiar / Recuperar Contraseña")
            lista_usuarios = obtener_usuarios_tabla()
            usuarios_clientes = [u for u in lista_usuarios if u.get("rol") != "admin"]

            if usuarios_clientes:
                opciones = {f"{u['empresa_nombre']} (Usuario: {u['username']})": u for u in usuarios_clientes}
                seleccion = st.selectbox("Selecciona el Cliente:", list(opciones.keys()))
                usuario_obj = opciones[seleccion]

                with st.form("reset_pass_form"):
                    st.info(f"👤 **Contacto:** {usuario_obj.get('nombre_completo', 'N/A')}\n\n🏢 **Empresa:** {usuario_obj.get('empresa_nombre')}")
                    clave_nueva = st.text_input("Nueva Contraseña:", type="password")
                    btn_reset = st.form_submit_button("🔄 Actualizar Contraseña", type="primary")

                    if btn_reset:
                        if clave_nueva.strip():
                            try:
                                supabase.table("usuarios").update({"password": clave_nueva.strip()}).eq("id", usuario_obj["id"]).execute()
                                st.cache_data.clear()
                                st.success("✅ Contraseña actualizada exitosamente.")
                            except Exception as e:
                                st.error(f"Error: {e}")
            else:
                st.info("💡 Aún no hay empresas registradas.")

        st.write("---")
        st.subheader("📋 Usuarios Registrados en el Sistema")
        if lista_usuarios:
            df_u = pd.DataFrame(lista_usuarios)[["username", "nombre_completo", "empresa_nombre", "rol", "created_at"]]
            st.dataframe(df_u, use_container_width=True, hide_index=True)