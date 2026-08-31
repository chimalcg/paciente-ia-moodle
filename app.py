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

@st.cache_data(ttl=3600)
def obtener_modelo_activo():
    """Detecta automáticamente el primer modelo disponible para generateContent según tu API Key."""
    try:
        modelos_disponibles = [
            m.name.replace("models/", "") 
            for m in genai.list_models() 
            if "generateContent" in m.supported_generation_methods
        ]
        # Lista de preferencia de modelos estables (con Pro al inicio para actualización futura)
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

# --- 3. CONSTRUIR DICCIONARIO DE PACIENTES PARA EL MENÚ ---
pacientes_dict = {}

for entrada in entries:
    entry_id = entrada["id"]
    textos_campo = []
    
    for campo in entrada.get("contents", []):
        t = limpiar_html(campo.get("content"))
        if t:
            textos_campo.append(t)
    
    titulo_paciente = textos_campo[0][:40] if textos_campo else f"Caso #{entry_id}"
    pacientes_dict[entry_id] = f"ID {entry_id}: {titulo_paciente}"

# --- 4. SELECCIÓN DE PACIENTE EN LA BARRA LATERAL ---
st.sidebar.header("📋 Expedientes Clínicos")

paciente_id_seleccionado = st.sidebar.selectbox(
    "Selecciona al paciente para la sesión:",
    options=list(pacientes_dict.keys()),
    format_func=lambda x: pacientes_dict[x]
)

entrada_actual = next((e for e in entries if e["id"] == paciente_id_seleccionado), None)

expediente_lineas = []
if entrada_actual:
    for campo in entrada_actual.get("contents", []):
        texto_limpio = limpiar_html(campo.get("content"))
        if texto_limpio:
            expediente_lineas.append(f"- {texto_limpio}")

expediente_texto = "\n".join(expediente_lineas)

# --- 5. GESTIÓN DEL ESTADO DEL CHAT ---
if "paciente_actual_id" not in st.session_state or st.session_state.paciente_actual_id != paciente_id_seleccionado:
    st.session_state.paciente_actual_id = paciente_id_seleccionado
    st.session_state.messages = [
        {"role": "assistant", "content": "Hola... buenas tardes. (Toma asiento y espera a que inicies la entrevista)."}
    ]

# Botón manual para reiniciar la entrevista actual
if st.sidebar.button("🔄 Reiniciar Entrevista Actual"):
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
    # Agregar y desplegar mensaje del usuario
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar="👨‍⚕️"):
        st.write(prompt)

    # Generar respuesta dinámica del paciente
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
