import streamlit as st
import google.generativeai as genai
import json
import re
import docx
from pypdf import PdfReader
import io
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload

# --- CONFIGURACIÓN DE GOOGLE OAUTH Y DRIVE ---
SCOPES = ['https://www.googleapis.com/auth/drive']
CLIENT_CONFIG = {
    "web": {
        "client_id": st.secrets["GOOGLE_CLIENT_ID"],
        "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
        "redirect_uris": [st.secrets["GOOGLE_REDIRECT_URI"]],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token", # Corregido de token_uri a token
    }
}
ROOT_FOLDER_NAME = "ProyectosLicitaciones"

def upload_file_to_drive(service, file_object, folder_id):
    """Sube un objeto de archivo (de st.file_uploader) a una carpeta de Drive."""
    file_metadata = {
        'name': file_object.name,
        'parents': [folder_id]
    }
    media = MediaIoBaseUpload(io.BytesIO(file_object.getvalue()),
                              mimetype=file_object.type,
                              resumable=True)
    file = service.files().create(body=file_metadata,
                                  media_body=media,
                                  fields='id').execute()
    st.toast(f"📄 Archivo '{file_object.name}' guardado en Drive.")
    return file.get('id')

def delete_file_from_drive(service, file_id):
    """Elimina un archivo de Drive por su ID."""
    try:
        service.files().delete(fileId=file_id).execute()
        return True
    except HttpError as error:
        st.error(f"No se pudo eliminar el archivo: {error}")
        return False

def find_file_by_name(service, file_name, folder_id):
    """Busca un archivo por nombre dentro de una carpeta específica."""
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    response = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
    files = response.get('files', [])
    return files[0]['id'] if files else None
    
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

PROMPT_REGENERACION = """
Actúas como un editor experto que refina una estructura JSON para una memoria técnica.
Te proporcionaré TRES elementos clave:
1.  Los documentos originales (Pliegos y/o plantilla).
2.  La estructura JSON que se generó en un primer intento.
3.  Las INSTRUCCIONES DE UN USUARIO con los cambios que desea.

Tu única tarea es generar una **NUEVA VERSIÓN MEJORADA** del objeto JSON que incorpore a la perfección los cambios solicitados por el usuario.

## REGLAS OBLIGATORIAS:
-   **MANTÉN TODAS LAS REGLAS DEL PROMPT ORIGINAL:** El formato de salida debe seguir siendo un JSON válido con las claves "estructura_memoria" y "matices_desarrollo", la numeración debe ser correcta (1, 1.1, etc.), y las indicaciones deben ser detalladas.
-   **INCORPORA EL FEEDBACK:** Lee atentamente las instrucciones del usuario y aplícalas a la nueva estructura. Por ejemplo, si pide "une los apartados 1.1 y 1.2", debes hacerlo. Si pide "el apartado 2 debe hablar sobre la experiencia del equipo", debes modificar las indicaciones de ese apartado.
-   **NO PIERDAS INFORMACIÓN:** Si el usuario solo pide cambiar el apartado 3, los apartados 1, 2, 4, etc., deben permanecer intactos en la nueva versión.
-   **SÉ PRECISO:** No inventes nuevos apartados a menos que el usuario te lo pida explícitamente. Céntrate únicamente en aplicar las correcciones solicitadas.

Genera únicamente el objeto JSON corregido. No incluyas ningún texto fuera de él.
"""

# =============================================================================
#              NUEVAS FUNCIONES: AUTENTICACIÓN Y GOOGLE DRIVE
# =============================================================================

def get_google_flow():
    """Crea y devuelve el objeto Flow de Google OAuth."""
    return Flow.from_client_config(
        client_config=CLIENT_CONFIG,
        scopes=SCOPES,
        redirect_uri=st.secrets["GOOGLE_REDIRECT_URI"]
    )

def get_credentials():
    """Obtiene las credenciales del usuario desde el session_state o inicia el flujo OAuth."""
    if 'credentials' in st.session_state and st.session_state.credentials:
        # Check if token is expired. Refresh if it is.
        creds = st.session_state.credentials
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            st.session_state.credentials = creds
        return creds

    if 'code' in st.query_params:
        try:
            flow = get_google_flow()
            flow.fetch_token(code=st.query_params['code'])
            st.session_state.credentials = flow.credentials
            st.query_params.clear()
            st.rerun() # Rerun to clear the code from URL and update the state
        except Exception as e:
            st.error(f"Error al obtener el token: {e}")
            return None
    return None

def build_drive_service(credentials):
    """Construye y devuelve el objeto de servicio de la API de Drive."""
    try:
        return build('drive', 'v3', credentials=credentials)
    except HttpError as error:
        st.error(f"No se pudo crear el servicio de Drive: {error}")
        return None

def find_or_create_folder(service, folder_name, parent_id=None):
    """Busca una carpeta por nombre. Si no la encuentra, la crea."""
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    files = response.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        file_metadata = {'name': folder_name, 'mimeType': 'application/vnd.google-apps.folder'}
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        folder = service.files().create(body=file_metadata, fields='id').execute()
        st.toast(f"Carpeta '{folder_name}' creada en tu Drive.")
        return folder.get('id')

def list_project_folders(service, root_folder_id):
    """Lista las subcarpetas (proyectos) dentro de la carpeta raíz."""
    query = f"'{root_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    return {file['name']: file['id'] for file in response.get('files', [])}
    
def get_files_in_project(service, project_folder_id):
    """Obtiene los archivos dentro de una carpeta de proyecto."""
    query = f"'{project_folder_id}' in parents and trashed = false"
    response = service.files().list(q=query, spaces='drive', fields='files(id, name, mimeType)').execute()
    return response.get('files', [])
    
def download_file_from_drive(service, file_id):
    """Descarga el contenido de un archivo de Drive y lo devuelve como BytesIO."""
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    fh.seek(0)
    return fh
    
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

# --- NAVEGACIÓN Y GESTIÓN DE ESTADO (actualizada) ---
if 'page' not in st.session_state: st.session_state.page = 'landing'
if 'credentials' not in st.session_state: st.session_state.credentials = None
if 'drive_service' not in st.session_state: st.session_state.drive_service = None
if 'selected_project' not in st.session_state: st.session_state.selected_project = None

def go_to_project_selection(): st.session_state.page = 'project_selection'
def go_to_landing(): st.session_state.page = 'landing'
def go_to_phase1(): st.session_state.page = 'phase_1'
def go_to_phase1_results(): st.session_state.page = 'phase_1_results'

def back_to_project_selection_and_cleanup():
    for key in ['generated_structure', 'word_file', 'uploaded_template', 'uploaded_pliegos', 'selected_project']:
        if key in st.session_state: del st.session_state[key]
    go_to_project_selection()


# =============================================================================
#                 PÁGINAS DE LA APLICACIÓN (NUEVA VERSIÓN)
# =============================================================================

def landing_page():
    """Pantalla de bienvenida que ahora incluye el inicio de sesión con Google."""
    col1, col_center, col3 = st.columns([1, 2, 1])
    with col_center:
        st.write("")
        st.markdown(f'<div style="text-align: center;"><img src="https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png" width="150"></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown("<div style='text-align: center;'><h1>Asistente Inteligente para Memorias Técnicas</h1></div>", unsafe_allow_html=True)
        st.markdown("<div style='text-align: center;'><h3>Optimiza y acelera la creación de tus propuestas de licitación</h3></div>", unsafe_allow_html=True)
        st.markdown("---")
        st.info("Para empezar, necesitas dar permiso a la aplicación para que gestione los proyectos en tu Google Drive.")
        
        # Generamos la URL de autenticación
        flow = get_google_flow()
        auth_url, _ = flow.authorization_url(prompt='consent')
        
        # Usamos st.link_button para una experiencia de usuario limpia
        st.link_button("🔗 Conectar con Google Drive", auth_url, use_container_width=True, type="primary")

def project_selection_page():
    """Nueva página para seleccionar o crear un proyecto en Google Drive."""
    st.markdown("<h3>Selección de Proyecto</h3>", unsafe_allow_html=True)
    st.markdown("Elige un proyecto existente de tu Google Drive o crea uno nuevo para empezar.")
    st.markdown("---")
    
    # Construimos el servicio de Drive si no existe
    if 'drive_service' not in st.session_state or not st.session_state.drive_service:
        st.session_state.drive_service = build_drive_service(st.session_state.credentials)
    
    service = st.session_state.drive_service
    # Manejo de error si el servicio no se puede crear
    if not service:
        st.error("No se pudo conectar con Google Drive. Por favor, intenta volver a la página de inicio y reconectar.")
        if st.button("← Volver a Inicio"):
            # Limpiamos las credenciales para forzar un nuevo login
            for key in ['credentials', 'drive_service']:
                if key in st.session_state:
                    del st.session_state[key]
            go_to_landing()
            st.rerun()
        return

    # Buscamos o creamos la carpeta raíz y listamos los proyectos
    with st.spinner("Accediendo a tu Google Drive..."):
        root_folder_id = find_or_create_folder(service, ROOT_FOLDER_NAME)
        projects = list_project_folders(service, root_folder_id)
    
    with st.container(border=True):
        st.subheader("1. Elige un proyecto existente")
        if not projects:
            st.info("Aún no tienes proyectos. Crea uno nuevo en el paso 2.")
        else:
            # Añadimos una opción vacía para que el usuario deba elegir activamente
            project_names = ["-- Selecciona un proyecto --"] + list(projects.keys())
            selected_name = st.selectbox("Selecciona tu proyecto:", project_names)
            
            if st.button("Cargar Proyecto Seleccionado", type="primary"):
                if selected_name != "-- Selecciona un proyecto --":
                    st.session_state.selected_project = {"name": selected_name, "id": projects[selected_name]}
                    st.toast(f"Proyecto '{selected_name}' cargado.")
                    go_to_phase1()
                    st.rerun()
                else:
                    st.warning("Por favor, selecciona un proyecto de la lista.")

    with st.container(border=True):
        st.subheader("2. O crea un nuevo proyecto")
        new_project_name = st.text_input("Nombre del nuevo proyecto (ej: Licitación Metro Madrid 2024)", key="new_project_name_input")
        if st.button("Crear y Empezar Nuevo Proyecto"):
            if not new_project_name.strip():
                st.warning("Por favor, introduce un nombre para el proyecto.")
            elif new_project_name in projects:
                st.error("Ya existe un proyecto con ese nombre. Por favor, elige otro.")
            else:
                with st.spinner(f"Creando carpeta '{new_project_name}' en tu Drive..."):
                    new_project_id = find_or_create_folder(service, new_project_name, parent_id=root_folder_id)
                    st.session_state.selected_project = {"name": new_project_name, "id": new_project_id}
                    st.success(f"¡Proyecto '{new_project_name}' creado! Ya puedes cargar los documentos.")
                    go_to_phase1()
                    st.rerun()

# =============================================================================
#           PÁGINA 4: RESULTADOS FASE 1 (VERSIÓN CON REGENERACIÓN)
# =============================================================================

# =============================================================================
#           COPIA Y PEGA ESTA FUNCIÓN EN TU CÓDIGO
# =============================================================================

def phase_1_page():
    """Página de Fase 1 con gestión completa y lógica de estado corregida."""
    if not st.session_state.get('selected_project'):
        st.warning("No se ha seleccionado ningún proyecto. Volviendo a la selección.")
        go_to_project_selection()
        st.rerun()

    project_name = st.session_state.selected_project['name']
    project_folder_id = st.session_state.selected_project['id']
    service = st.session_state.drive_service

    st.markdown(f"<h3>FASE 1: Análisis y Estructura</h3>", unsafe_allow_html=True)
    st.info(f"Estás trabajando en el proyecto: **{project_name}**")

    # Gestión de archivos (esta parte ya funciona bien)
    existing_files = get_files_in_project(service, project_folder_id)
    document_files = [f for f in existing_files if f['name'] != 'ultimo_indice.json']
    
    if document_files:
        st.success("Hemos encontrado estos archivos en tu Drive para este proyecto:")
        with st.container(border=True):
            for file in document_files:
                cols = st.columns([4, 1])
                cols[0].write(f"📄 **{file['name']}**")
                if cols[1].button("Eliminar", key=f"del_{file['id']}", type="secondary"):
                    with st.spinner(f"Eliminando '{file['name']}'..."):
                        if delete_file_from_drive(service, file['id']):
                            st.toast(f"Archivo '{file['name']}' eliminado.")
                            st.rerun()
    else:
        st.info("Este proyecto aún no tiene documentos. Sube los archivos base a continuación.")

    with st.expander("Añadir o reemplazar documentación", expanded=not document_files):
        with st.container(border=True):
            st.subheader("Subir nuevos documentos")
            new_files_uploader = st.file_uploader("Arrastra aquí los nuevos Pliegos o Plantilla", type=['docx', 'pdf'], accept_multiple_files=True, key="new_files_uploader")
            if st.button("Guardar nuevos archivos en Drive"):
                if new_files_uploader:
                    with st.spinner("Subiendo archivos a tu proyecto en Drive..."):
                        for file_obj in new_files_uploader:
                            upload_file_to_drive(service, file_obj, project_folder_id)
                        st.rerun()
                else:
                    st.warning("Por favor, selecciona al menos un archivo para subir.")

    st.markdown("---")
    st.header("Análisis y Generación de Índice")

    # --- !! COMIENZO DE LA LÓGICA CORREGIDA !! ---
    
    saved_index_id = find_file_by_name(service, "ultimo_indice.json", project_folder_id)

    # Creamos las columnas para los botones de acción
    col1, col2 = st.columns(2)

    # Botón para cargar el índice existente (si existe)
    with col1:
        if st.button("Cargar último índice generado", use_container_width=True, disabled=not saved_index_id):
            with st.spinner("Cargando índice desde Drive..."):
                index_content_bytes = download_file_from_drive(service, saved_index_id)
                index_data = json.loads(index_content_bytes.getvalue().decode('utf-8'))
                st.session_state.generated_structure = index_data
                st.session_state.uploaded_pliegos = document_files
                go_to_phase1_results()
                st.rerun()

    # Botón para analizar y generar un nuevo índice (siempre disponible si hay documentos)
    with col2:
        if st.button("Analizar Archivos y Generar Nuevo Índice", type="primary", use_container_width=True, disabled=not document_files):
            with st.spinner("Descargando archivos de Drive y analizando..."):
                try:
                    downloaded_files_for_ia = []
                    for file in document_files:
                        file_content_bytes = download_file_from_drive(service, file['id'])
                        downloaded_files_for_ia.append({"mime_type": file['mimeType'], "data": file_content_bytes.getvalue()})

                    contenido_ia = [PROMPT_PLIEGOS]
                    contenido_ia.extend(downloaded_files_for_ia)
                    
                    generation_config = genai.GenerationConfig(response_mime_type="application/json")
                    response = model.generate_content(contenido_ia, generation_config=generation_config)
                    
                    json_limpio_str = limpiar_respuesta_json(response.text)
                    if json_limpio_str:
                        informacion_estructurada = json.loads(json_limpio_str)
                        st.session_state.generated_structure = informacion_estructurada
                        st.session_state.uploaded_pliegos = document_files
                        go_to_phase1_results()
                        st.rerun()
                    else:
                        st.error("La IA devolvió una respuesta vacía o no válida.")
                except Exception as e:
                    st.error(f"Ocurrió un error: {e}")

    # --- !! FIN DE LA LÓGICA CORREGIDA !! ---

    st.write("")
    st.markdown("---")
    st.button("← Volver a Selección de Proyecto", on_click=back_to_project_selection_and_cleanup, use_container_width=True, key="back_to_projects")

# =============================================================================
#           PÁGINA 4: RESULTADOS FASE 1 (VERSIÓN FINAL CORREGIDA)
# =============================================================================

def phase_1_results_page():
    """Página para revisar los resultados de la Fase 1, con opción de regenerar."""
    st.markdown("<h3>FASE 1: Revisión de Resultados</h3>", unsafe_allow_html=True)
    st.markdown("Revisa el índice propuesto por la IA. Si es correcto, genera el guion. Si no, pide los cambios que necesites.")
    st.markdown("---")
    st.button("← Volver a Cargar Archivos", on_click=go_to_phase1)

    if 'generated_structure' not in st.session_state or not st.session_state.generated_structure:
        st.warning("No se ha generado ninguna estructura. Por favor, vuelve a la fase anterior.")
        return

    # --- FUNCIÓN CALLBACK CORREGIDA ---
    def handle_regeneration():
        feedback_text = st.session_state.feedback_area
        if not feedback_text:
            st.warning("Por favor, escribe tus indicaciones en el área de texto.")
            return

        with st.spinner("🧠 Incorporando tu feedback y regenerando la estructura..."):
            try:
                contenido_ia_regeneracion = [PROMPT_REGENERACION]
                contenido_ia_regeneracion.append("--- INSTRUCCIONES DEL USUARIO ---\n" + feedback_text)
                contenido_ia_regeneracion.append("--- ESTRUCTURA JSON ANTERIOR A CORREGIR ---\n" + json.dumps(st.session_state.generated_structure, indent=2))
                
                # --- !! COMIENZO DEL CAMBIO !! ---
                # Ahora los archivos vienen de Drive, no son UploadedFile.
                # Necesitamos descargarlos para enviarlos a la IA.
                if st.session_state.get('uploaded_pliegos'):
                    service = st.session_state.drive_service
                    for file_info in st.session_state.uploaded_pliegos:
                        # 'file_info' es ahora un diccionario {'id': ..., 'name': ..., 'mimeType': ...}
                        file_content_bytes = download_file_from_drive(service, file_info['id'])
                        contenido_ia_regeneracion.append({
                            "mime_type": file_info['mimeType'], # Usamos 'mimeType' en lugar de '.type'
                            "data": file_content_bytes.getvalue()
                        })
                # --- !! FIN DEL CAMBIO !! ---

                generation_config = genai.GenerationConfig(response_mime_type="application/json")
                response_regeneracion = model.generate_content(contenido_ia_regeneracion, generation_config=generation_config)
                json_limpio_str_regenerado = limpiar_respuesta_json(response_regeneracion.text)
                
                if json_limpio_str_regenerado:
                    nueva_estructura = json.loads(json_limpio_str_regenerado)
                    st.session_state.generated_structure = nueva_estructura
                    st.toast("¡Estructura regenerada con éxito!")
                    st.session_state.feedback_area = ""
                else:
                    st.error("La IA no devolvió una estructura válida tras la regeneración.")
            except Exception as e:
                st.error(f"Ocurrió un error durante la regeneración: {e}")

    with st.container(border=True):
        mostrar_indice_desplegable(st.session_state.generated_structure.get('estructura_memoria'))
        st.markdown("---")
        st.subheader("Validación y Siguiente Paso")
        
        st.text_area("Si necesitas cambios, indícalos aquí:", key="feedback_area", placeholder="Ej: 'Une los apartados 1.1 y 1.2 en uno solo que hable del contexto general.'")
        
        col_val_1, col_val_2 = st.columns(2)
        with col_val_1:
            st.button(
                "Regenerar con Feedback",
                on_click=handle_regeneration,
                use_container_width=True,
                disabled=not st.session_state.get("feedback_area")
            )

        with col_val_2:
            if st.button("Aceptar y Generar Guion →", type="primary", use_container_width=True):
                with st.spinner("✍️ Creando el guion estratégico..."):
                    try:
                        # --- !! TAMBIÉN NECESITAMOS CORREGIR ESTA PARTE !! ---
                        contenido_ia_preguntas = [PROMPT_PREGUNTAS_TECNICAS]
                        contenido_ia_preguntas.append("--- ESTRUCTURA VALIDADA (JSON) ---\n" + json.dumps(st.session_state.generated_structure, indent=2))
                        if st.session_state.get('uploaded_pliegos'):
                            service = st.session_state.drive_service
                            for file_info in st.session_state.uploaded_pliegos:
                                file_content_bytes = download_file_from_drive(service, file_info['id'])
                                contenido_ia_preguntas.append({
                                    "mime_type": file_info['mimeType'],
                                    "data": file_content_bytes.getvalue()
                                })

                        response_preguntas = model.generate_content(contenido_ia_preguntas)
                        
                        documento = docx.Document()
                        documento.add_heading("Guion Estratégico de Enfoque", level=0)
                        agregar_markdown_a_word(documento, response_preguntas.text)
                        
                        doc_io = io.BytesIO()
                        documento.save(doc_io)
                        doc_io.seek(0)
                        st.session_state.word_file = doc_io.getvalue()
                        
                        st.success("¡Documento Word generado!")
                    except Exception as e:
                        st.error(f"Ocurrió un error al generar el guion: {e}")

    if 'word_file' in st.session_state and st.session_state.word_file:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("Descarga del Resultado Final")
            st.download_button(
                label="📥 Descargar Guion Estratégico (.docx)",
                data=st.session_state.word_file,
                file_name="guion_estrategico.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )
# =============================================================================
#                        LÓGICA PRINCIPAL (ROUTER) - VERSIÓN CORRECTA
# =============================================================================

# Primero, SIEMPRE comprobamos si tenemos credenciales de usuario.
credentials = get_credentials()

# Si NO hay credenciales, el usuario no ha iniciado sesión.
if not credentials:
    # La única página que puede ver es la de bienvenida para que inicie sesión.
    landing_page()

# Si SÍ hay credenciales, el usuario ya ha iniciado sesión.
else:
    # Ahora que sabemos que está dentro, miramos en qué página quiere estar.
    # Si acaba de iniciar sesión, su 'page' será 'landing', así que lo llevamos
    # a la selección de proyectos.
    if st.session_state.page == 'landing' or st.session_state.page == 'project_selection':
        project_selection_page()
    
    elif st.session_state.page == 'phase_1':
        phase_1_page()
        
    elif st.session_state.page == 'phase_1_results':
        phase_1_results_page()
        
    # La página 'phases' ya no existe en este nuevo flujo, por eso no se incluye.
