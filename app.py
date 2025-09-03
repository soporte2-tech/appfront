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

PROMPT_PREGUNTAS_TECNICAS = """
Actúa como un planificador de licitación. Te quieres presentar a una licitación y debes crear un documento enfocando el contenido que aparecerá en este para que tus compañeros vean tu propuesta
y la validen y complementen. Tu objetivo será crear una propuesta de contenido ganadora basándote en lo que se pide en los pliegos para que tus compañeros sólo den el ok
y se pueda mandar el contenido a un redactor para que simplemente profundice en lo que tu has planteado. Esa "mini memoria técnica" será la que se le dará a un compañaero que se dedica a redactar.

La estructura del documento será un indice pegando la estructrua simplemente que tendrá esa memoria técnica ("Estructura de la memoria técnica") y la propuesta de los apartados ("Propuesta de contenido para Nombre Licitación").
En la propuesta de contenido por apartado debes responder a dos preguntas: qué se debe incluir en este apartado y el contenido propuesto para ese apartado.
La primera pregunta debe ser un resumen de todo lo que se pide en el pliego para ese apartado. Debes detallar qué aspectos se valoran básandote en lo que se dice en el pliego administrativo, qué información se detallará en profundida en esa parte exclusivamente , cuales son los puntos generales que tocarás en este apartado, qué aspectos se valoran básandote en lo que se dice en el pliego técnico y las puntuaciones relativas a este apartado. Esto debe estar en párrafos y en bullet points.
La segunda pregunta debe ser tu propuesta de contenido para responder ese apartado. Esa propuesta debe enfocarse a explicar la propuesta que tu crees más óptima para obtener la mayor puntuación. Debes detallarla ampliamente de una manera esquemática enfocando en el contenido (no en la explicación) de eso que propones. Esa propuesta será analizada por tus compañeros para mejorar el enfoque.
Para responder a esa segunda pregunta, deberás crear preguntas que desengranen el contenido general de ese apartado en preguntas más pequeñas para que tus compañeros puedan ir ajustando y mejorando cada fase.
Por ejemplo, si se te habla de metodología: primero deberás leerte el pliego administrativo y ver que estructura debe tener una metodología y segundo leerte el pliego técnico y ver el contenido que debe tener. En ese caso localizaste (ampliando lo que se dice en los pliegios) que la metodología debe hablar sobre los principios que enmarcan esa propuesta, la teoría de la metodología, las actividades y el cronograma.
Con esos puntos localizados deberías escribir un párrafo amplio profundizando en esa primera pregunta de resumen de todo lo que se pide en el pliego para ese apartado y después escribir la desengranción de preguntas por apartado y dar una respuesta detallada sobre el contenido o el enfoque que deberá tener ese contenido para definir perfectamente la metodología final de esa memoria técnica.
Debe ser propuestas muy precisas, es decir, deben de ser textos que expliquen muy bien todas las actividades, metodologías y conceptos relacionados con el enfoque de una manera que la persona que lea este documento solo se dedique a matizar y a mejorar los contenidos.

Para cada apartado y subapartado del índice, desarrollarás el contenido siguiendo OBLIGATORIAMENTE estas 6 REGLAS DE ORO:

    1.  **TONO PROFESIONAL E IMPERSONAL:** Redacta siempre en tercera persona. Elimina CUALQUIER referencia personal (ej. "nosotros", "nuestra propuesta"). Usa formulaciones como "El servicio se articula en...", "La metodología implementada será...".

    2.  **CONCRECIÓN ABSOLUTA (EL "CÓMO"):** Cada afirmación general DEBE ser respaldada por una acción concreta, una herramienta específica (ej. CRM HubSpot for Startups, WhatsApp Business API), una métrica medible o un entregable tangible. Evita las frases vacías.

    3.  **ENFOQUE EN EL USUARIO FINAL (BUYER PERSONA):** Orienta todo el contenido a resolver los problemas del buyer persona objetivo de esa licitación. Demuestra un profundo conocimiento de su perfil, retos (burocracia, aislamiento) y objetivos (viabilidad, crecimiento).

    4.  **LONGITUD CONTROLADA POR PALABRAS:** El desarrollo completo de la "Propuesta de Contenido" debe tener una extensión total de entre 6.000 y 8.000 palabras. Distribuye el contenido de forma equilibrada entre los apartados para alcanzar este objetivo sin generar texto de relleno.

    5.  **PROPUESTA DE VALOR ESTRATÉGICA:** Enfócate en los resultados y el valor añadido. En esta memoria no busques adornar las ideas, centrate en mostrar las ideas de una manera fácil de ver y clara.

    6.  **ALINEACIÓN TOTAL CON EL PLIEGO (PPT):** La justificación de cada acción debe ser su alineación con los requisitos del Pliego y el valor que aporta para obtener la máxima puntuación.

    Para el desarrollo de cada apartado en la PARTE 2, usa este formato:
    -   **"Qué se debe incluir en este apartado (Análisis del Pliego)":** Resume los requisitos del PPT, criterios de evaluación y puntuación.
    -   **"Contenido Propuesto para el Apartado":** Aplica aquí las 6 Reglas de Oro, desarrollando la propuesta de forma concreta, estratégica y detallada.

En este documento solo deberán aparecer los apartados angulares de la propuesta. Se omitirán los de presentación, los de introducción y los que no vayan directamente asociados a definir lo principal de la licitación. Normalmente lo prinicipal es la metodología, las actividades que se van a hacer y la planificación con su cronograma correspondiente.

Te proporcionaré DOS elementos clave:
1.  El texto completo de los documentos base (Pliegos y/o plantilla).
2.  La estructura que se ha generado en el mensaje anterior con los apartados y las anotaciones.
"""

# --- FUNCIONES AUXILIARES DE BACKEND ---
def limpiar_respuesta_json(texto_sucio):
    if not isinstance(texto_sucio, str): return ""
    match_bloque = re.search(r'```(?:json)?\s*(\{.*\})\s*```', texto_sucio, re.DOTALL)
    if match_bloque: return match_bloque.group(1).strip()
    match_objeto = re.search(r'\{.*\}', texto_sucio, re.DOTALL)
    if match_objeto: return match_objeto.group(0).strip()
    return ""

def agregar_markdown_a_word(documento, texto_markdown):
    patron_encabezado = re.compile(r'^(#+)\s+(.*)')
    patron_lista_numerada = re.compile(r'^\s*\d+\.\s+')
    patron_lista_viñeta = re.compile(r'^\s*[\*\-]\s+')
    def procesar_linea_con_negritas(parrafo, texto):
        partes = re.split(r'(\*\*.*?\*\*)', texto)
        for parte in partes:
            if parte.startswith('**') and parte.endswith('**'): parrafo.add_run(parte[2:-2]).bold = True
            elif parte: parrafo.add_run(parte)
    for linea in texto_markdown.split('\n'):
        linea_limpia = linea.strip()
        if not linea_limpia: continue
        match_encabezado = patron_encabezado.match(linea_limpia)
        if match_encabezado:
            documento.add_heading(match_encabezado.group(2).strip(), level=min(len(match_encabezado.group(1)), 4))
            continue
        if patron_lista_numerada.match(linea_limpia):
            p = documento.add_paragraph(style='List Number')
            procesar_linea_con_negritas(p, patron_lista_numerada.sub('', linea_limpia))
        elif patron_lista_viñeta.match(linea_limpia):
            p = documento.add_paragraph(style='List Bullet')
            procesar_linea_con_negritas(p, patron_lista_viñeta.sub('', linea_limpia))
        else:
            p = documento.add_paragraph()
            procesar_linea_con_negritas(p, linea_limpia)

def mostrar_indice_desplegable(estructura_memoria):
    if not estructura_memoria:
        st.warning("No se encontró una estructura de memoria para mostrar.")
        return
    st.subheader("Índice Propuesto")
    for seccion in estructura_memoria:
        apartado_titulo = seccion.get("apartado", "Apartado sin título")
        subapartados = seccion.get("subapartados", [])
        with st.expander(f"**{apartado_titulo}**"):
            if subapartados:
                for sub in subapartados: st.markdown(f"- {sub}")
            else: st.markdown("_Este apartado no tiene subapartados definidos._")

# --- NAVEGACIÓN Y GESTIÓN DE ESTADO ---
if 'page' not in st.session_state: st.session_state.page = 'landing'

def go_to_phases(): st.session_state.page = 'phases'
def go_to_landing(): st.session_state.page = 'landing'
def go_to_phase1(): st.session_state.page = 'phase_1'
def go_to_phase1_results(): st.session_state.page = 'phase_1_results'

def back_to_phases_and_cleanup():
    for key in ['generated_structure', 'word_file', 'uploaded_template', 'uploaded_pliegos']:
        if key in st.session_state: del st.session_state[key]
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
#                           PÁGINA 3: FASE 1 (CARGA)
# =============================================================================
def phase_1_page():
    """Página para la carga de documentos de la Fase 1."""
    st.markdown("<h3>FASE 1: Análisis y Estructura</h3>", unsafe_allow_html=True)
    st.markdown("Carga los documentos base para que la IA genere y valide la estructura de la memoria técnica.")
    st.markdown("---")
    
    # --- PASO 1: CARGA DE DOCUMENTOS ---
    with st.container(border=True):
        st.subheader("PASO 1: Carga de Documentos")
        has_template = st.radio("¿Dispones de una plantilla?", ("No", "Sí"), horizontal=True, key="template_radio")
        
        if 'uploaded_template' not in st.session_state: st.session_state.uploaded_template = None
        if has_template == 'Sí':
            st.session_state.uploaded_template = st.file_uploader("Sube tu plantilla (DOCX/PDF)", type=['docx', 'pdf'], key="template_uploader")
        
        if 'uploaded_pliegos' not in st.session_state: st.session_state.uploaded_pliegos = None
        st.session_state.uploaded_pliegos = st.file_uploader("Sube los Pliegos (DOCX/PDF)", type=['docx', 'pdf'], accept_multiple_files=True, key="pliegos_uploader")

    st.write("")
    if st.button("Generar Estructura", type="primary", use_container_width=True):
        if not st.session_state.uploaded_pliegos:
            st.warning("Por favor, sube al menos un archivo de Pliegos.")
        else:
            with st.spinner("🧠 Analizando documentos y generando la estructura..."):
                try:
                    # --- Tu lógica de backend para llamar a la IA (sin cambios) ---
                    contenido_ia = []
                    texto_plantilla = ""
                    if has_template == 'Sí' and st.session_state.uploaded_template is not None:
                        prompt_a_usar = PROMPT_PLANTILLA
                        if st.session_state.uploaded_template.name.endswith('.docx'):
                            doc = docx.Document(st.session_state.uploaded_template)
                            texto_plantilla = "\n".join([p.text for p in doc.paragraphs])
                        elif st.session_state.uploaded_template.name.endswith('.pdf'):
                            reader = PdfReader(st.session_state.uploaded_template)
                            texto_plantilla = "\n".join([page.extract_text() for page in reader.pages])
                    else:
                        prompt_a_usar = PROMPT_PLIEGOS

                    contenido_ia.append(prompt_a_usar)
                    if texto_plantilla:
                        contenido_ia.append(texto_plantilla)
                    
                    for pliego in st.session_state.uploaded_pliegos:
                        contenido_ia.append({"mime_type": pliego.type, "data": pliego.getvalue()})

                    generation_config = genai.GenerationConfig(response_mime_type="application/json")
                    response = model.generate_content(contenido_ia, generation_config=generation_config)
                    
                    json_limpio_str = limpiar_respuesta_json(response.text)
                    if json_limpio_str:
                        informacion_estructurada = json.loads(json_limpio_str)
                        st.session_state.generated_structure = informacion_estructurada
                        # --- CAMBIO CLAVE: NAVEGACIÓN AUTOMÁTICA ---
                        go_to_phase1_results()
                        st.rerun() # Forza a Streamlit a recargar el script y mostrar la nueva página
                    else:
                        st.error("La IA devolvió una respuesta vacía o en un formato no válido.")

                except Exception as e:
                    st.error(f"Ocurrió un error al contactar con la IA: {e}")

    # --- BOTÓN DE VOLVER AL MENÚ DE FASES ---
    st.write("")
    st.markdown("---")
    _, col_back_center, _ = st.columns([2.5, 1, 2.5])
    with col_back_center:
        st.button("← Volver al Menú de Fases", on_click=back_to_phases_and_cleanup, use_container_width=True, key="back_to_menu")

# =============================================================================
#                       PÁGINA 4: RESULTADOS FASE 1
# =============================================================================
def phase_1_results_page():
    st.markdown("<h3>FASE 1: Revisión de Resultados</h3>", unsafe_allow_html=True)
    st.markdown("Revisa el índice propuesto por la IA. Si es correcto, genera el guion estratégico.")
    st.markdown("---")
    st.button("← Volver a Cargar Archivos", on_click=go_to_phase1)

    with st.container(border=True):
        mostrar_indice_desplegable(st.session_state.generated_structure.get('estructura_memoria'))
        st.markdown("---")
        st.subheader("Validación y Siguiente Paso")
        feedback = st.text_area("Si necesitas cambios, indícalos aquí:", key="feedback_area")
        col_val_1, col_val_2 = st.columns(2)
        with col_val_1:
            if st.button("Regenerar con Feedback", use_container_width=True, disabled=not feedback):
                st.info("Funcionalidad de regeneración pendiente.")
        with col_val_2:
            if st.button("Aceptar y Generar Guion →", type="primary", use_container_width=True):
                with st.spinner("✍️ Creando el guion estratégico... Este proceso puede tardar varios minutos."):
                    try:
                        contenido_ia_preguntas = [PROMPT_PREGUNTAS_TECNICAS]
                        contenido_ia_preguntas.append("--- ESTRUCTURA VALIDADA (JSON) ---\n" + json.dumps(st.session_state.generated_structure, indent=2))
                        for pliego in st.session_state.uploaded_pliegos:
                            contenido_ia_preguntas.append({"mime_type": pliego.type, "data": pliego.getvalue()})
                        if st.session_state.get('uploaded_template'):
                            contenido_ia_preguntas.append({"mime_type": st.session_state.uploaded_template.type, "data": st.session_state.uploaded_template.getvalue()})

                        response_preguntas = model.generate_content(contenido_ia_preguntas)
                        
                        documento = docx.Document()
                        documento.add_heading("Guion Estratégico de Enfoque", level=0)
                        agregar_markdown_a_word(documento, response_preguntas.text)
                        
                        doc_io = io.BytesIO()
                        documento.save(doc_io)
                        doc_io.seek(0)
                        st.session_state.word_file = doc_io.getvalue()
                        
                        st.success("¡Documento Word generado! Ya puedes descargarlo a continuación.")
                    except Exception as e:
                        st.error(f"Ocurrió un error al generar el guion: {e}")
                        if 'response_preguntas' in locals() and hasattr(response_preguntas, 'prompt_feedback'): st.error(f"Detalles del bloqueo: {response_preguntas.prompt_feedback}")

    if 'word_file' in st.session_state:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("Descarga del Resultado Final")
            st.download_button(label="📥 Descargar Guion Estratégico (.docx)", data=st.session_state.word_file, file_name="guion_estrategico.docx", mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document", use_container_width=True)

# =============================================================================
#                        LÓGICA PRINCIPAL (ROUTER)
# =============================================================================
if st.session_state.page == 'landing': landing_page()
elif st.session_state.page == 'phases': phases_page()
elif st.session_state.page == 'phase_1': phase_1_page()
elif st.session_state.page == 'phase_1_results': phase_1_results_page()
