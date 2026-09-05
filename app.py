import streamlit as st
import requests
import re
import json
import os
from bs4 import BeautifulSoup
import google.generativeai as genai

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Simulador de Pacientes Virtuales", 
    page_icon="logo_ad.jpeg", 
    layout="centered"
)

col_logo, col_titulo = st.columns([1, 5])

with col_logo:
    st.image("logo_ad.jpeg", use_container_width=True)

with col_titulo:
    st.title("Simulador de Entrevistas Clínicas")
coltera1, coltera2, coltera3 = st.columns([1, 2, 1])

with coltera2:  # Colocamos la imagen solo en la columna del centro
    st.image("terapia.jpeg", use_container_width=True)
st.caption("Selecciona un paciente del expediente de Moodle para iniciar la sesión de práctica.")

# --- CARPETA DE RESPALDOS ---
DATA_DIR = "guardados"
if not os.path.exists(DATA_DIR):
    os.makedirs(DATA_DIR)

# --- 1. SEGURIDAD Y CREDENCIALES ---
api_key = st.secrets.get("GEMINI_API_KEY", "")
if not api_key:
    st.error("⚠️ La clave de API de Gemini no está configurada en los Secrets de Streamlit.")
    st.stop()

genai.configure(api_key=api_key)

MOODLE_URL = "https://srv1032855.hstgr.cloud/webservice/rest/server.php"
MOODLE_TOKEN = "df2c3a0daa0665858b4b087b2d682003"
DATABASE_ID = 5

def limpiar_html(raw_html):
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    texto = soup.get_text(separator=" ")
    return re.sub(r'\s+', ' ', texto).strip()

@st.cache_data(ttl=3600)
def obtener_modelo_activo():
    try:
        modelos_disponibles = [
            m.name.replace("models/", "") 
            for m in genai.list_models() 
            if "generateContent" in m.supported_generation_methods
        ]
        for preferido in ["gemini-1.5-pro", "gemini-2.0-pro", "gemini-1.5-flash-latest", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-pro"]:
            if preferido in modelos_disponibles:
                return preferido
        if modelos_disponibles:
            return modelos_disponibles[0]
    except Exception:
        pass
    return "gemini-1.5-flash-latest"

# --- 2. CARGAR TODOS LOS PACIENTES DESDE MOODLE ---
@st.cache_data(ttl=300)
def obtener_todos_los_pacientes():
    params = {
        "wstoken": MOODLE_TOKEN,
        "wsfunction": "mod_data_get_entries",
        "moodlewsrestformat": "json",
        "databaseid": DATABASE_ID,
        "returncontents": 1
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        res = requests.get(MOODLE_URL, params=params, headers=headers, timeout=15).json()
        entries = res.get("entries", [])
        return entries
    except Exception as e:
        st.error(f"Error de conexión con Moodle: {e}")
        return []

entries = obtener_todos_los_pacientes()

if not entries:
    st.warning("No se encontraron expedientes clínicos registrados en la base de datos de Moodle.")
    st.stop()

# --- 3. CONSTRUIR DICCIONARIO DE PACIENTES USANDO EL CAMPO 2 (NOMBRE) ---
pacientes_dict = {}

for entrada in entries:
    entry_id = entrada["id"]
    textos_campo = []
    
    for campo in entrada.get("contents", []):
        t = limpiar_html(campo.get("content"))
        if t:
            textos_campo.append(t)
    
    # Extraer el nombre de forma segura (campo índice 1)
    if len(textos_campo) > 1:
        # Muestra el nombre del paciente y su identificador
        nombre_paciente = f"{textos_campo[1]} (ID: {textos_campo[0]})"
    elif len(textos_campo) == 1:
        nombre_paciente = textos_campo[0]
    else:
        nombre_paciente = f"Caso #{entry_id}"
        
    pacientes_dict[entry_id] = nombre_paciente

# --- 4. BÚSQUEDA Y SELECCIÓN DE PACIENTE EN LA BARRA LATERAL ---
st.sidebar.image("logov.jpeg", use_container_width=True)
st.sidebar.header("📋 Expedientes Clínicos")

# Buscador en tiempo real
criterio_busqueda = st.sidebar.text_input("🔍 Buscar paciente por nombre:", "").strip().lower()

if criterio_busqueda:
    pacientes_filtrados = {
        id_p: nombre for id_p, nombre in pacientes_dict.items()
        if criterio_busqueda in nombre.lower()
    }
else:
    pacientes_filtrados = pacientes_dict

if not pacientes_filtrados:
    st.sidebar.warning("No se encontraron pacientes que coincidan con la búsqueda.")
    st.stop()

paciente_id_seleccionado = st.sidebar.selectbox(
    "Selecciona al paciente para la sesión:",
    options=list(pacientes_filtrados.keys()),
    format_func=lambda x: pacientes_filtrados[x]
)

entrada_actual = next((e for e in entries if e["id"] == paciente_id_seleccionado), None)

expediente_lineas = []
if entrada_actual:
    for campo in entrada_actual.get("contents", []):
        texto_limpio = limpiar_html(campo.get("content"))
        if texto_limpio:
            expediente_lineas.append(f"- {texto_limpio}")

expediente_texto = "\n".join(expediente_lineas)

# --- 5. SISTEMA DE GESTIÓN Y PERSISTENCIA DE SESIÓN ---
if "paciente_actual_id" not in st.session_state or st.session_state.paciente_actual_id != paciente_id_seleccionado:
    st.session_state.paciente_actual_id = paciente_id_seleccionado
    st.session_state.messages = [
        {"role": "assistant", "content": "Hola... buenas tardes. (Toma asiento y espera a que inicies la entrevista)."}
    ]

st.sidebar.markdown("---")
st.sidebar.header("💾 Progreso de Entrevista")

alumno_id = st.sidebar.text_input("Ingresa tu Matrícula o Nombre:", placeholder="Ej. A01234567").strip()

def obtener_ruta_archivo():
    if not alumno_id:
        return None
    nombre_limpio = re.sub(r'[^a-zA-Z0-9_-]', '_', alumno_id.lower())
    return os.path.join(DATA_DIR, f"{nombre_limpio}_paciente_{paciente_id_seleccionado}.json")

col_btn1, col_btn2 = st.sidebar.columns(2)

with col_btn1:
    if st.button("💾 Guardar", use_container_width=True):
        ruta = obtener_ruta_archivo()
        if not ruta:
            st.sidebar.error("Escribe tu matrícula o nombre para guardar.")
        else:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(st.session_state.messages, f, ensure_ascii=False, indent=2)
            st.sidebar.success("¡Progreso guardado!")

with col_btn2:
    if st.button("📂 Cargar", use_container_width=True):
        ruta = obtener_ruta_archivo()
        if not ruta:
            st.sidebar.error("Escribe tu matrícula o nombre para cargar.")
        elif os.path.exists(ruta):
            with open(ruta, "r", encoding="utf-8") as f:
                st.session_state.messages = json.load(f)
            st.sidebar.success("¡Sesión restaurada!")
            st.rerun()
        else:
            st.sidebar.warning("No hay sesión guardada para este paciente.")

col_btn3, col_btn4 = st.sidebar.columns(2)

with col_btn3:
    if st.button("💾🚪 Guardar y Salir", use_container_width=True):
        ruta = obtener_ruta_archivo()
        if not ruta:
            st.sidebar.error("Escribe tu matrícula o nombre antes de salir.")
        else:
            with open(ruta, "w", encoding="utf-8") as f:
                json.dump(st.session_state.messages, f, ensure_ascii=False, indent=2)
            st.session_state.messages = [
                {"role": "assistant", "content": "Hola... buenas tardes. (Toma asiento y espera a que inicies la entrevista)."}
            ]
            st.sidebar.info("Progreso guardado. Sesión cerrada.")
            st.rerun()

with col_btn4:
    if st.button("🚪 Salir sin Guardar", use_container_width=True):
        st.session_state.messages = [
            {"role": "assistant", "content": "Hola... buenas tardes. (Toma asiento y espera a que inicies la entrevista)."}
        ]
        st.rerun()

with st.sidebar.expander("📄 Ver Ficha Técnica de la Entrada"):
    st.text(expediente_texto)

# --- 6. RENDERIZADO DEL CHAT INTERACTIVO ---
for msg in st.session_state.messages:
    avatar = "👨‍⚕️" if msg["role"] == "user" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

# --- 7. PROCESAMIENTO DE INTERACCIÓN ---
if prompt := st.chat_input("Escribe tu intervención como terapeuta..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👨‍⚕️"):
        st.write(prompt)

    with st.chat_message("assistant", avatar="👤"):
        with st.spinner("El paciente está respondiendo..."):
            try:
                nombre_modelo = obtener_modelo_activo()
                
                system_instruction = f"""
Actúa exclusivamente como el paciente descrito en la ficha clínica adjunta.
No rompas el personaje bajo ninguna circunstancia ni reveles que eres una IA o un modelo de lenguaje.

EXPEDIENTE CLÍNICO DEL PACIENTE:
{expediente_texto}

REGLAS ESTRICTAS DE INTERPRETACIÓN Y COMPORTAMIENTO:
1. Responde como un paciente real, con emociones, dudas y posibles resistencias acordes a tu expediente.
2. DOSIFICACIÓN DE INFORMACIÓN: NO proporciones toda tu historia o datos de inmediato. Permite que el alumno explore e indague mediante preguntas.
3. Muestra congruencia estricta con el motivo de consulta. Puedes presentar ambivalencia, evasión o dificultad para expresar tus emociones.
4. Si el terapeuta hace preguntas profundas, empáticas o bien formuladas, responde abriéndote gradualmente y dando más detalle.
5. Desarrolla gradualmente (solo si se indaga en la sesión):
   - Historia del problema y eventos recientes relacionados.
   - Relaciones familiares y dinámicas interpersonales.
   - Pensamientos recurrentes, síntomas emocionales y físicos.
6. NO actúes como experto en psicología ni uses lenguaje clínico técnico. Habla desde tu vivencia personal.
7. Al iniciar la interacción o responder a la primera indagación del terapeuta, menciona brevemente y de forma reservada tu motivo principal de consulta.
"""
                gemini_history = []
                for m in st.session_state.messages[:-1]:
                    role = "user" if m["role"] == "user" else "model"
                    gemini_history.append({"role": role, "parts": [m["content"]]})

                model = genai.GenerativeModel(
                    model_name=nombre_modelo,
                    system_instruction=system_instruction
                )
                
                chat = model.start_chat(history=gemini_history)
                response = chat.send_message(prompt)

                st.write(response.text)
                st.session_state.messages.append({"role": "assistant", "content": response.text})
            except Exception as e:
                st.error(f"Error en la interacción con la API de Gemini: {e}")
