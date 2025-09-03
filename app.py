import streamlit as st
import google.generativeai as genai
import json
import re
import docx
from pypdf import PdfReader

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Asistente de Licitaciones AI", layout="wide", initial_sidebar_state="collapsed")

# --- CONFIGURACIÓN DE LA API KEY Y MODELO DE IA ---
# Streamlit buscará el secret 'GEMINI_API_KEY' que has configurado.
try:
    # --- CORRECCIÓN AQUÍ ---
    # Usamos el NOMBRE del secret (la clave), no el valor.
    api_key = st.secrets["GEMINI_API_KEY"]
    genai.configure(api_key=api_key)
    # Usamos un modelo potente y rápido para esta tarea
    model = genai.GenerativeModel('gemini-2.5-flash')
except Exception as e:
    # Mostramos un error amigable si la API Key no está configurada
    st.error(f"Error al configurar la API de Gemini. Asegúrate de que el secret 'GEMINI_API_KEY' esté bien configurado en 'Manage app'. Error: {e}")
    # Detenemos la ejecución de la app si no hay API Key
    st.stop()

# --- PROMPTS DE LA IA ---
# He copiado tus prompts directamente desde tu código de Colab.

PROMPT_PLANTILLA = """
Eres un analista de documentos extremadamente preciso.
Te daré el texto de una plantilla de memoria técnica y los Pliegos correspondientes.
Tu única tarea es convertirlo a un objeto JSON que contenga la estructura del indice y unas indicaciones para que la persona
que va a redactar la memoria técnica sepa todo lo necesario para poder redactar la memoria técnica con mayor puntuación.

## REGLAS ESTRICTAS:
1.  La estructura del documento debes sacarlo de la plantilla y las indicaciones mezclando esa información con la de los pliegos.
2.  El objeto JSON DEBE contener dos claves de nivel superior y solo dos: "estructura_memoria" y "matices_desarrollo".
3.  Para CADA apartado y subapartado, DEBES anteponer su numeración correspondiente (ej: "1. Título", "1.1. Subtítulo").
    ESTO ES OBLIGATORIO Y DEBE SER EN NÚMEROS NORMALES (1,2,3...) NADA DE LETRAS NI COSAS RARAS.
4.  La clave "estructura_memoria" contiene la lista de apartados y subapartados como un ÍNDICE.
    La lista "subapartados" SOLO debe contener los TÍTULOS numerados, NUNCA el texto de las instrucciones.
5.  Debes coger exactamente el mismo título del apartado o subapartado que existe en el texto de la plantilla, no lo modifiques.
    Mantenlo aunque esté en otro idioma.
6.  La clave "matices_desarrollo" desglosa CADA subapartado, asociando su título numerado con las INSTRUCCIONES completas.
    NO RESUMAS. DEBES CONTAR TODO LO QUE SEPAS DE ELLO.
    Llena estas indicaciones de mucho contexto útil para que alguien sin experiencia pueda redactar la memoria.
7.  DEBES INDICAR OBLIGATORIAMENTE LA LONGITUD DE CADA SUBAPARTADO.
    NO TE LO PUEDES INVENTAR. ESTE DATO ES CLAVE.
8.  Cada instrucción debe incluir. Si no tiene eso la instrucción no vale:
    - La longitud exacta de palabras del apartado (o aproximada según lo que se diga en los pliegos). No pongas en ningún caso
    "La longitud de este subapartado no está especificada en los documentos proporcionados", propon tú uno si no existe. Esta proposición debe
    ser coherente con el apartado que es y con lo que se valora en los pliegos.
    - Una explicación clara de lo que incluirá este apartado.
    - El objetivo de contenido para que este apartado sume a obtener la excelencia en la memoria técnica.
    - Cosas que no deben faltar en el apartado.

## MEJORAS AÑADIDAS:
- Responde SIEMPRE en formato JSON válido y bien estructurado. No incluyas texto fuera del objeto JSON.
- No inventes información: solo utiliza lo que aparezca en la plantilla o en los pliegos.
- Debes mostrar conocimiento de los pliegos, no puedes asumir que el que lee las intrucciones ya posee ese conociminento.
Debes explicar todo como si el que fuera a leer las indicaciones no supiera nada del tema y deba redactar todo el contenido.
- Mantén consistencia en la numeración (ejemplo: 1, 1.1, 1.1.1). Nunca mezcles números y letras.
- Si los pliegos mencionan tablas, gráficos o anexos obligatorios, añádelos en las indicaciones como recordatorio.
- Si hay discrepancias entre plantilla y pliego, PRIORIZA SIEMPRE lo que diga el pliego.
- Valida que cada subapartado en "estructura_memoria" tenga su correspondiente bloque en "matices_desarrollo".

## EJEMPLO DE ESTRUCTURA DE SALIDA OBLIGATORIA:
{
  "estructura_memoria": [
    {
      "apartado": "1. Análisis",
      "subapartados": ["1.1. Contexto", "1.2. DAFO"]
    }
  ],
  "matices_desarrollo": [
    {
      "apartado": "1. Análisis",
      "subapartado": "1.1. Contexto",
      "indicaciones": "El subapartado debe durar 5 páginas. Este subapartado debe describir el objeto de la contratación, que es la prestación de servicios de asesoramiento, mentoría y consultoría a personas emprendedoras autónomas en Galicia. El objetivo principal es apoyar la consolidación y crecimiento de 200 proyectos empresariales de trabajadores autónomos, a través de una red de mentores especializados, para potenciar sus competencias emprendedoras, mejorar su competitividad y reducir los riesgos. Se espera que se incluyan las dos modalidades de consultoría y mentoring: una estratégica para mejorar rendimiento y rentabilidad, y otra especializada para el desarrollo de una estrategia de expansión y escalabilidad, incluyendo un análisis competitivo y de mercado..."
    },
    {
      "apartado": "1. Análisis",
      "subapartado": "1.2. DAFO",
      "indicaciones": "El subapartado debe durar 5 páginas. Este subapartado debe conseguir mostrar ..."
    }
  ]
}
"""

PROMPT_PLIEGOS = """
Eres un consultor experto en licitaciones y tu conocimiento se basa ÚNICAMENTE en los archivos que te he proporcionado.
Tu misión es analizar los Pliegos y proponer una estructura para la memoria técnica que responda a todos los requisitos y criterios de valoración.
Te daré los pliegos para hacer la memoria técnica. Revisa cuidadosamente todos los que te mando (técnicos y administrativos) para sacar la estructura obligatoria, mínima o recomendada.
Tu única tarea es convertirlo a un objeto JSON que contenga la estructura del indice y unas indicaciones para que la persona
que va a redactar la memoria técnica sepa todo lo necesario para poder redactar la memoria técnica con mayor puntuación.

## REGLAS ESTRICTAS:
1.  Tu respuesta DEBE ser un único objeto JSON válido y nada más. Sin texto introductorio ni marcadores de formato como ```json.
2.  El objeto JSON DEBE contener dos claves de nivel superior y solo dos: "estructura_memoria" y "matices_desarrollo".
3.  Para CADA apartado y subapartado, DEBES anteponer su numeración correspondiente (ej: "1. Título", "1.1. Subtítulo").
    ESTO ES OBLIGATORIO Y DEBE SER EN NÚMEROS NORMALES (1,2,3...) NADA DE LETRAS NI COSAS RARAS.
4.  La clave "estructura_memoria" contiene la lista de apartados y subapartados como un ÍNDICE.
    La lista "subapartados" SOLO debe contener los TÍTULOS numerados, NUNCA el texto de las instrucciones.
5.  Debes coger exactamente el mismo título del apartado o subapartado que existe en los Pliegos, no lo modifiques.
    Mantenlo aunque esté en otro idioma.
6.  La clave "matices_desarrollo" desglosa CADA subapartado, asociando su título numerado con las INSTRUCCIONES completas.
    NO RESUMAS. DEBES CONTAR TODO LO QUE SEPAS DE ELLO.
    Llena estas indicaciones de mucho contexto útil para que alguien sin experiencia pueda redactar la memoria.
7.  DEBES INDICAR OBLIGATORIAMENTE LA LONGITUD DE CADA SUBAPARTADO.
    NO TE LO PUEDES INVENTAR. ESTE DATO ES CLAVE.
8.  Cada instrucción debe incluir. Si no tiene eso la instrucción no vale:
    - La longitud exacta de palabras del apartado (o aproximada según lo que se diga en los Pliegos).
      No pongas en ningún caso "La longitud de este subapartado no está especificada en los documentos proporcionados";
      propone tú una si no existe. Esta proposición debe ser coherente con el apartado que es y con lo que se valora en los Pliegos.
    - Una explicación clara de lo que incluirá este apartado.
    - El objetivo de contenido para que este apartado sume a obtener la excelencia en la memoria técnica.
    - Cosas que no deben faltar en el apartado.

## MEJORAS AÑADIDAS:
- Responde SIEMPRE en formato JSON válido y bien estructurado. No incluyas texto fuera del objeto JSON.
- No inventes información: utiliza únicamente lo que aparezca en los Pliegos.
- Debes mostrar conocimiento de los Pliegos; no puedes asumir que quien lea las indicaciones ya posee ese conocimiento.
  Explica todo como si la persona que redacta no supiera nada del tema y necesitara todas las claves para escribir el contenido.
- Mantén consistencia en la numeración (ejemplo: 1, 1.1, 1.1.1). Nunca mezcles números y letras.
- Si los Pliegos mencionan tablas, gráficos o anexos obligatorios, añádelos en las indicaciones como recordatorio.
- Valida que cada subapartado en "estructura_memoria" tenga su correspondiente bloque en "matices_desarrollo".

## EJEMPLO DE ESTRUCTURA DE SALIDA OBLIGATORIA:
{
  "estructura_memoria": [
    {
      "apartado": "1. Solución Técnica",
      "subapartados": ["1.1. Metodología", "1.2. Plan de Trabajo"]
    }
  ],
  "matices_desarrollo": [
    {
      "apartado": "1. Solución Técnica",
      "subapartado": "1.1. Metodología",
      "indicaciones": "El subapartado debe durar 5 páginas. Este subapartado debe describir el objeto de la contratación, que es la prestación de servicios de asesoramiento, mentoría y consultoría a personas emprendedoras autónomas en Galicia. El objetivo principal es apoyar la consolidación y crecimiento de 200 proyectos empresariales de trabajadores autónomos, a través de una red de mentores especializados, para potenciar sus competencias emprendedoras, mejorar su competitividad y reducir los riesgos. Se espera que se incluyan las dos modalidades de consultoría y mentoring: una estratégica para mejorar rendimiento y rentabilidad, y otra especializada para el desarrollo de una estrategia de expansión y escalabilidad, incluyendo un análisis competitivo y de mercado..."
    },
    {
      "apartado": "1. Solución Técnica",
      "subapartado": "1.2. Plan de Trabajo",
      "indicaciones": "El subapartado debe durar 5 páginas. Este subapartado debe conseguir mostrar ..."
    }
  ]
}
"""


# --- FUNCIONES AUXILIARES DE BACKEND ---
def limpiar_respuesta_json(texto_sucio):
    """Limpia la respuesta de la IA para extraer un objeto JSON de forma robusta."""
    if not isinstance(texto_sucio, str):
        return ""
    # Prioriza la búsqueda de un bloque de código JSON
    match_bloque = re.search(r'```(?:json)?\s*(\{.*\})\s*```', texto_sucio, re.DOTALL)
    if match_bloque:
        return match_bloque.group(1).strip()
    # Si no lo encuentra, busca el primer objeto JSON que vea
    match_objeto = re.search(r'\{.*\}', texto_sucio, re.DOTALL)
    if match_objeto:
        return match_objeto.group(0).strip()
    return ""

# --- INICIALIZACIÓN DEL ESTADO DE LA PÁGINA (Router) ---
if 'page' not in st.session_state:
    st.session_state.page = 'landing'

# --- FUNCIONES DE NAVEGACIÓN ---
def go_to_phases():
    st.session_state.page = 'phases'
def go_to_landing():
    st.session_state.page = 'landing'
def go_to_phase1():
    st.session_state.page = 'phase_1'

def back_to_phases_and_cleanup():
    """Limpia las variables de la sesión de la Fase 1 antes de volver."""
    for key in ['generated_structure', 'word_file']:
        if key in st.session_state:
            del st.session_state[key]
    go_to_phases()


# =============================================================================
#                              PÁGINA 1: LANDING PAGE
# =============================================================================
def landing_page():
    """Muestra la pantalla de bienvenida inicial de la aplicación."""
    col1, col_center, col3 = st.columns([1, 2, 1])
    with col_center:
        st.write("") # Espacio superior
        
        # Columnas internas para centrar el logo
        inner_col1, inner_col2, inner_col3 = st.columns([1, 1, 1])
        with inner_col2:
            logo_url = "https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png"
            # Usamos markdown con <img> para evitar el icono de ampliar
            st.markdown(f'<div style="text-align: center;"><img src="{logo_url}" width="150"></div>', unsafe_allow_html=True)
        
        st.write("")
        
        # Títulos envueltos en <div> para evitar el icono de enlace
        st.markdown("<div style='text-align: center;'><h1>Asistente Inteligente para Memorias Técnicas</h1></div>", unsafe_allow_html=True)
        st.markdown("<div style='text-align: center;'><h3>Optimiza y acelera la creación de tus propuestas de licitación</h3></div>", unsafe_allow_html=True)
        
        st.write(""); st.write("") # Doble espacio antes del botón
        
        # Columnas internas para centrar y dar un ancho fijo al botón
        btn_col1, btn_col2, btn_col3 = st.columns([2, 1.5, 2])
        with btn_col2:
            st.button("¡Vamos allá!", on_click=go_to_phases, type="primary", use_container_width=True)

# =============================================================================
#                          PÁGINA 2: SELECCIÓN DE FASES
# =============================================================================
def phases_page():
    """Muestra el menú principal con las tres fases seleccionables."""
    # --- Cabecera con logo y título ---
    logo_url = "https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png"
    st.markdown(f"""
    <div style="display: flex; align-items: center; justify-content: flex-start;">
        <div style="flex: 1; margin-right: 20px;">
            <img src="{logo_url}" width="120">
        </div>
        <div style="flex: 4;">
            <h2 style="margin: 0; padding: 0;">Asistente Inteligente para Memorias Técnicas</h2>
            <p style="margin: 0; padding: 0;">Selecciona una fase para comenzar</p>
        </div>
    </div>
    """, unsafe_allow_html=True)
    st.markdown("---")
    
    # --- Columnas para las cajas de las fases ---
    col1, col2, col3 = st.columns(3, gap="large")
    with col1:
        with st.container(border=True):
            st.markdown("<h4>FASE 1: Análisis y Estructura</h4>", unsafe_allow_html=True)
            st.write("Prepara los documentos base y define el esqueleto de la memoria técnica.")
            st.write("")
            st.button("Iniciar Fase 1", on_click=go_to_phase1, type="primary", use_container_width=True, key="start_f1")
    with col2:
        with st.container(border=True):
            st.markdown("<h4>FASE 2: Redacción Asistida</h4>", unsafe_allow_html=True)
            st.write("Genera los borradores iniciales de contenido para cada apartado.")
            st.write("")
            if st.button("Iniciar Fase 2", type="primary", use_container_width=True, key="start_f2"):
                st.info("La Fase 2 estará disponible próximamente.")
    with col3:
        with st.container(border=True):
            st.markdown("<h4>FASE 3: Revisión y Exportación</h4>", unsafe_allow_html=True)
            st.write("Pule el documento final, valida requisitos y expórtalo a Word.")
            st.write("")
            if st.button("Iniciar Fase 3", type="primary", use_container_width=True, key="start_f3"):
                st.info("La Fase 3 estará disponible próximamente.")

    # --- Botón para volver a la página de inicio ---
    st.write(""); st.write("")
    _, col_back_center, _ = st.columns([2.5, 1, 2.5])
    with col_back_center:
        st.button("← Volver a Inicio", on_click=go_to_landing, use_container_width=True)

# =============================================================================
#                           PÁGINA 3: FASE 1
# =============================================================================
def phase_1_page():
    """Contiene toda la interfaz y lógica para la Fase 1."""
    # --- Cabecera de la página ---
    st.markdown("<h3>FASE 1: Análisis y Estructura</h3>", unsafe_allow_html=True)
    st.markdown("Carga los documentos base para que la IA genere y valide la estructura de la memoria técnica.")
    st.markdown("---")
    
    # --- PASO 1: Carga de Documentos ---
    with st.container(border=True):
        st.subheader("PASO 1: Carga de Documentos")
        has_template = st.radio("¿Dispones de una plantilla?", ("No", "Sí"), horizontal=True, key="template_radio")
        
        # Guardamos los archivos subidos en el estado de la sesión para que persistan
        st.session_state.uploaded_template = None
        if has_template == 'Sí':
            st.session_state.uploaded_template = st.file_uploader("Sube tu plantilla (DOCX/PDF)", type=['docx', 'pdf'], key="template_uploader")
        
        st.session_state.uploaded_pliegos = st.file_uploader("Sube los Pliegos (DOCX/PDF)", type=['docx', 'pdf'], accept_multiple_files=True, key="pliegos_uploader")

    st.write("")
    if st.button("Generar Estructura", type="primary", use_container_width=True):
        if not st.session_state.uploaded_pliegos:
            st.warning("Por favor, sube al menos un archivo de Pliegos.")
        else:
            with st.spinner("🧠 Analizando documentos y generando la estructura... Esto puede tardar unos minutos."):
                try:
                    contenido_ia = []
                    texto_plantilla = ""

                    # 1. Procesar la plantilla si existe
                    if has_template == 'Sí' and st.session_state.uploaded_template is not None:
                        prompt_a_usar = PROMPT_PLANTILLA
                        # Extraer texto de la plantilla
                        if st.session_state.uploaded_template.name.endswith('.docx'):
                            doc = docx.Document(st.session_state.uploaded_template)
                            texto_plantilla = "\n".join([p.text for p in doc.paragraphs])
                        elif st.session_state.uploaded_template.name.endswith('.pdf'):
                            reader = PdfReader(st.session_state.uploaded_template)
                            texto_plantilla = "\n".join([page.extract_text() for page in reader.pages])
                    else:
                        prompt_a_usar = PROMPT_PLIEGOS

                    # 2. Construir el contenido para la IA
                    contenido_ia.append(prompt_a_usar)
                    if texto_plantilla:
                        contenido_ia.append(texto_plantilla)
                    
                    # 3. Procesar los pliegos
                    for pliego in st.session_state.uploaded_pliegos:
                        contenido_ia.append({
                            "mime_type": pliego.type,
                            "data": pliego.getvalue()
                        })

                    # 4. Llamar a la API de Gemini
                    generation_config = genai.GenerationConfig(response_mime_type="application/json")
                    response = model.generate_content(contenido_ia, generation_config=generation_config)
                    
                    # 5. Procesar la respuesta
                    json_limpio_str = limpiar_respuesta_json(response.text)
                    if json_limpio_str:
                        informacion_estructurada = json.loads(json_limpio_str)
                        st.session_state.generated_structure = informacion_estructurada
                        st.success("¡Estructura generada con éxito!")
                    else:
                        st.error("La IA devolvió una respuesta vacía o en un formato no válido. Inténtalo de nuevo.")
                        st.text_area("Respuesta recibida de la IA:", response.text)

                except Exception as e:
                    st.error(f"Ocurrió un error al contactar con la IA: {e}")
                    if 'response' in locals() and hasattr(response, 'prompt_feedback'):
                        st.error(f"Detalles del bloqueo de la API: {response.prompt_feedback}")
    
    # --- PASO 2: VALIDACIÓN Y RESULTADO ---
    if 'generated_structure' in st.session_state:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("PASO 2: Validación de la Estructura")
            st.json(st.session_state.generated_structure.get('estructura_memoria', "No se encontró la estructura."))
            
            with st.expander("Ver detalles y matices de la estructura"):
                 st.json(st.session_state.generated_structure.get('matices_desarrollo', "No se encontraron los matices."))
            
            # La lógica para generar el Word vendría aquí...

    # --- BOTÓN DE VOLVER AL MENÚ DE FASES ---
    st.write("")
    st.markdown("---")
    _, col_back_center, _ = st.columns([2.5, 1, 2.5])
    with col_back_center:
        st.button("← Volver al Menú de Fases", on_click=back_to_phases_and_cleanup, use_container_width=True, key="back_to_menu")


# =============================================================================
#                        LÓGICA PRINCIPAL (ROUTER)
# =============================================================================
# Este bloque final decide qué función de página ejecutar basado en el estado.
if st.session_state.page == 'landing':
    landing_page()
elif st.session_state.page == 'phases':
    phases_page()
elif st.session_state.page == 'phase_1':
    phase_1_page()
