import streamlit as st
import requests
import re
from bs4 import BeautifulSoup
import google.generativeai as genai

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Simulador de Pacientes Virtuales", 
    page_icon="🧠", 
    layout="centered"
)

st.title("🧠 Simulador de Entrevistas Clínicas")
st.caption("Selecciona un paciente del expediente de Moodle para iniciar la sesión de práctica.")

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

# --- 3. CONSTRUIR DICCIONARIO DE PACIENTES PARA EL MENÚ ---
pacientes_dict = {}

for entrada in entries:
    entry_id = entrada["id"]
    textos_campo = []
    
    for campo in entrada.get("contents", []):
        t = limpiar_html(campo.get("content"))
        if t:
            textos_campo.append(t)
    
    # Toma el primer campo legible como nombre/título o usa el ID
    titulo_paciente = textos_campo[0][:40] if textos_campo else f"Caso #{entry_id}"
    pacientes_dict[entry_id] = f"ID {entry_id}: {titulo_paciente}"

# --- 4. SELECCIÓN DE PACIENTE EN LA BARRA LATERAL ---
st.sidebar.header("📋 Expedientes Clínicos")

paciente_id_seleccionado = st.sidebar.selectbox(
    "Selecciona al paciente para la sesión:",
    options=list(pacientes_dict.keys()),
    format_func=lambda x: pacientes_dict[x]
)

# Extraer el expediente completo del paciente seleccionado
entrada_actual = next((e for e in entries if e["id"] == paciente_id_seleccionado), None)

expediente_lineas = []
if entrada_actual:
    for campo in entrada_actual.get("contents", []):
        texto_limpio = limpiar_html(campo.get("content"))
        if texto_limpio:
            expediente_lineas.append(f"- {texto_limpio}")

expediente_texto = "\n".join(expediente_lineas)

# --- 5. GESTIÓN DEL ESTADO DEL CHAT ---
# Si el alumno cambia de paciente en el menú, se reinicia la conversación automáticamente
if "paciente_actual_id" not in st.session_state or st.session_state.paciente_actual_id != paciente_id_seleccionado:
    st.session_state.paciente_actual_id = paciente_id_seleccionado
    
    system_instruction = f"""
Actúa exclusivamente como el paciente descrito en la siguiente ficha clínica.
Mantén el tono, lenguaje corporal implícito, sesgos cognitivos, resistencias y motivo de consulta descritos en la ficha.
No rompas el personaje bajo ninguna circunstancia ni reveles que eres una IA.

EXPEDIENTE CLÍNICO DEL PACIENTE:
{expediente_texto}
"""

    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=system_instruction
    )
    
    st.session_state.chat = model.start_chat(history=[])
    
    # Saludo inicial general en rol
    st.session_state.messages = [
        {"role": "assistant", "content": "Hola... pase y tome asiento. (Se acomoda esperando que inicies la consulta)."}
    ]

# Botón manual para reiniciar la entrevista actual
if st.sidebar.button("🔄 Reiniciar Entrevista Actual"):
    st.session_state.paciente_actual_id = None
    st.rerun()

# Mostrar información básica del expediente activo en la barra lateral
with st.sidebar.expander("📄 Ver Ficha Técnica de la Entrada"):
    st.text(expediente_texto)

# --- 6. RENDERIZADO DEL CHAT INTERACTIVO ---
for msg in st.session_state.messages:
    avatar = "👨‍⚕️" if msg["role"] == "user" else "👤"
    with st.chat_message(msg["role"], avatar=avatar):
        st.write(msg["content"])

# Entrada de respuesta del alumno
if prompt := st.chat_input("Escribe tu intervención como terapeuta..."):
    # Guardar y mostrar mensaje del terapeuta
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👨‍⚕️"):
        st.write(prompt)

    # Respuesta generada por la IA
    with st.chat_message("assistant", avatar="👤"):
        with st.spinner("El paciente está respondiendo..."):
            response = st.session_state.chat.send_message(prompt)
            st.write(response.text)
            st.session_state.messages.append({"role": "assistant", "content": response.text})