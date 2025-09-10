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
from google.auth.transport.requests import Request
from googleapiclient.http import MediaIoBaseUpload, MediaIoBaseDownload
import base64
from email.mime.text import MIMEText
# Y asegúrate también de que estas de antes siguen ahí:
import time
import httplib2
import google_auth_httplib2 
import os      # <-- AÑADE ESTA LÍNEA
import imgkit  # <-- Y AÑADE ESTA LÍNEA TAMBIÉN

# =============================================================================
#           BLOQUE COMPLETO DE CONFIGURACIÓN Y FUNCIONES DE DRIVE
# =============================================================================
st.set_page_config(layout="wide")

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/userinfo.profile',
    'https://www.googleapis.com/auth/userinfo.email',
    'openid',
    'https://www.googleapis.com/auth/documents.readonly' # <-- NUEVO PERMISO
]
CLIENT_CONFIG = {
    "web": {
        "client_id": st.secrets["GOOGLE_CLIENT_ID"],
        "client_secret": st.secrets["GOOGLE_CLIENT_SECRET"],
        "redirect_uris": [st.secrets["GOOGLE_REDIRECT_URI"]],
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
}
ROOT_FOLDER_NAME = "ProyectosLicitaciones"


# =============================================================================
#           BLOQUE DE FUNCIONES DE DRIVE DEFINITIVO (CON LAS 6 FUNCIONES)
# =============================================================================

def find_or_create_folder(service, folder_name, parent_id=None, retries=3):
    """Busca una carpeta. Si no la encuentra, la crea. Incluye reintentos para errores de red."""
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    for attempt in range(retries):
        try:
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
        except (TimeoutError, httplib2.ServerNotFoundError) as e:
            if attempt < retries - 1:
                st.toast(f"⏳ Error de red con Drive ({type(e).__name__}). Reintentando... ({attempt + 2}/{retries})")
                time.sleep(2 ** attempt)
            else:
                st.error("❌ No se pudo conectar con Google Drive. Por favor, refresca la página.")
                raise
        except Exception as e:
            st.error(f"Ocurrió un error inesperado con Google Drive: {e}")
            raise

def upload_file_to_drive(service, file_object, folder_id, retries=3):
    """Sube un objeto de archivo a una carpeta de Drive, con reintentos."""
    for attempt in range(retries):
        try:
            file_metadata = {'name': file_object.name, 'parents': [folder_id]}
            file_object.seek(0) 
            media = MediaIoBaseUpload(file_object, mimetype=file_object.type, resumable=True)
            file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
            st.toast(f"📄 Archivo '{file_object.name}' guardado en Drive.")
            return file.get('id')
        except (TimeoutError, httplib2.ServerNotFoundError) as e:
            if attempt < retries - 1:
                st.toast(f"⏳ Error de red al subir archivo. Reintentando... ({attempt + 2}/{retries})")
                time.sleep(2 ** attempt)
            else:
                st.error(f"❌ No se pudo subir el archivo '{file_object.name}' tras varios intentos.")
                raise
        except Exception as e:
            st.error(f"Error inesperado al subir archivo: {e}")
            raise

def delete_file_from_drive(service, file_id, retries=3):
    """Elimina un archivo de Drive por su ID, con reintentos."""
    for attempt in range(retries):
        try:
            service.files().delete(fileId=file_id).execute()
            return True
        except (TimeoutError, httplib2.ServerNotFoundError) as e:
            if attempt < retries - 1:
                st.toast(f"⏳ Error de red al eliminar. Reintentando... ({attempt + 2}/{retries})")
                time.sleep(2 ** attempt)
            else:
                st.error(f"❌ No se pudo eliminar el archivo/carpeta tras varios intentos.")
                return False
        except HttpError as error:
            st.error(f"No se pudo eliminar el archivo: {error}")
            return False

def find_file_by_name(service, file_name, folder_id, retries=3):
    """Busca un archivo por nombre dentro de una carpeta, con reintentos."""
    query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
    for attempt in range(retries):
        try:
            response = service.files().list(q=query, spaces='drive', fields='files(id)').execute()
            files = response.get('files', [])
            return files[0]['id'] if files else None
        except (TimeoutError, httplib2.ServerNotFoundError) as e:
            if attempt < retries - 1:
                st.toast(f"⏳ Error de red buscando archivo. Reintentando... ({attempt + 2}/{retries})")
                time.sleep(2 ** attempt)
            else:
                st.error(f"❌ No se pudo buscar el archivo '{file_name}' tras varios intentos.")
                raise
        except Exception as e:
            st.error(f"Error inesperado al buscar archivo: {e}")
            raise
    
def download_file_from_drive(service, file_id, retries=3):
    """Descarga el contenido de un archivo de Drive, con reintentos."""
    for attempt in range(retries):
        try:
            request = service.files().get_media(fileId=file_id)
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while done is False:
                status, done = downloader.next_chunk()
            fh.seek(0)
            return fh
        except (TimeoutError, httplib2.ServerNotFoundError) as e:
            if attempt < retries - 1:
                st.toast(f"⏳ Error de red al descargar. Reintentando... ({attempt + 2}/{retries})")
                time.sleep(2 ** attempt)
            else:
                st.error(f"❌ No se pudo descargar el archivo tras varios intentos.")
                raise
        except Exception as e:
            st.error(f"Error inesperado al descargar: {e}")
            raise

# --- ESTA ES LA FUNCIÓN QUE FALTABA ---
def list_project_folders(service, root_folder_id, retries=3):
    """Lista las subcarpetas (proyectos) dentro de la carpeta raíz, con reintentos."""
    query = f"'{root_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    for attempt in range(retries):
        try:
            response = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
            return {file['name']: file['id'] for file in response.get('files', [])}
        except (TimeoutError, httplib2.ServerNotFoundError) as e:
            if attempt < retries - 1:
                st.toast(f"⏳ Error de red listando proyectos. Reintentando... ({attempt + 2}/{retries})")
                time.sleep(2 ** attempt)
            else:
                st.error("❌ No se pudieron listar los proyectos de Drive tras varios intentos.")
                return {} # Devolvemos un diccionario vacío en caso de fallo final
        except Exception as e:
            st.error(f"Error inesperado al listar proyectos: {e}")
            return {}

def sync_guiones_folders_with_index(service, project_folder_id, new_index_structure):
    """
    Compara las carpetas de guiones existentes en Drive con el nuevo índice.
    Elimina las carpetas que ya no corresponden a ningún subapartado.
    """
    st.toast("🔄 Sincronizando carpetas de guiones con el nuevo índice...")
    
    # 1. Obtener la lista de nombres de carpetas ESPERADOS según el nuevo índice
    expected_folders = set()
    if 'estructura_memoria' in new_index_structure:
        for seccion in new_index_structure.get('estructura_memoria', []):
            for subapartado_titulo in seccion.get('subapartados', []):
                # Usamos la misma lógica que en la fase 2 para crear nombres de carpeta
                nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", subapartado_titulo)
                expected_folders.add(nombre_limpio)
    
    if not expected_folders:
        st.warning("El nuevo índice no contiene subapartados. No se realizó ninguna limpieza.")
        return 0

    # 2. Obtener la lista de carpetas de guiones EXISTENTES en Google Drive
    guiones_main_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
    # Reutilizamos la función que lista subcarpetas
    existing_folders_map = list_project_folders(service, guiones_main_folder_id) # Devuelve {name: id}

    # 3. Comparar y eliminar las obsoletas
    deleted_count = 0
    folders_to_delete = []
    for folder_name, folder_id in existing_folders_map.items():
        if folder_name not in expected_folders:
            folders_to_delete.append((folder_name, folder_id))

    if not folders_to_delete:
        st.toast("✅ Las carpetas de guiones ya estaban sincronizadas.")
        return 0
        
    with st.spinner(f"Eliminando {len(folders_to_delete)} carpetas de guiones obsoletas..."):
        for folder_name, folder_id in folders_to_delete:
            if delete_file_from_drive(service, folder_id):
                st.toast(f"🗑️ Carpeta obsoleta eliminada: '{folder_name}'")
                deleted_count += 1
            else:
                st.warning(f"No se pudo eliminar la carpeta obsoleta: '{folder_name}'")
    
    return deleted_count
# --- PROMPTS DE LA IA ---
# He copiado tus prompts directamente desde tu código de Colab.
PROMPT_CONSULTOR_REVISION = """
Actúas como un Consultor de Licitaciones Senior y redactor técnico experto, el mejor del mercado. Tu tarea es analizar el feedback de un cliente sobre un borrador y generar una versión mejorada que no solo corrija, sino que también proponga soluciones de alto valor.

Te proporcionaré TRES elementos:
1.  **BORRADOR ORIGINAL:** La primera versión del guion.
2.  **FEEDBACK DEL CLIENTE:** El texto del mismo documento, pero con las correcciones, ediciones o comentarios del cliente.
3.  **CONTEXTO DE LA LICITACIÓN:** Los pliegos originales para asegurar la coherencia estratégica.

Tu misión es generar una **NUEVA VERSIÓN ESTRATÉGICAMENTE SUPERIOR** del texto en formato Markdown.

## REGLAS DE ORO PARA LA REVISIÓN:
1.  **INCORPORA CORRECCIONES DIRECTAS:** Si el cliente corrige un dato o una frase, aplica ese cambio directamente. Su palabra es ley en cuanto a hechos o estilo.
2.  **SÉ UN CONSULTOR PROACTIVO (¡CLAVE!):** Si el cliente expresa una duda o un descontento (ej: "la metodología Scrum no me gusta" o "¿podemos enfocar esto de otra manera?"), NO te limites a eliminar lo antiguo. DEBES:
    a) **Analizar el problema:** Entiende por qué no le gusta la propuesta actual.
    b) **Proponer una alternativa mejor:** Basándote en tu conocimiento como licitador senior y en los pliegos, sugiere una nueva metodología, un enfoque diferente o una solución alternativa que sea más potente y tenga más probabilidades de ganar.
    c) **Justificar tu propuesta:** Explica brevemente por qué tu nueva propuesta es mejor en el contexto de esta licitación.
3.  **MANTÉN LO QUE FUNCIONA:** Conserva intactas las partes del borrador original que no recibieron feedback negativo.
4.  **FUSIÓN INTELIGENTE:** Integra todos los cambios (tanto las correcciones directas como tus nuevas propuestas) de forma natural y coherente, manteniendo el tono profesional y las reglas de oro de la redacción original.
5.  **RESPUESTA DIRECTA Y LIMPIA:** Genera únicamente el texto mejorado en Markdown. No expliques los cambios que has hecho ni uses frases introductorias.

## EJEMPLO DE ACTUACIÓN:
-   **Feedback del cliente:** "En la sección de metodología, no me convence Scrum para este proyecto, es demasiado rígido. Proponme otra cosa."
-   **Tu acción:** No solo borras Scrum. Lo reemplazas con una sección detallada sobre Kanban o Lean, explicando por qué es más flexible y adecuado para los objetivos descritos en los pliegos.

Tu objetivo final es que el cliente, al leer la nueva versión, piense: "No solo ha hecho lo que le he pedido, sino que me ha dado una solución mejor en la que no había pensado".
"""

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
Eres un consultor experto en licitaciones públicas, especializado en estructurar memorias técnicas para maximizar la puntuación. Tu conocimiento se basa ÚNICAMENTE en los archivos que te he proporcionado.

Tu misión es analizar los Pliegos (administrativos y técnicos) para diseñar un **índice jerárquico y estratégico** para la memoria técnica. Este índice debe responder perfectamente a todos los requisitos y, fundamentalmente, a los criterios de valoración.

## METODOLOGÍA DE ANÁLISIS OBLIGATORIA:
Para crear la estructura, seguirás estos pasos:
1.  **IDENTIFICAR APARTADOS PRINCIPALES:** Busca en los pliegos la sección de "CRITERIOS DE VALORACIÓN SUJETOS A JUICIO DE VALOR" (o similar). CADA UNO de estos criterios principales (ej: "Calidad de la Metodología", "Plan de Trabajo", "Equipo Adscrito") se convertirá en un **apartado de nivel superior** en tu estructura (ej: "1. Metodología Propuesta", "2. Plan de Trabajo", etc.).
2.  **AGRUPAR SUBAPARTADOS LÓGICAMENTE:** Para cada apartado principal que has identificado, busca en TODO el pliego (especialmente en el Pliego de Prescripciones Técnicas - PPT) los requisitos, detalles y especificaciones que correspondan a ese criterio. Estos detalles se convertirán en los **subapartados** (ej: "1.1. Fases de la Metodología", "1.2. Herramientas a utilizar").
3.  **GARANTIZAR COBERTURA TOTAL:** Asegúrate de que cada requisito relevante del pliego tenga su lugar en la estructura. Si un requisito no encaja claramente en un criterio de valoración, crea un apartado lógico para él (como "Mejoras Adicionales").

## REGLAS ESTRICTAS DE SALIDA:
0.  **LA JERARQUÍA ES CLAVE:** El objetivo es un índice bien estructurado con varios apartados principales (1, 2, 3...) y sus correspondientes subapartados (1.1, 1.2, 2.1...). **Está prohibido generar una estructura con un único apartado principal y una larga lista de subapartados.**
1.  **RESPUESTA EXCLUSIVAMENTE EN JSON:** Tu única salida debe ser un objeto JSON válido. No incluyas texto introductorio, explicaciones ni marcadores como ```json.
2.  **CLAVES PRINCIPALES FIJAS:** El objeto JSON DEBE contener dos claves de nivel superior y solo dos: "estructura_memoria" y "matices_desarrollo".
3.  **NUMERACIÓN JERÁRQUICA:** Para CADA apartado y subapartado, DEBES anteponer su numeración correspondiente (ej: "1. Título", "1.1. Subtítulo", "1.2. Subtítulo", "2. Otro Título"). Usa solo números, nunca letras.
4.  **TÍTULOS FIELES AL PLIEGO:** Utiliza los títulos y la terminología exactos de los Pliegos para los apartados y subapartados. Si el pliego no proporciona un título claro para un grupo de requisitos, puedes crear un título descriptivo y lógico.
5.  **CONTENIDO DE "matices_desarrollo":** Esta sección debe ser exhaustiva. Para CADA subapartado, las "indicaciones" deben incluir OBLIGATORIAMENTE:
    -   **Puntuación y Relevancia:** Menciona explícitamente cuántos puntos vale el criterio principal asociado y por qué este subapartado es crucial para obtenerlos.
    -   **Longitud Estimada:** Propón una longitud en páginas o palabras. Si el pliego no lo especifica, haz una estimación razonable basada en la importancia y puntuación del apartado. NUNCA digas que no está especificado.
    -   **Contenido Detallado:** Explica qué información específica del pliego se debe desarrollar aquí.
    -   **Objetivo Estratégico:** Describe qué se debe demostrar al evaluador para conseguir la máxima puntuación (ej: "El objetivo es demostrar un dominio completo del proceso X y cómo nuestra metodología mitiga los riesgos Y").
    -   **Elementos Clave a Incluir:** Lista de puntos, tablas, gráficos o datos que no pueden faltar.

## EJEMPLO DE ESTRUCTURA DE SALIDA OBLIGATORIA (CON BUENA JERARQUÍA):
{
  "estructura_memoria": [
    {
      "apartado": "1. Solución Técnica y Metodología",
      "subapartados": ["1.1. Metodología de Trabajo", "1.2. Plan de Trabajo", "1.3. Equipo de Trabajo"]
    },
    {
      "apartado": "2. Calidad del Servicio y Mejoras",
      "subapartados": ["2.1. Actuaciones adicionales", "2.2. Políticas empresariales"]
    }
  ],
  "matices_desarrollo": [
    {
      "apartado": "1. Solución Técnica y Metodología",
      "subapartado": "1.1. Metodología de Trabajo",
      "indicaciones": "Este subapartado es clave para el criterio 'Calidad de la Propuesta Técnica', valorado con 40 puntos. Se recomienda una extensión de 8 páginas. Aquí se debe detallar la metodología agile-scrum que se implementará, describiendo las fases del proyecto: Sprint 0 (Setup), Sprints de Desarrollo (ciclos de 2 semanas) y Sprint de Cierre. Es fundamental incluir un diagrama de flujo del proceso y explicar cómo las ceremonias (Daily, Planning, Review, Retro) garantizan la comunicación y la adaptación continua. El objetivo es demostrar que nuestra metodología es robusta, flexible y minimiza los riesgos de desviación del proyecto..."
    },
    {
      "apartado": "2. Calidad del Servicio y Mejoras",
      "subapartado": "2.1. Actuaciones adicionales",
      "indicaciones": "Este subapartado responde al criterio de 'Mejoras Propuestas', valorado con 15 puntos. Se recomienda una extensión de 3 páginas. Se debe proponer la implantación de un dashboard de seguimiento en tiempo real con PowerBI sin coste adicional para el cliente. Hay que detallar qué KPIs se mostrarán (ej: avance de tareas, presupuesto consumido, incidencias abiertas/cerradas) y qué beneficios aporta en términos de transparencia y toma de decisiones. No debe faltar una captura de pantalla de un dashboard de ejemplo..."
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

PROMPT_PREGUNTAS_TECNICAS_INDIVIDUAL = """
Actúa como un planificador de licitación. Te quieres presentar a una licitación y debes crear un documento enfocando el contenido que aparecerá en este para que tus compañeros vean tu propuesta
y la validen y complementen. Tu objetivo será crear una propuesta de contenido ganadora basándote en lo que se pide en los pliegos para que tus compañeros sólo den el ok
y se pueda mandar el contenido a un redactor para que simplemente profundice en lo que tu has planteado. Esa "mini memoria técnica" será la que se le dará a un compañaero que se dedica a redactar.

!! Tu respuesta debe centrarse EXCLUSIVAMENTE en el apartado proporcionado. No incluyas un índice general ni el título "Propuesta de contenido para...". Empieza directamente con el desarrollo del apartado. !!
Para el apartado proporcionado, debes responder a dos preguntas: "qué se debe incluir en este apartado" y "el contenido propuesto para ese apartado".

La primera pregunta ("Qué se debe incluir...") debe ser un resumen de todo lo que se pide en el pliego para ese apartado. Debes detallar qué aspectos se valoran, qué información se detallará en profundidad, cuáles son los puntos generales que tocarás, qué aspectos se valoran según el pliego técnico y las puntuaciones relativas. Usa párrafos y bullet points.

La segunda pregunta ("Contenido propuesto...") debe ser tu propuesta de contenido para obtener la mayor puntuación. Detállala ampliamente de manera esquemática, enfocando en el contenido (no en la explicación). Desgrana el contenido general en preguntas más pequeñas y da respuestas detalladas que expliquen muy bien las actividades, metodologías y conceptos.

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

Te proporcionaré TRES elementos clave:
1.  El texto completo de los documentos base (Pliegos).
2.  Las indicaciones para el apartado específico que debes desarrollar (extraídas de un JSON de estructura).
3.  Documentación de apoyo adicional (opcional) que el usuario haya subido para este apartado.
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

PROMPT_DESARROLLO = """
    Actúa como un consultor experto redactando una memoria técnica para una licitación pública. Debes hacer una memoria técnica seria, pero amena de leer con algunos (sin excederse) elementos gráficos, tablas y listas que hagan la lectura más fácil y profesional.
    Tu tarea es crear los prompts que darán forma al texto de este subapartado. Es por ello que debes que tener en cuenta que estas indicaciones
    deben tener todo tipo de detalles para que otra IA sea capaz de con ese contexto recibirlo y generar el contenido final de la mejor manera posible.
    Debes ser un buen guía para que la IA no cometa errores de escritura y realice un buen trabajo.
    Debes seguir estos pasos para hacer estos prompts:


    1. Tu objetivo es crear UN SOLO prompt para el subapartado completo que se te ha asignado. No lo dividas en múltiples prompts. Define un rango de palabras coherente para que el redactor final sepa la longitud esperada.
    2. Dentro de ese único prompt, detalla todo el contexto y los puntos clave que el redactor debe cubrir, basándote en la información de los Pliegos y los guiones. Sé exhaustivo en las instrucciones.
    3. Una vez ya sabes cuántas palabras tendrán los prompts, complementa el contenido de cada prompt con el CONTEXTO ADICIONAL que te proporciono. Este contexto incluye el guion borrador ya creado y la documentación de apoyo. Úsalo como base principal para dar forma a la propuesta de contenido.Intenta siempre usar un contenidio de la empresa real, pero si en la documentación o el mensaje inicial que se te dió no hay nada para llegar a ese objetivo.
    4. Añade en los prompts siempre la libertad para que referencien algo mencionado antes (menos de los Pliegos en exceso, que queda cantoso), mostrando así una coherencia y un humanismo. Menciona también que debe parecer humana la redacción. El objetivo es que sea fácil de leer y que resulte amena la lectura.
    5. Pide que se tenga en cuenta lo que se ha dicho antes tanto en el apartado como en general para evitar incongruencias. Añade referencias a lo que se ha dicho en otros párrafos.
    5.1 Está prohibido poner explícitamente algo de cómo ha sido la estructura o que hay referencias de prompts como "(referencia a PROMPT_1_1_B)". Si tienes que poner alguna referencia de algún sitio pon el apartado. Si no sabes que apartado es, opta por no poner nada de la referencia. No pueden detectar que este trabajo ha sido realizado con IA.
    6. No dudes en añadir tablas que resuman el contenido. Debes usar bullet points y listas para dar las ideas de una manera más clara para que el lector se sienta cómodo al leerlo. Lo ideal es que haya un número coherente de tablas, listados y elementos htmls sin resultar repetitivo. Siempre siguiendo un balance de 75% texto normal y 25% tablas, elementos gráficos html y listas fáciles de ver.
    7. Evita las conclusiones si van a ser redundantes. Suelen ser un sintoma de que se usa IA, así que saltatelas o no las empieces con expresiones como 'En definitiva' o 'En conclusión'. El objetivo es ser ameno y directo, y este tipo de secciones impiden llegar a ese objetivo.
    8. **REGLA DE ORO PARA ELEMENTOS VISUALES:** Si necesitas crear un elemento visual, DEBES generar un archivo HTML completo y auto-contenido. NO PUEDES generar solo CSS. Tu respuesta DEBE ser únicamente el código HTML, empezando con `<!DOCTYPE html>`. OBLIGATORIAMENTE, usa la siguiente plantilla base y solo modifica el contenido de los placeholders `<!-- TÍTULO AQUÍ -->` y `<!-- LISTA DE ELEMENTOS AQUÍ -->`. No alteres la estructura ni el CSS.

        ```html
        <!DOCTYPE html>
        <html lang="es">
        <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Visual Element</title>
            <style>
                @import url('https://fonts.googleapis.com/css2?family=Urbanist:wght@400;600;700&display=swap');
                body {{
                    font-family: 'Urbanist', sans-serif;
                    background-color: #f0f2f5;
                    display: flex;
                    justify-content: center;
                    align-items: center;
                    padding: 20px;
                    width: 800px;
                    box-sizing: border-box;
                }}
                .card {{
                    background-color: white;
                    border-radius: 10px;
                    box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                    padding: 25px;
                    width: 100%;
                    max-width: 750px;
                    border-top: 5px solid #0046C6;
                }}
                h2 {{
                    color: #0046C6;
                    text-align: center;
                    margin-top: 0;
                    font-size: 24px;
                    font-weight: 700;
                }}
                ul {{
                    list-style-type: none;
                    padding: 0;
                }}
                li {{
                    display: flex;
                    align-items: center;
                    margin-bottom: 15px;
                    font-size: 16px;
                    color: #333;
                }}
                li::before {{
                    content: '✔';
                    color: #32CFAA;
                    font-size: 20px;
                    font-weight: bold;
                    margin-right: 15px;
                }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2><!-- TÍTULO AQUÍ --></h2>
                <ul>
                    <!-- LISTA DE ELEMENTOS AQUÍ (usa <li>Elemento 1</li>, <li>Elemento 2</li>, etc.) -->
                </ul>
            </div>
        </body>
        </html>
        ```
    9. Debes cumplir todos los criterios pero sin mencionar que tu objetivo es cumplirlos. Es decir, debes hacer lo que se valora pero sin decir que esa sección existe para cumplir con un criterio. La redacción y el parafraseo debe ser muy elegante para demostrar un dominio y cumplimiento de los objetivos sin sonar pesado.
    10. No uses recursos como el ;, los : y ese tipo de expresiones que parecen hechas con IA. Tampoco uses expresiones precedidas por -. Debes prafasear mucho. Tu texto debe parecer natural sin perder la profesionalidad.
    11. Debes establecer el mismo idioma para todas las redacciones. Este idioma debe ser el castellano.
    12. Debes poner mucho detalle en los cronogramas. Detalla bien las fases y bájalo a semanas. En las actividades detalla bien cuánto tiempo llevan y qué se va a hacer en cada una de ellas. Especifica detalladamente las actividades o los objetos de contratación propuestos para que se vean como un plan de acción más que como algo teórico, que el que evalúa el contenido pueda ver claramente qué es exactamente lo que se va a hacer o ofrecer.
    13. Si se habla de KPIs de evaluación, propón unos realistas y que estén relacionados con la empresa. Explica porqué esos indicadores, en qué consistirán y cómo se utilizarán para evaluar el desempeño. Hazlo desde un marco que no comprometa a la empresa (es decir que sean realistas) y que de una imagen de profesionalidad al evaluador.
    14. No puedes mencionar las cualidades y atributos de la empresa cada dos por tres. Debes evitar el exceso de retórica, repetición continua de “metodología validada en mas de 1000 proyectos”, “índice de satisfacción 9.6”, “aliado estratégico...”. Eso suena a texto estandar y no convence. Debes ser directo, pulcro y evitar el meter contenido que no aporte valor. Evita frases grandilocuentes y repetitivas.
    15. Sé concreto, da siempre información clara sobre el quién, cómo, cuándo y cuánto. El corrector valora mucho que se sea concreto y claro en la propuesta. Específica clarmente la propuesta con pulcridad para que el redactor no entre en ambiguedades.
    16. Evita la redacción uniforme con frases muy largas, estructuradas y sobre todo con la repetición de conceptos. Evita el exceso de adjetivos y palabras muy cantosas típicas de textos generados o revisados con IA.
    17. No repitas la misma idea con palabras diferentes en apartados distintos. Intenta ser muy concreto en cada apartado y diferenciarte de los anteriores. No suenes redundante y trata de ser concreto y claro en cada apartado nuevo, manteniendo la coherencia con lo anterior pero evitando repetirte.
    18. No comiences los párrafos de los subapartados mencionando el nombre de la empresa y su compromiso con no se que "DPI Estrategia, en su compromiso con la transparencia y la rendición de cuentas, elaborará y entregará una memoria final completa al término de los doce meses del programa.". Usa mejor una introducción más limpia que no mencione el nombre de la empresa y que diga "A modo de cerrar el servicio, se cerrará con una memoria final. Esta memoria final incluirá...".
    19. No menciones el nombre de la empresa que se presenta a la licitación todo el rato. Ya se sabe que es la empresa, no hace falta ponerlo tan repetidamente.
    20. NO PONGAS NUNCA los títulos las primeras letras de las palabras en mayusculas. Es decir si la frase es "El Enfoque Nativo en la Nube y la IA" ponlo así "El enfoque nativo en la nube y la IA". Cuida mucho eso en tu redacción es fundamental.
    21. ESTÁ PROHIBIDO GENERAR PROMPTS QUE INCLUYAN INSTRUCCIONES O MARCADORES DE POSICIÓN como '[Completa aquí]' o '[Ajusta la tabla]'. El prompt debe contener toda la información para que el redactor final genere el texto completo, no para que le dé instrucciones.


    Estructura obligatoria para cada prompt: Cada prompt debe comenzar indicando con claridad qué apartado se va a redactar y cuál es el objetivo específico de ese apartado dentro de la memoria. A continuación, debe definir el rango o número aproximado de palabras que debe ocupar el texto. Seguidamente, se incluirá una explicación de contexto general de la dictación, detallando todos los puntos y requisitos que se deben cubrir en ese apartado. Después, se aportará un contexto concreto de la empresa, para cumplir esos requisitos presentando la propuesta de la empresa totalmente personalizada a sus fortalezas . Finalmente, el prompt debe cerrar con una lista de matices o consideraciones importantes para la redacción (tono, estilo, prohibiciones, obligatoriedades, etc.) las cuáles hemos pautado anteriormente cuando mencionamos las reglas, que sirvan como guía de calidad y eviten errores habituales.


    Si un apartado es "Índice", apartados que posean un 0 delante o algo análogo, evita ese apartado y no crees un prompt para ese caso. No hay que redactar nada en ese caso y por lo tanto no nos interesa.
    Debes seguir las intrucciones de contexto general que se te han dado al comienzo de esta conversación para que el docuemnto esté alineado a ello.
    Redacta el contenido de los prompts dentro del json en GitHub Flavored Markdown (gfm). Se pulcro con ello y pide que en la redacción también se use ese estilo.
    Es muy importante la calidad del contenido y lo visual que se muestre. Intenta meter muchas tablas, listas y elementos HTML que decoren y resuman el contenido. Debe ser visual y atractivo sin perder el toque profesional. Intenta no meter mucha paja ni contenido que no aporte nada de valor. Menos contenido, bien explicado y sin explicar los conceptos dos veces, céntrate en ir al grano y no dar vueltas.


    Este es el subapartado para el que debes redactar los prompts:


    - **Apartado Principal:** "{apartado_titulo}"
    - **Subapartado a Redactar:** "{subapartado_titulo}"


    Las instrucciones exactas de la plantilla para este subapartado son:
    - **Indicaciones (pueden venir vacías, en ese caso búscalas):** "{indicaciones}" (Complementalas y aumenta el contexto en tus instrucciones)


    **REGLAS DE SALIDA:**
    Tu respuesta DEBE ser SÓLO un único objeto JSON válido (sin ```json al principio ni ``` al final y sin ningún texto que lo acompañe), que contenga una única clave `"plan_de_prompts"` cuyo valor sea una lista de objetos. Cada objeto de la lista representa un prompt y debe seguir esta estructura exacta:


    {{{{
      "apartado_referencia": "El título del apartado principal que te he proporcionado (ej: 2. Solución Técnica Propuesta)",
      "subapartado_referencia": "El título del subapartado que te he proporcionado (ej: 2.1. Metodología de Trabajo)",
      "prompt_id": "Un identificador único para el prompt (ej: PROMPT_2_1_A)(Si es un HTML se debe agregar "HTML_VISUAL" al id (ej: PROMPT_2_1_1_HTML_VISUAL))",
      "prompt_para_asistente": "La pregunta o instrucción específica y detallada para el asistente (ej: )."
    }}}}


    Para redactar tu respuesta, DEBES utilizar la información de los archivos que tienes disponibles:
    1.  Consulta los **Pliegos** para entender y cumplir todos los requisitos técnicos y de puntuación mencionados en las indicaciones.
    2.  Consulta las **Memorias de ejemplo** para adoptar un tono, estilo y nivel de detalle similar. (Si aplica)
    3.  Consulta la **Doc. Empresa** para incorporar información específica de nuestra compañía (como nombres de tecnologías, proyectos pasados o certificaciones) si es relevante.


    **RESPUESTA EN ESPAÑOL SIEMPRE**


    Genera un texto profesional, bien estructurado y que responda directamente a las indicaciones. No añadas introducciones o conclusiones que no se pidan.
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
    """Obtiene las credenciales, forzando un nuevo login si los scopes han cambiado."""
    
    # --- !! ESTA ES LA NUEVA LÓGICA DE COMPROBACIÓN !! ---
    if 'credentials' in st.session_state and st.session_state.credentials:
        creds = st.session_state.credentials
        # Comprobamos si todos los scopes que necesitamos están en las credenciales guardadas.
        if not all(scope in creds.scopes for scope in SCOPES):
            # Si faltan scopes, las credenciales no son válidas. Las borramos.
            del st.session_state.credentials
            # Forzamos al usuario a la página de inicio para que se loguee de nuevo.
            go_to_landing()
            st.rerun() # Detenemos la ejecución actual y recargamos
    # --- !! FIN DE LA NUEVA LÓGICA !! ---

    if 'credentials' in st.session_state and st.session_state.credentials:
        creds = st.session_state.credentials
        if creds.expired and creds.refresh_token:
            try:
                # Necesitamos importar Request de google.auth.transport.requests
                from google.auth.transport.requests import Request
                creds.refresh(Request())
                st.session_state.credentials = creds
            except Exception as e:
                # Si el refresh token falla (p.ej. ha sido revocado), borramos credenciales
                del st.session_state.credentials
                go_to_landing()
                st.rerun()
        return creds

    if 'code' in st.query_params:
        try:
            flow = get_google_flow()
            flow.fetch_token(code=st.query_params['code'])
            st.session_state.credentials = flow.credentials
            # Limpiamos los parámetros de la URL para evitar bucles
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            # Si hay un error (como 'scope has changed'), lo mostramos y limpiamos el estado.
            st.error(f"Error al obtener el token: {e}")
            if 'credentials' in st.session_state:
                del st.session_state.credentials
            # Damos la opción de reintentar
            st.button("Reintentar inicio de sesión")
            st.stop() # Detenemos la ejecución para que no continúe con error
            
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
def go_to_phase2():
    st.session_state.page = 'phase_2'
def go_to_phase3(): st.session_state.page = 'phase_3'
def go_to_phase4(): st.session_state.page = 'phase_4' # <-- AÑADE ESTA LÍNEA

def back_to_project_selection_and_cleanup():
    for key in ['generated_structure', 'word_file', 'uploaded_template', 'uploaded_pliegos', 'selected_project']:
        if key in st.session_state: del st.session_state[key]
    go_to_project_selection()

def handle_full_regeneration(model):
    """
    Función centralizada que genera un índice completamente nuevo desde cero
    analizando los archivos de la carpeta 'Pliegos'.
    """
    if not st.session_state.get('drive_service') or not st.session_state.get('selected_project'):
        st.error("Error de sesión. No se puede iniciar la regeneración.")
        return False

    with st.spinner("Descargando archivos de 'Pliegos' y re-analizando desde cero..."):
        try:
            service = st.session_state.drive_service
            project_folder_id = st.session_state.selected_project['id']
            pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
            document_files = get_files_in_project(service, pliegos_folder_id)

            if not document_files:
                st.warning("No se encontraron archivos en la carpeta 'Pliegos' para analizar.")
                return False

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
                st.session_state.uploaded_pliegos = document_files # Actualizamos la lista de pliegos por si acaso
                st.toast("✅ ¡Índice regenerado desde cero con éxito!")
                return True
            else:
                st.error("La IA devolvió una respuesta vacía o no válida.")
                return False
        except Exception as e:
            st.error(f"Ocurrió un error durante la regeneración completa: {e}")
            return False

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

# =============================================================================
#           VERSIÓN DEFINITIVA DE phase_1_page()
# =============================================================================
def phase_1_page(model):
    """Página de Fase 1 que lee/escribe en subcarpetas y gestiona el estado correctamente."""
    if not st.session_state.get('selected_project'):
        st.warning("No se ha seleccionado ningún proyecto. Volviendo a la selección.")
        go_to_project_selection()
        st.rerun()

    project_name = st.session_state.selected_project['name']
    project_folder_id = st.session_state.selected_project['id']
    service = st.session_state.drive_service

    st.markdown(f"<h3>FASE 1: Análisis y Estructura</h3>", unsafe_allow_html=True)
    st.info(f"Estás trabajando en el proyecto: **{project_name}**")

    pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
    document_files = get_files_in_project(service, pliegos_folder_id)
    
    if document_files:
        st.success("Hemos encontrado estos archivos en la carpeta 'Pliegos' de tu proyecto:")
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
        st.info("La carpeta 'Pliegos' de este proyecto está vacía. Sube los archivos base.")

    with st.expander("Añadir o reemplazar documentación en la carpeta 'Pliegos'", expanded=not document_files):
        with st.container(border=True):
            st.subheader("Subir nuevos documentos")
            new_files_uploader = st.file_uploader("Arrastra aquí los nuevos Pliegos o Plantilla", type=['docx', 'pdf'], accept_multiple_files=True, key="new_files_uploader")
            if st.button("Guardar nuevos archivos en Drive"):
                if new_files_uploader:
                    with st.spinner("Subiendo archivos a la carpeta 'Pliegos'..."):
                        for file_obj in new_files_uploader:
                            upload_file_to_drive(service, file_obj, pliegos_folder_id)
                        st.rerun()
                else:
                    st.warning("Por favor, selecciona al menos un archivo para subir.")

    st.markdown("---")
    st.header("Análisis y Generación de Índice")
    
    docs_app_folder_id = find_or_create_folder(service, "Documentos aplicación", parent_id=project_folder_id)
    saved_index_id = find_file_by_name(service, "ultimo_indice.json", docs_app_folder_id)

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Cargar último índice generado", use_container_width=True, disabled=not saved_index_id):
            with st.spinner("Cargando índice desde Drive..."):
                index_content_bytes = download_file_from_drive(service, saved_index_id)
                index_data = json.loads(index_content_bytes.getvalue().decode('utf-8'))
                st.session_state.generated_structure = index_data
                st.session_state.uploaded_pliegos = document_files
                go_to_phase1_results()
                st.rerun()

    with col2:
        # Simplificamos este botón para que llame a la nueva función
        if st.button("Analizar Archivos y Generar Nuevo Índice", type="primary", use_container_width=True, disabled=not document_files):
            if handle_full_regeneration(model):
                go_to_phase1_results()
                st.rerun()

    st.write("")
    st.markdown("---")
    st.button("← Volver a Selección de Proyecto", on_click=back_to_project_selection_and_cleanup, use_container_width=True, key="back_to_projects")
# =============================================================================
#           VERSIÓN FINAL Y COMPLETA DE phase_1_results_page()
# =============================================================================

# =============================================================================
#           REEMPLAZA phase_1_results_page POR ESTA VERSIÓN COMPLETA
# =============================================================================

# =============================================================================
#           VERSIÓN FINAL Y COMPLETA DE phase_1_results_page() CON SINCRONIZACIÓN
# =============================================================================

def phase_1_results_page(model):
    """Página para revisar, regenerar, ACEPTAR el índice y SINCRONIZAR carpetas."""
    st.markdown("<h3>FASE 1: Revisión de Resultados</h3>", unsafe_allow_html=True)
    st.markdown("Revisa el índice. Puedes hacer ajustes con feedback, regenerarlo todo desde cero, o aceptarlo para continuar.")
    st.markdown("---")
    st.button("← Volver a la gestión de archivos", on_click=go_to_phase1)

    if 'generated_structure' not in st.session_state or not st.session_state.generated_structure:
        st.warning("No se ha generado ninguna estructura.")
        return

    def handle_regeneration_with_feedback():
        feedback_text = st.session_state.feedback_area
        if not feedback_text:
            st.warning("Por favor, escribe tus indicaciones en el área de texto.")
            return

        with st.spinner("🧠 Incorporando tu feedback y regenerando la estructura..."):
            try:
                contenido_ia_regeneracion = [PROMPT_REGENERACION]
                contenido_ia_regeneracion.append("--- INSTRUCCIONES DEL USUARIO ---\n" + feedback_text)
                contenido_ia_regeneracion.append("--- ESTRUCTURA JSON ANTERIOR A CORREGIR ---\n" + json.dumps(st.session_state.generated_structure, indent=2))
                
                if st.session_state.get('uploaded_pliegos'):
                    service = st.session_state.drive_service
                    for file_info in st.session_state.uploaded_pliegos:
                        file_content_bytes = download_file_from_drive(service, file_info['id'])
                        contenido_ia_regeneracion.append({"mime_type": file_info['mimeType'], "data": file_content_bytes.getvalue()})

                generation_config = genai.GenerationConfig(response_mime_type="application/json")
                response_regeneracion = model.generate_content(contenido_ia_regeneracion, generation_config=generation_config)
                json_limpio_str_regenerado = limpiar_respuesta_json(response_regeneracion.text)
                
                if json_limpio_str_regenerado:
                    st.session_state.generated_structure = json.loads(json_limpio_str_regenerado)
                    st.toast("¡Estructura regenerada con feedback!")
                    st.session_state.feedback_area = "" # Limpiamos el área de texto
                else:
                    st.error("La IA no devolvió una estructura válida tras la regeneración.")
            except Exception as e:
                st.error(f"Ocurrió un error durante la regeneración: {e}")

    with st.container(border=True):
        mostrar_indice_desplegable(st.session_state.generated_structure.get('estructura_memoria'))
        st.markdown("---")
        st.subheader("Validación y Siguiente Paso")
        
        st.text_area("Si necesitas cambios, indícalos aquí:", key="feedback_area", placeholder="Ej: 'Une los apartados 1.1 y 1.2 en uno solo.'")
        
        # --- NUEVO LAYOUT DE BOTONES ---
        col1, col2 = st.columns(2)
        with col1:
            st.button("Regenerar con Feedback", on_click=handle_regeneration_with_feedback, use_container_width=True, disabled=not st.session_state.get("feedback_area"))
        with col2:
            # ESTE ES TU NUEVO BOTÓN
            st.button("🔁 Regenerar Índice Entero", on_click=handle_full_regeneration, args=(model,), use_container_width=True, help="Descarta este índice y genera uno nuevo desde cero analizando los pliegos otra vez.")

        # Botón de aceptar ahora ocupa todo el ancho para destacar
        if st.button("Aceptar Índice y Pasar a Fase 2 →", type="primary", use_container_width=True):
            with st.spinner("Sincronizando carpetas y guardando índice final en Drive..."):
                try:
                    service = st.session_state.drive_service
                    project_folder_id = st.session_state.selected_project['id']
                    
                    deleted_count = sync_guiones_folders_with_index(service, project_folder_id, st.session_state.generated_structure)
                    if deleted_count > 0:
                        st.success(f"Limpieza completada: {deleted_count} carpetas de guiones obsoletas eliminadas.")

                    docs_app_folder_id = find_or_create_folder(service, "Documentos aplicación", parent_id=project_folder_id)
                    json_bytes = json.dumps(st.session_state.generated_structure, indent=2).encode('utf-8')
                    mock_file_obj = io.BytesIO(json_bytes)
                    mock_file_obj.name = "ultimo_indice.json"
                    mock_file_obj.type = "application/json"
                    
                    saved_index_id = find_file_by_name(service, "ultimo_indice.json", docs_app_folder_id)
                    if saved_index_id:
                        delete_file_from_drive(service, saved_index_id)
                    upload_file_to_drive(service, mock_file_obj, docs_app_folder_id)
                    st.toast("Índice final guardado en tu proyecto de Drive.")
                    
                    go_to_phase2()
                    st.rerun()

                except Exception as e:
                    st.error(f"Ocurrió un error durante la sincronización o guardado: {e}")

# =============================================================================
#           REEMPLAZA TU phase_2_page ACTUAL POR ESTA VERSIÓN DEFINITIVA
# =============================================================================

# =============================================================================
#           REEMPLAZA TU phase_2_page ACTUAL POR ESTA VERSIÓN DEFINITIVA
# =============================================================================

def phase_2_page(model):
    """Centro de mando para la generación y re-generación de guiones con documentación de apoyo."""
    st.markdown("<h3>FASE 2: Centro de Mando de Guiones</h3>", unsafe_allow_html=True)
    st.markdown("Genera los borradores iniciales adjuntando documentación de apoyo, revísalos en Drive y luego re-genéralos con el feedback incorporado.")
    st.markdown("---")

    # --- SETUP INICIAL (VERSIÓN ROBUSTA) ---
    service = st.session_state.drive_service
    project_folder_id = st.session_state.selected_project['id']

    if 'generated_structure' not in st.session_state:
        st.info("Sincronizando índice desde Google Drive...")
        try:
            docs_app_folder_id = find_or_create_folder(service, "Documentos aplicación", parent_id=project_folder_id)
            saved_index_id = find_file_by_name(service, "ultimo_indice.json", docs_app_folder_id)
            if saved_index_id:
                index_content_bytes = download_file_from_drive(service, saved_index_id)
                st.session_state.generated_structure = json.loads(index_content_bytes.getvalue().decode('utf-8'))
                st.rerun() 
            else:
                st.warning("No se ha encontrado un índice guardado. Por favor, vuelve a la Fase 1 para generar uno.")
                if st.button("← Ir a Fase 1"): go_to_phase1(); st.rerun()
                return
        except Exception as e:
            st.error(f"Error al cargar el índice desde Drive: {e}")
            return

    # =============================================================================
    #           INICIO DEL BLOQUE CORREGIDO: CONSTRUCCIÓN DE LISTA A PRUEBA DE FALLOS
    # =============================================================================
    
    estructura = st.session_state.generated_structure.get('estructura_memoria', [])
    matices_originales = st.session_state.generated_structure.get('matices_desarrollo', [])
    
    # --- INICIO DE LA CORRECCIÓN ---
    # Creamos un diccionario para buscar matices, PERO solo si el item es un diccionario válido.
    # Esto evita el AttributeError si la lista contiene strings u otros tipos.
    matices_dict = {
        item.get('subapartado', ''): item 
        for item in matices_originales 
        if isinstance(item, dict) and 'subapartado' in item
    }
    # --- FIN DE LA CORRECCIÓN ---
    
    # Construimos nuestra propia lista completa y robusta
    if not estructura:
        st.error("La estructura JSON no contiene la clave 'estructura_memoria'. Vuelve a generar el índice.")
        return

    subapartados_a_mostrar = []
    for seccion in estructura:
        apartado_principal = seccion.get('apartado', 'Sin Título')
        for subapartado_titulo in seccion.get('subapartados', []):
            # Buscamos si hay un matiz detallado para este subapartado
            matiz_existente = matices_dict.get(subapartado_titulo)
            
            if matiz_existente:
                # Si lo encontramos, lo usamos tal cual
                subapartados_a_mostrar.append(matiz_existente)
            else:
                # Si no existe, creamos una entrada básica para asegurar que se muestre en la UI
                subapartados_a_mostrar.append({
                    "apartado": apartado_principal,
                    "subapartado": subapartado_titulo,
                    "indicaciones": "No se encontraron indicaciones detalladas para este apartado en el JSON."
                })

    if not subapartados_a_mostrar:
        st.warning("El índice no parece contener ningún subapartado para gestionar.")
        return
        
    # =============================================================================
    #           FIN DEL BLOQUE CORREGIDO. AHORA USAMOS 'subapartados_a_mostrar'
    # =============================================================================


    # --- LÓGICA DE ACCIONES (GENERAR Y RE-GENERAR) ---
    def ejecutar_generacion(titulo, indicaciones_completas):
        nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", titulo)
        nombre_archivo = nombre_limpio + ".docx"
        
        with st.spinner(f"Generando borrador para '{titulo}'..."):
            try:
                guiones_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
                subapartado_guion_folder_id = find_or_create_folder(service, nombre_limpio, parent_id=guiones_folder_id)
                pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
                pliegos_en_drive = get_files_in_project(service, pliegos_folder_id)

                contenido_ia = [PROMPT_PREGUNTAS_TECNICAS_INDIVIDUAL]
                contenido_ia.append("--- INDICACIONES PARA ESTE APARTADO ---\n" + json.dumps(indicaciones_completas, indent=2, ensure_ascii=False))
                
                for file_info in pliegos_en_drive:
                    file_content_bytes = download_file_from_drive(service, file_info['id'])
                    contenido_ia.append({"mime_type": file_info['mimeType'], "data": file_content_bytes.getvalue()})
                
                doc_extra_key = f"upload_{titulo}"
                if doc_extra_key in st.session_state and st.session_state[doc_extra_key]:
                    for uploaded_file in st.session_state[doc_extra_key]:
                        contenido_ia.append("--- DOCUMENTACIÓN DE APOYO ADICIONAL ---\n")
                        contenido_ia.append({"mime_type": uploaded_file.type, "data": uploaded_file.getvalue()})
                        upload_file_to_drive(service, uploaded_file, subapartado_guion_folder_id)

                response = model.generate_content(contenido_ia)
                
                documento = docx.Document()
                agregar_markdown_a_word(documento, response.text)
                doc_io = io.BytesIO()
                documento.save(doc_io)
                word_file_obj = io.BytesIO(doc_io.getvalue())
                word_file_obj.name = nombre_archivo
                word_file_obj.type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                
                upload_file_to_drive(service, word_file_obj, subapartado_guion_folder_id)
                
                st.toast(f"Borrador para '{titulo}' generado y guardado en su carpeta.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al generar '{titulo}': {e}")

    def ejecutar_regeneracion(titulo, file_id_borrador):
        nombre_archivo = re.sub(r'[\\/*?:"<>|]', "", titulo) + ".docx"
        with st.spinner(f"Re-generando '{titulo}' con feedback de Drive..."):
            try:
                file_metadata = service.files().get(fileId=file_id_borrador, fields='parents').execute()
                parent_folder_id = file_metadata.get('parents')[0] if file_metadata.get('parents') else None
                if not parent_folder_id:
                    st.error("No se pudo encontrar la carpeta del guion original. Operación cancelada.")
                    return

                doc_bytes = download_file_from_drive(service, file_id_borrador)
                documento_revisado = docx.Document(io.BytesIO(doc_bytes.getvalue()))
                texto_revisado = "\n".join([p.text for p in documento_revisado.paragraphs])
                
                pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
                pliegos_en_drive = get_files_in_project(service, pliegos_folder_id)
                contenido_ia = [PROMPT_CONSULTOR_REVISION]
                contenido_ia.append("--- BORRADOR ORIGINAL / TEXTO REVISADO Y COMENTARIOS ---\n" + texto_revisado)
                
                for file_info in pliegos_en_drive:
                    file_content_bytes = download_file_from_drive(service, file_info['id'])
                    contenido_ia.append({"mime_type": file_info['mimeType'], "data": file_content_bytes.getvalue()})

                response = model.generate_content(contenido_ia)
                
                documento = docx.Document()
                agregar_markdown_a_word(documento, response.text)
                doc_io = io.BytesIO()
                documento.save(doc_io)
                word_file_obj = io.BytesIO(doc_io.getvalue())
                word_file_obj.name = nombre_archivo
                word_file_obj.type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                
                delete_file_from_drive(service, file_id_borrador)
                upload_file_to_drive(service, word_file_obj, parent_folder_id)
                
                st.toast(f"Guion para '{titulo}' re-generado con éxito.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al re-generar '{titulo}': {e}")
                
    def ejecutar_borrado(titulo, folder_id_to_delete):
        with st.spinner(f"Eliminando guion y contexto para '{titulo}'..."):
            try:
                success = delete_file_from_drive(service, folder_id_to_delete)
                if success:
                    st.toast(f"Guion para '{titulo}' eliminado correctamente.")
                    st.rerun()
                else:
                    st.error(f"No se pudo completar la eliminación de '{titulo}'.")
            except Exception as e:
                st.error(f"Ocurrió un error inesperado al intentar borrar '{titulo}': {e}")

    # --- INTERFAZ DE GESTIÓN DE GUIONES ---
    st.subheader("Gestión de Guiones de Subapartados")
    
    with st.spinner("Sincronizando con Google Drive..."):
        guiones_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
        query_subcarpetas = f"'{guiones_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        response_subcarpetas = service.files().list(q=query_subcarpetas, spaces='drive', fields='files(id, name)').execute()
        carpetas_de_guiones_existentes = {f['name']: f['id'] for f in response_subcarpetas.get('files', [])}

    # Bucle final que ahora usa la lista robusta 'subapartados_a_mostrar'
    for i, matiz in enumerate(subapartados_a_mostrar):
        subapartado_titulo = matiz.get('subapartado')
        if not subapartado_titulo:
            continue
        
        nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", subapartado_titulo)
        
        if nombre_limpio in carpetas_de_guiones_existentes:
            estado = "📄 Generado"
            subapartado_folder_id = carpetas_de_guiones_existentes[nombre_limpio]
            files_in_subfolder = get_files_in_project(service, subapartado_folder_id)
            file_info = next((f for f in files_in_subfolder if f['name'].endswith('.docx')), None)
        else:
            estado = "⚪ No Generado"
            file_info = None
            subapartado_folder_id = None

        with st.container(border=True):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.write(f"**{subapartado_titulo}**")
                st.caption(f"Estado: {estado}")

                if estado == "⚪ No Generado":
                    st.file_uploader(
                        "Aportar documentación de apoyo",
                        type=['pdf', 'docx', 'txt'],
                        key=f"upload_{subapartado_titulo}",
                        accept_multiple_files=True,
                        label_visibility="collapsed"
                    )

            with col2:
                btn_container = st.container()
                if estado == "📄 Generado" and file_info:
                    link = f"https://docs.google.com/document/d/{file_info['id']}/edit"
                    btn_container.link_button("Revisar en Drive", link, use_container_width=True)
                    if btn_container.button("Re-Generar con Feedback", key=f"regen_{i}", type="primary", use_container_width=True):
                        ejecutar_regeneracion(subapartado_titulo, file_info['id'])
                    if btn_container.button("🗑️ Borrar", key=f"del_{i}", help="Eliminar guion y su carpeta", use_container_width=True):
                         ejecutar_borrado(subapartado_titulo, subapartado_folder_id)
                else:
                    if btn_container.button("Generar Borrador", key=f"gen_{i}", use_container_width=True):
                        ejecutar_generacion(subapartado_titulo, matiz)

    # --- NAVEGACIÓN ---
    st.markdown("---")
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        st.button("← Volver a Revisión de Índice (F1)", on_click=go_to_phase1_results, use_container_width=True)
    with col_nav2:
        st.button("Ir a Plan de Prompts (F3) →", on_click=go_to_phase3, use_container_width=True)
# =============================================================================
#           REEMPLAZA TU phase_3_page ACTUAL POR ESTA VERSIÓN DEFINITIVA
# =============================================================================

# =============================================================================
#           REEMPLAZA TU phase_3_page ACTUAL POR ESTA VERSIÓN DEFINITIVA
# =============================================================================

def phase_3_page(model):
    """Página interactiva para generar, descargar y unificar planes de prompts."""
    st.markdown("<h3>FASE 3: Centro de Mando de Prompts</h3>", unsafe_allow_html=True)
    st.markdown("Genera planes de prompts individuales para los apartados que necesites. Cuando termines, unifícalos en un solo plan maestro para la redacción final.")
    st.markdown("---")

    # --- SETUP ROBUSTO ---
    service = st.session_state.drive_service
    project_folder_id = st.session_state.selected_project['id']
    docs_app_folder_id = find_or_create_folder(service, "Documentos aplicación", parent_id=project_folder_id)

    if 'generated_structure' not in st.session_state:
        st.info("Sincronizando índice desde Google Drive...")
        saved_index_id = find_file_by_name(service, "ultimo_indice.json", docs_app_folder_id)
        if saved_index_id:
            index_content_bytes = download_file_from_drive(service, saved_index_id)
            st.session_state.generated_structure = json.loads(index_content_bytes.getvalue().decode('utf-8'))
            st.rerun()
        else:
            st.warning("No se ha encontrado un índice. Vuelve a Fase 1 para generarlo.")
            if st.button("← Ir a Fase 1"): go_to_phase1(); st.rerun()
            return

    # =============================================================================
    #           INICIO DEL BLOQUE CORREGIDO: CONSTRUCCIÓN DE LISTA A PRUEBA DE FALLOS
    # =============================================================================
    
    estructura = st.session_state.generated_structure.get('estructura_memoria', [])
    matices_originales = st.session_state.generated_structure.get('matices_desarrollo', [])
    
    # --- INICIO DE LA CORRECCIÓN ---
    # Creamos un diccionario para buscar matices, PERO solo si el item es un diccionario válido.
    matices_dict = {
        item.get('subapartado', ''): item 
        for item in matices_originales 
        if isinstance(item, dict) and 'subapartado' in item
    }
    # --- FIN DE LA CORRECCIÓN ---
    
    if not estructura:
        st.error("La estructura JSON no contiene la clave 'estructura_memoria'. Vuelve a generar el índice.")
        return

    subapartados_a_mostrar = []
    for seccion in estructura:
        apartado_principal = seccion.get('apartado', 'Sin Título')
        for subapartado_titulo in seccion.get('subapartados', []):
            matiz_existente = matices_dict.get(subapartado_titulo)
            if matiz_existente:
                subapartados_a_mostrar.append(matiz_existente)
            else:
                subapartados_a_mostrar.append({
                    "apartado": apartado_principal,
                    "subapartado": subapartado_titulo,
                    "indicaciones": "No se encontraron indicaciones detalladas para este apartado en el JSON."
                })

    if not subapartados_a_mostrar:
        st.warning("El índice no parece contener ningún subapartado para gestionar.")
        return

    # =============================================================================
    #           FIN DEL BLOQUE CORREGIDO. AHORA USAMOS 'subapartados_a_mostrar'
    # =============================================================================
    
    # --- FUNCIÓN INTERNA DE GENERACIÓN INDIVIDUAL ---
    def handle_individual_generation(matiz_info, callback_model):
        apartado_titulo = matiz_info.get("apartado", "N/A")
        subapartado_titulo = matiz_info.get("subapartado", "N/A")
        
        with st.spinner(f"Generando y guardando plan para: '{subapartado_titulo}'..."):
            try:
                guiones_main_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
                nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", subapartado_titulo)
                subapartado_folder_id = find_or_create_folder(service, nombre_limpio, parent_id=guiones_main_folder_id)
                
                contexto_adicional_str = ""
                files_in_subfolder = get_files_in_project(service, subapartado_folder_id)
                for file_info in files_in_subfolder:
                    file_bytes = download_file_from_drive(service, file_info['id'])
                    if file_info['name'].endswith('.docx'):
                        doc = docx.Document(io.BytesIO(file_bytes.getvalue()))
                        texto_doc = "\n".join([p.text for p in doc.paragraphs])
                        contexto_adicional_str += f"\n--- CONTENIDO DEL GUION ({file_info['name']}) ---\n{texto_doc}\n"
                    elif file_info['name'].endswith('.pdf'):
                        reader = PdfReader(io.BytesIO(file_bytes.getvalue()))
                        texto_pdf = "".join(page.extract_text() for page in reader.pages)
                        contexto_adicional_str += f"\n--- CONTENIDO DEL PDF DE APOYO ({file_info['name']}) ---\n{texto_pdf}\n"

                pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
                pliegos_files_info = get_files_in_project(service, pliegos_folder_id)
                pliegos_content_for_ia = [{"mime_type": f['mimeType'], "data": download_file_from_drive(service, f['id']).getvalue()} for f in pliegos_files_info]

                prompt_final = PROMPT_DESARROLLO.format(
                    apartado_titulo=apartado_titulo,
                    subapartado_titulo=subapartado_titulo,
                    indicaciones=matiz_info.get("indicaciones", ""),
                )

                contenido_ia = [prompt_final] + pliegos_content_for_ia
                if contexto_adicional_str:
                    contenido_ia.append("--- CONTEXTO ADICIONAL DE GUIONES Y DOCUMENTACIÓN DE APOYO ---\n" + contexto_adicional_str)

                generation_config = genai.GenerationConfig(response_mime_type="application/json")
                response = callback_model.generate_content(contenido_ia, generation_config=generation_config)
                
                json_limpio_str = limpiar_respuesta_json(response.text)
                if json_limpio_str:
                    plan_parcial_obj = json.loads(json_limpio_str)
                    json_bytes = json.dumps(plan_parcial_obj, indent=2, ensure_ascii=False).encode('utf-8')
                    mock_file_obj = io.BytesIO(json_bytes)
                    mock_file_obj.name = "prompts_individual.json"
                    mock_file_obj.type = "application/json"
                    
                    old_plan_id = find_file_by_name(service, "prompts_individual.json", subapartado_folder_id)
                    if old_plan_id:
                        delete_file_from_drive(service, old_plan_id)
                    upload_file_to_drive(service, mock_file_obj, subapartado_folder_id)
                    st.toast(f"Plan para '{subapartado_titulo}' guardado en su carpeta de Drive.")
                    st.rerun()

            except Exception as e:
                st.error(f"Error generando prompts para '{subapartado_titulo}': {e}")
    
    def handle_conjunto_generation():
        with st.spinner("Buscando y unificando todos los planes de prompts individuales..."):
            try:
                all_prompts = []
                guiones_main_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
                query_subcarpetas = f"'{guiones_main_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
                response_subcarpetas = service.files().list(q=query_subcarpetas, spaces='drive', fields='files(id, name)').execute()
                
                for subfolder in response_subcarpetas.get('files', []):
                    individual_plan_id = find_file_by_name(service, "prompts_individual.json", subfolder['id'])
                    if individual_plan_id:
                        json_bytes = download_file_from_drive(service, individual_plan_id).getvalue()
                        individual_plan_obj = json.loads(json_bytes.decode('utf-8'))
                        all_prompts.extend(individual_plan_obj.get("plan_de_prompts", []))
                
                if not all_prompts:
                    st.warning("No se encontraron planes individuales para unificar. Genera al menos uno.")
                    return

                all_prompts.sort(key=lambda x: x.get('prompt_id', ''))

                final_json_object = {"plan_de_prompts": all_prompts}
                json_bytes_conjunto = json.dumps(final_json_object, indent=2, ensure_ascii=False).encode('utf-8')
                mock_file_obj = io.BytesIO(json_bytes_conjunto)
                mock_file_obj.name = "plan_de_prompts_conjunto.json"
                mock_file_obj.type = "application/json"
                
                old_conjunto_id = find_file_by_name(service, "plan_de_prompts_conjunto.json", docs_app_folder_id)
                if old_conjunto_id:
                    delete_file_from_drive(service, old_conjunto_id)
                
                upload_file_to_drive(service, mock_file_obj, docs_app_folder_id)
                st.success(f"¡Plan conjunto generado y ORDENADO con {len(all_prompts)} prompts y guardado en Drive!")

            except Exception as e:
                st.error(f"Error al generar el plan conjunto: {e}")

    # --- INTERFAZ DE USUARIO ---
    with st.spinner("Verificando estado de los guiones y planes..."):
        guiones_main_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
        query_subcarpetas = f"'{guiones_main_folder_id}' in parents and trashed = false"
        response_subcarpetas = service.files().list(q=query_subcarpetas, spaces='drive', fields='files(id, name)').execute()
        carpetas_con_info = {f['name']: f['id'] for f in response_subcarpetas.get('files', [])}
        
        planes_individuales_existentes = {}
        for nombre, folder_id in carpetas_con_info.items():
            plan_id = find_file_by_name(service, "prompts_individual.json", folder_id)
            if plan_id:
                planes_individuales_existentes[nombre] = plan_id

    # Bucle que ahora usa la lista robusta 'subapartados_a_mostrar'
    for i, matiz in enumerate(subapartados_a_mostrar):
        subapartado_titulo = matiz.get("subapartado")
        if not subapartado_titulo: continue

        nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", subapartado_titulo)
        guion_generado = nombre_limpio in carpetas_con_info
        plan_individual_id = planes_individuales_existentes.get(nombre_limpio)

        with st.container(border=True):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.write(f"**{subapartado_titulo}**")
                if not guion_generado:
                    st.warning("⚠️ Guion no generado en Fase 2. No se puede crear un plan de prompts.")
                elif plan_individual_id:
                    st.success("✔️ Plan generado")
                    with st.expander("Ver / Descargar Plan Individual"):
                        json_bytes = download_file_from_drive(service, plan_individual_id).getvalue()
                        st.json(json_bytes.decode('utf-8'))
                        st.download_button("Descargar JSON", data=json_bytes, file_name=f"prompts_{nombre_limpio}.json", mime="application/json", key=f"dl_{i}")
                else:
                    st.info("⚪ Pendiente de generar plan de prompts")
            
            with col2:
                if plan_individual_id:
                    st.button("Re-generar Plan", key=f"gen_regen_{i}", on_click=handle_individual_generation, args=(matiz, model), use_container_width=True, type="secondary", disabled=not guion_generado)
                else:
                    st.button("Generar Plan de Prompts", key=f"gen_{i}", on_click=handle_individual_generation, args=(matiz, model), use_container_width=True, type="primary", disabled=not guion_generado)

    # --- BOTONES DE NAVEGACIÓN ---
    st.markdown("---")
    col_nav3_1, col_nav3_2 = st.columns(2)
    with col_nav3_1:
        st.button("🚀 Generar Plan de Prompts Conjunto", on_click=handle_conjunto_generation, use_container_width=True, type="primary", help="Unifica todos los planes individuales generados en un único archivo maestro.")

    with col_nav3_2:
        st.button("Ir a Redacción Final (F4) →", on_click=go_to_phase4, use_container_width=True)

    st.button("← Volver al Centro de Mando (F2)", on_click=go_to_phase2, use_container_width=True)
# =============================================================================
#           FASE 4 - REDACCIÓN Y ENSAMBLAJE FINAL
# =============================================================================

def phase_4_page(model):
    """Página para ejecutar el plan de prompts y generar el documento Word final."""
    st.markdown("<h3>FASE 4: Redacción y Ensamblaje Final</h3>", unsafe_allow_html=True)
    st.markdown("Ejecuta el plan de prompts conjunto para generar el contenido de la memoria técnica y descargar el documento Word final.")
    st.markdown("---")

    # --- SETUP ROBUSTO Y CARGA DEL PLAN CONJUNTO ---
    service = st.session_state.drive_service
    project_folder_id = st.session_state.selected_project['id']
    docs_app_folder_id = find_or_create_folder(service, "Documentos aplicación", parent_id=project_folder_id)

    # Buscar el plan de prompts conjunto
    plan_conjunto_id = find_file_by_name(service, "plan_de_prompts_conjunto.json", docs_app_folder_id)

    if not plan_conjunto_id:
        st.warning("No se ha encontrado un 'plan_de_prompts_conjunto.json' en la carpeta 'Documentos aplicación'.")
        st.info("Por favor, vuelve a la Fase 3 y genera el plan conjunto antes de continuar.")
        if st.button("← Ir a Fase 3"):
            go_to_phase3()
            st.rerun()
        return

    # Descargar y cargar el plan
    try:
        json_bytes = download_file_from_drive(service, plan_conjunto_id).getvalue()
        plan_de_accion = json.loads(json_bytes.decode('utf-8'))
        lista_de_prompts = plan_de_accion.get("plan_de_prompts", [])
        st.success(f"✔️ Plan de acción conjunto cargado con éxito. Se encontraron {len(lista_de_prompts)} prompts para ejecutar.")
    except Exception as e:
        st.error(f"Error al cargar o procesar el plan de acción desde Drive: {e}")
        return

    # Función para convertir HTML a imagen (adaptada para Streamlit)
    def html_a_imagen(html_content, output_filename="imagen_html.png"):
        try:
            options = {
                'format': 'png',
                'encoding': "UTF-8",
                'quiet': ''
            }
            # Usamos imgkit para generar la imagen desde el string HTML
            imgkit.from_string(html_content, output_filename, options=options)
            if os.path.exists(output_filename):
                return output_filename
            return None
        except Exception as e:
            st.error(f"Error al convertir HTML a imagen con imgkit: {e}")
            st.warning("Asegúrate de tener 'wkhtmltopdf' en tu 'packages.txt'.")
            return None

    # --- LÓGICA DE EJECUCIÓN ---
    if st.button("🚀 Iniciar Redacción y Generar Documento Final", type="primary", use_container_width=True):
        if not lista_de_prompts:
            st.warning("El plan de acción está vacío. No hay nada que generar.")
            return

        st.info("Iniciando el proceso de redacción... Esto puede tardar varios minutos.")
        progress_bar = st.progress(0, text="Configurando sesión de chat...")

        documento = docx.Document()
        chat_redaccion = model.start_chat()
        
        # Contexto inicial para el chat
        prompt_inicial = """
        Eres un consultor experto redactando memorias técnicas para licitaciones. Tu única misión es redactar el contenido que te solicite.
        Tu salida debe ser exclusivamente el texto solicitado, ya sea en formato Markdown o en código HTML completo.
        El objetivo es un informe claro, muy visual, directo y de lectura amena.
        No añadas títulos a menos que el prompt indique que es un nuevo subapartado (usando ## o ###).
        Recuerda el toque humano, la coherencia y evita formalismos excesivos.
        Evita clichés como 'referente indiscutible' o 'vibrante ecosistema'.
        
        REGLA DE ORO: Está estrictamente prohibido que dejes texto por completar o que incluyas marcadores de posición como '[Completa con información...]' o '[Ajusta la tabla...]'. Debes generar siempre el contenido final y completo. Si no tienes la información, es preferible que omitas esa parte a que dejes una instrucción.
        """
        try:
            chat_redaccion.send_message(prompt_inicial)
            time.sleep(1)
        except Exception as e:
            st.error(f"Error en el mensaje de configuración inicial con la IA: {e}")
            return
        
        ultimo_apartado_escrito = ""
        ultimo_subapartado_escrito = ""
        total_prompts = len(lista_de_prompts)
        
        for i, tarea in enumerate(lista_de_prompts):
            progress_text = f"Procesando Tarea {i+1}/{total_prompts} (ID: {tarea.get('prompt_id', 'N/A')})"
            progress_bar.progress((i + 1) / total_prompts, text=progress_text)
            
            prompt_actual = tarea.get("prompt_para_asistente")
            if not prompt_actual:
                continue

            # Añadir títulos de apartado y subapartado si cambian
            apartado_actual = tarea.get("apartado_referencia", "Sin Apartado")
            subapartado_actual = tarea.get("subapartado_referencia", "Sin Subapartado")
            if apartado_actual != ultimo_apartado_escrito:
                if ultimo_apartado_escrito != "":
                    documento.add_page_break()
                documento.add_heading(apartado_actual, level=1)
                ultimo_apartado_escrito = apartado_actual
                ultimo_subapartado_escrito = ""
            if subapartado_actual and subapartado_actual != ultimo_subapartado_escrito:
                documento.add_heading(subapartado_actual, level=2)
                ultimo_subapartado_escrito = subapartado_actual

            # Lógica de reintentos para la llamada a la API
            respuesta_ia = None
            for attempt in range(3):
                try:
                    response = chat_redaccion.send_message(prompt_actual)
                    respuesta_ia = response.text
                    time.sleep(1) # Pausa para no saturar la API
                    break
                except Exception as e:
                    st.warning(f"Intento {attempt + 1} fallido para la tarea {i+1}: {e}. Reintentando...")
                    time.sleep(5)
            
            if respuesta_ia is None:
                st.error(f"Fallo definitivo al generar contenido para la tarea {i+1}. Se insertará un marcador de error.")
                documento.add_paragraph(f"[ERROR: No se pudo generar el contenido para este bloque tras 3 intentos]").bold = True
                continue

            # Procesamiento de la respuesta (HTML o Markdown)
            if '<!DOCTYPE html>' in respuesta_ia and '<body>' in respuesta_ia and '<style>' in respuesta_ia:
                html_limpio = limpiar_respuesta_json(respuesta_ia) # Reutilizamos esta función para limpiar ```html
                nombre_img = f"temp_img_prompt_{i+1}.png"
                image_file = html_a_imagen(html_limpio, output_filename=nombre_img)
                if image_file and os.path.exists(image_file):
                    documento.add_picture(image_file, width=docx.shared.Inches(6))
                    os.remove(image_file)
                else:
                    documento.add_paragraph(f"[ERROR AL GENERAR IMAGEN, SE INCLUYE CÓDIGO HTML COMO TEXTO]").bold = True
                    documento.add_paragraph(f"```html\n{html_limpio}\n```")
            else:
                agregar_markdown_a_word(documento, respuesta_ia)

        # --- GUARDADO Y DESCARGA ---
        progress_bar.progress(1.0, text="Ensamblando y guardando el documento final...")
        
        project_name = st.session_state.selected_project['name']
        safe_project_name = re.sub(r'[\\/*?:"<>|]', "", project_name).replace(' ', '_')
        nombre_archivo_final = f"Memoria_Tecnica_{safe_project_name}.docx"

        # Guardar en un buffer en memoria
        doc_io = io.BytesIO()
        documento.save(doc_io)
        doc_io.seek(0)
        
        # Subir a Google Drive
        st.toast("Subiendo documento final a Google Drive...")
        try:
            # Creamos un objeto de archivo simulado para la función de subida
            word_file_obj = io.BytesIO(doc_io.getvalue()) # Usamos una copia del buffer
            word_file_obj.name = nombre_archivo_final
            word_file_obj.type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            
            # Borramos la versión anterior si existe, para evitar duplicados
            old_file_id = find_file_by_name(service, nombre_archivo_final, docs_app_folder_id)
            if old_file_id:
                delete_file_from_drive(service, old_file_id)
            
            upload_file_to_drive(service, word_file_obj, docs_app_folder_id)
            st.success(f"¡Documento '{nombre_archivo_final}' guardado en la carpeta 'Documentos aplicación' de tu Drive!")
        except Exception as e:
            st.error(f"Error al guardar el documento en Drive: {e}")

        # Ofrecer para descarga en Streamlit
        st.balloons()
        st.download_button(
            label="🎉 Descargar Memoria Técnica Final (.docx)",
            data=doc_io, # Usamos el buffer original
            file_name=nombre_archivo_final,
            mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            use_container_width=True
        )

    st.markdown("---")
    st.button("← Volver a Fase 3", on_click=go_to_phase3, use_container_width=True)
    
# =============================================================================
#                        LÓGICA PRINCIPAL (ROUTER) - VERSIÓN CORREGIDA
# =============================================================================

# Primero, SIEMPRE comprobamos si tenemos credenciales de usuario.
credentials = get_credentials()

# Si NO hay credenciales, el usuario no ha iniciado sesión.
if not credentials:
    # La única página que puede ver es la de bienvenida para que inicie sesión.
    landing_page()

# Si SÍ hay credenciales, el usuario ya ha iniciado sesión.
else:
    # --- !! INICIO DE LA CORRECCIÓN !! ---
    # Configurar la API de Gemini y crear el modelo una sola vez aquí.
    # Así estará disponible para todas las páginas.
    try:
        genai.configure(api_key=st.secrets["GEMINI_API_KEY"])
        # Asegúrate de que tienes una secret llamada "GEMINI_API_KEY" en Streamlit Cloud
        model = genai.GenerativeModel('gemini-1.5-pro-latest') 
    except Exception as e:
        st.error(f"Error al configurar la API de Gemini. Verifica tu 'GEMINI_API_KEY' en los secrets. Detalle: {e}")
        st.stop()
    # --- FIN DE LA CORRECCIÓN ---

    # Ahora que sabemos que está dentro, miramos en qué página quiere estar.
    # Si acaba de iniciar sesión, su 'page' será 'landing', así que lo llevamos
    # a la selección de proyectos.
    if st.session_state.page == 'landing' or st.session_state.page == 'project_selection':
        project_selection_page()
    
    elif st.session_state.page == 'phase_1':
        # Pasamos el objeto 'model' a la función de la página
        phase_1_page(model)
        
    elif st.session_state.page == 'phase_1_results':
        # Pasamos el objeto 'model' a la función de la página
        phase_1_results_page(model)

    elif st.session_state.page == 'phase_2':
        # Pasamos el objeto 'model' a la función de la página
        phase_2_page(model)

    elif st.session_state.page == 'phase_3':
        # Pasamos el objeto 'model' a la función de la página
        phase_3_page(model)
        
    elif st.session_state.page == 'phase_4': # <-- AÑADE ESTE BLOQUE
        # Pasamos el objeto 'model' a la función de la página
        phase_4_page(model)
