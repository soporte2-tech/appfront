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

# =============================================================================
#           BLOQUE COMPLETO DE CONFIGURACIÓN Y FUNCIONES DE DRIVE
# =============================================================================


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


    1. Investiga cuántas páginas tiene que durar este apartado viendo lo que pone en los archivos que empiezan por la palabra "Pliego" (que dicen esos Pliegos sobre la duración del contenido) y "Memoria de ejemplo" (cuánto le duró la redacción a la persona, en caso de que exista claro). Entiende esa longitud y decide cuántas palabras tiene que haber por prompt para llegar a esa longitud.
    2. Investiga en los archivos del "Pliego" lo que se pide en ese apartado y dividelo en varios prompts para poder llegar al objetivo. Detalla mucho contexto en cada uno para que no haya sorpresas.
    3. Una vez ya sabes cuántas palabras tendrán los prompts, complementa el contenido de cada prompt con el CONTEXTO ADICIONAL que te proporciono. Este contexto incluye el guion borrador ya creado y la documentación de apoyo. Úsalo como base principal para dar forma a la propuesta de contenido.Intenta siempre usar un contenidio de la empresa real, pero si en la documentación o el mensaje inicial que se te dió no hay nada para llegar a ese objetivo.
    4. Añade en los prompts siempre la libertad para que referencien algo mencionado antes (menos de los Pliegos en exceso, que queda cantoso), mostrando así una coherencia y un humanismo. Menciona también que debe parecer humana la redacción. El objetivo es que sea fácil de leer y que resulte amena la lectura.
    5. Pide que se tenga en cuenta lo que se ha dicho antes tanto en el apartado como en general para evitar incongruencias. Añade referencias a lo que se ha dicho en otros párrafos.
    5.1 Está prohibido poner explícitamente algo de cómo ha sido la estructura o que hay referencias de prompts como "(referencia a PROMPT_1_1_B)". Si tienes que poner alguna referencia de algún sitio pon el apartado. Si no sabes que apartado es, opta por no poner nada de la referencia. No pueden detectar que este trabajo ha sido realizado con IA.
    6. No dudes en añadir tablas que resuman el contenido. Debes usar bullet points y listas para dar las ideas de una manera más clara para que el lector se sienta cómodo al leerlo. Lo ideal es que haya un número coherente de tablas, listados y elementos htmls sin resultar repetitivo. Siempre siguiendo un balance de 75% texto normal y 25% tablas, elementos gráficos html y listas fáciles de ver.
    7. Evita las conclusiones si van a ser redundantes. Suelen ser un sintoma de que se usa IA, así que saltatelas o no las empieces con expresiones como 'En definitiva' o 'En conclusión'. El objetivo es ser ameno y directo, y este tipo de secciones impiden llegar a ese objetivo.
    8. Finalmente, si consideras que la sección se podría resumir con un buen elemento visual (como podrían ser secciones en las cuáles hables de varias cosas y sea necesario un resumen visual) crea un prompt específico en HTML que resuma todo lo que se ha visto. Ten en cuenta que ese elemento será tratado en python y que por ello debe salir muy bien preparado, ya que no se podrá editar bajo ningún concepto. Asume esa presión y haz que salga perfecto en esa versión inicial. Piensa que de ese html se sacará una captura png y se pegará en un Word, haz que el html entre en un espacio reducido horizontal. Usa la letra Urbansit y estos colores #0046C6 #EDE646 #32CFAA #C2D1F2 #EB0045 y que no posean emoticonos para facilitar su creación . Haz diseños minimalistas y muy visuales. Poco texto y explicaciones muy visuales. No pongas contenido a pie de página de la empresa diciendo cosas redundantes. El objetivo del HTML es hacer más bonita la presentación, aportar información y asentar conceptos.
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


    {{
      "apartado_referencia": "El título del apartado principal que te he proporcionado (ej: 2. Solución Técnica Propuesta)",
      "subapartado_referencia": "El título del subapartado que te he proporcionado (ej: 2.1. Metodología de Trabajo)",
      "prompt_id": "Un identificador único para el prompt (ej: PROMPT_2_1_A)(Si es un HTML se debe agregar "HTML_VISUAL" al id (ej: PROMPT_2_1_1_HTML_VISUAL))",
      "prompt_para_asistente": "La pregunta o instrucción específica y detallada para el asistente (ej: )."
    }}


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

# =============================================================================
#           VERSIÓN DEFINITIVA DE phase_1_page()
# =============================================================================

def phase_1_page():
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

    # 1. Buscamos o creamos la subcarpeta 'Pliegos' y obtenemos su ID
    pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
    
    # 2. Buscamos los archivos DENTRO de esa subcarpeta 'Pliegos'
    document_files = get_files_in_project(service, pliegos_folder_id)
    
    # 3. Mostramos SOLO los archivos encontrados en 'Pliegos'
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
                            # 4. Guardamos los nuevos archivos DENTRO de la subcarpeta 'Pliegos'
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
        if st.button("Analizar Archivos y Generar Nuevo Índice", type="primary", use_container_width=True, disabled=not document_files):
            with st.spinner("Descargando archivos de 'Pliegos' y analizando..."):
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

    st.write("")
    st.markdown("---")
    st.button("← Volver a Selección de Proyecto", on_click=back_to_project_selection_and_cleanup, use_container_width=True, key="back_to_projects")
# =============================================================================
#           VERSIÓN FINAL Y COMPLETA DE phase_1_results_page()
# =============================================================================

# =============================================================================
#           REEMPLAZA phase_1_results_page POR ESTA VERSIÓN COMPLETA
# =============================================================================

def phase_1_results_page():
    """Página para revisar, regenerar y ACEPTAR el índice para pasar a Fase 2."""
    st.markdown("<h3>FASE 1: Revisión de Resultados</h3>", unsafe_allow_html=True)
    st.markdown("Revisa y ajusta el índice hasta que sea perfecto. Cuando esté listo, pasa a la siguiente fase para generar el contenido de cada apartado.")
    st.markdown("---")
    st.button("← Volver a la gestión de archivos", on_click=go_to_phase1)

    if 'generated_structure' not in st.session_state or not st.session_state.generated_structure:
        st.warning("No se ha generado ninguna estructura.")
        return

    # --- FUNCIÓN INTERNA COMPLETA ---
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
                
                if st.session_state.get('uploaded_pliegos'):
                    service = st.session_state.drive_service
                    for file_info in st.session_state.uploaded_pliegos:
                        file_content_bytes = download_file_from_drive(service, file_info['id'])
                        contenido_ia_regeneracion.append({
                            "mime_type": file_info['mimeType'],
                            "data": file_content_bytes.getvalue()
                        })

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
    # --- FIN DE LA FUNCIÓN INTERNA ---

    with st.container(border=True):
        mostrar_indice_desplegable(st.session_state.generated_structure.get('estructura_memoria'))
        st.markdown("---")
        st.subheader("Validación y Siguiente Paso")
        
        st.text_area("Si necesitas cambios, indícalos aquí:", key="feedback_area", placeholder="Ej: 'Añade un subapartado 1.3 sobre riesgos.'")
        
        col_val_1, col_val_2 = st.columns(2)
        with col_val_1:
            st.button("Regenerar con Feedback", on_click=handle_regeneration, use_container_width=True, disabled=not st.session_state.get("feedback_area"))

        with col_val_2:
            if st.button("Aceptar Índice y Pasar a Fase 2 →", type="primary", use_container_width=True):
                with st.spinner("Guardando índice final en Drive..."):
                    try:
                        service = st.session_state.drive_service
                        project_folder_id = st.session_state.selected_project['id']
                        docs_app_folder_id = find_or_create_folder(service, "Documentos aplicación", parent_id=project_folder_id)

                        indice_final = st.session_state.generated_structure
                        json_bytes = json.dumps(indice_final, indent=2).encode('utf-8')
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
                        st.error(f"Ocurrió un error al guardar el índice: {e}")


#           VERSIÓN DEFINITIVA de phase_2_page (CON TODA LA LÓGICA)
# =============================================================================
def phase_2_page():
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
                st.rerun() # Refrescamos para que el resto de la página cargue con el índice
            else:
                st.warning("No se ha encontrado un índice guardado. Por favor, vuelve a la Fase 1 para generar uno.")
                if st.button("← Ir a Fase 1"): go_to_phase1(); st.rerun()
                return
        except Exception as e:
            st.error(f"Error al cargar el índice desde Drive: {e}")
            return
    matices = st.session_state.generated_structure.get('matices_desarrollo', [])
    
    # --- BUSCAR CARPETAS Y ARCHIVOS ---
    with st.spinner("Sincronizando con Google Drive..."):
        pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
        guiones_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
        # La carpeta 'Contexto empresa' se sigue creando si no existe, pero ya no la usamos para subir archivos aquí.
        contexto_folder_id = find_or_create_folder(service, "Contexto empresa", parent_id=project_folder_id)
        
        pliegos_en_drive = get_files_in_project(service, pliegos_folder_id)
        
        # <-- CAMBIO: Ya no listamos archivos, sino las CARPETAS de cada subapartado
        query_subcarpetas = f"'{guiones_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        response_subcarpetas = service.files().list(q=query_subcarpetas, spaces='drive', fields='files(id, name)').execute()
        carpetas_de_guiones_existentes = {f['name']: f['id'] for f in response_subcarpetas.get('files', [])}

    # --- LÓGICA DE ACCIONES (GENERAR Y RE-GENERAR) ---
    def ejecutar_generacion(titulo, indicaciones):
        """Función para la generación inicial de un borrador."""
        # Limpiamos el título para que sea un nombre de archivo/carpeta válido
        nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", titulo)
        nombre_archivo = nombre_limpio + ".docx"
        
        with st.spinner(f"Generando borrador para '{titulo}'..."):
            try:
                # 1. Crear la carpeta específica para este subapartado
                subapartado_guion_folder_id = find_or_create_folder(service, nombre_limpio, parent_id=guiones_folder_id)

                # 2. Preparamos el contenido para la IA
                contenido_ia = [PROMPT_PREGUNTAS_TECNICAS_INDIVIDUAL]
                contenido_ia.append("--- INDICACIONES PARA ESTE APARTADO ---\n" + json.dumps(indicaciones, indent=2))
                
                # Añadimos los pliegos
                for file_info in pliegos_en_drive:
                    file_content_bytes = download_file_from_drive(service, file_info['id'])
                    contenido_ia.append({"mime_type": file_info['mimeType'], "data": file_content_bytes.getvalue()})
                
                # Añadimos la documentación de apoyo si existe
                doc_extra_key = f"upload_{titulo}"
                if doc_extra_key in st.session_state and st.session_state[doc_extra_key]:
                    doc_extra = st.session_state[doc_extra_key]
                    contenido_ia.append("--- DOCUMENTACIÓN DE APOYO ADICIONAL ---\n")
                    contenido_ia.append({"mime_type": doc_extra.type, "data": doc_extra.getvalue()})
                    # 3. Guardamos el doc de apoyo en la NUEVA carpeta del subapartado
                    upload_file_to_drive(service, doc_extra, subapartado_guion_folder_id)

                # Llamada a la IA
                response = model.generate_content(contenido_ia)
                
                # Creación del DOCX
                documento = docx.Document()
                agregar_markdown_a_word(documento, response.text)
                doc_io = io.BytesIO()
                documento.save(doc_io)
                word_file_obj = io.BytesIO(doc_io.getvalue())
                word_file_obj.name = nombre_archivo
                word_file_obj.type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                
                # 4. Guardamos el guion DOCX en la NUEVA carpeta del subapartado
                upload_file_to_drive(service, word_file_obj, subapartado_guion_folder_id)
                
                st.toast(f"Borrador para '{titulo}' generado y guardado en su carpeta.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al generar '{titulo}': {e}")

    def ejecutar_regeneracion(titulo, file_id_borrador):
        """Función para la re-generación con feedback."""
        nombre_archivo = re.sub(r'[\\/*?:"<>|]', "", titulo) + ".docx"
        with st.spinner(f"Re-generando '{titulo}' con feedback de Drive..."):
            try:
                # 1. Obtener la carpeta padre del archivo ANTES de borrarlo
                file_metadata = service.files().get(fileId=file_id_borrador, fields='parents').execute()
                parent_folder_id = file_metadata.get('parents')[0] if file_metadata.get('parents') else None
                if not parent_folder_id:
                    st.error("No se pudo encontrar la carpeta del guion original. Operación cancelada.")
                    return

                # Descargamos el .docx de Drive y extraemos su texto
                doc_bytes = download_file_from_drive(service, file_id_borrador)
                documento_revisado = docx.Document(doc_bytes)
                texto_revisado = "\n".join([p.text for p in documento_revisado.paragraphs])
                
                # Preparamos el contenido para la IA
                contenido_ia = [PROMPT_CONSULTOR_REVISION]
                contenido_ia.append("--- BORRADOR ORIGINAL / TEXTO REVISADO Y COMENTARIOS ---\n" + texto_revisado)
                
                # Añadimos los pliegos para contexto estratégico
                for file_info in pliegos_en_drive:
                    file_content_bytes = download_file_from_drive(service, file_info['id'])
                    contenido_ia.append({"mime_type": file_info['mimeType'], "data": file_content_bytes.getvalue()})

                # Llamada a la IA
                response = model.generate_content(contenido_ia)
                
                # Creación del nuevo DOCX
                documento = docx.Document()
                agregar_markdown_a_word(documento, response.text)
                doc_io = io.BytesIO()
                documento.save(doc_io)
                word_file_obj = io.BytesIO(doc_io.getvalue())
                word_file_obj.name = nombre_archivo
                word_file_obj.type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                
                # 2. Borramos el archivo antiguo y subimos el nuevo a la MISMA CARPETA PADRE
                delete_file_from_drive(service, file_id_borrador)
                upload_file_to_drive(service, word_file_obj, parent_folder_id)
                
                st.toast(f"Guion para '{titulo}' re-generado con éxito.")
                st.rerun()
            except Exception as e:
                st.error(f"Error al re-generar '{titulo}': {e}")
                
    def ejecutar_borrado(titulo, folder_id_to_delete):
        """Función para eliminar la carpeta de un guion y todo su contenido."""
        with st.spinner(f"Eliminando guion y contexto para '{titulo}'..."):
            try:
                # Usamos la función que ya tenemos, ya que en Drive las carpetas son un tipo de 'file'
                success = delete_file_from_drive(service, folder_id_to_delete)
                if success:
                    st.toast(f"Guion para '{titulo}' eliminado correctamente.")
                    st.rerun()
                else:
                    # El error específico ya se mostraría dentro de delete_file_from_drive
                    st.error(f"No se pudo completar la eliminación de '{titulo}'.")

            except Exception as e:
                st.error(f"Ocurrió un error inesperado al intentar borrar '{titulo}': {e}")


    # --- INTERFAZ DE GESTIÓN DE GUIONES ---
    st.subheader("Gestión de Guiones de Subapartados")

    for i, item in enumerate(matices):
        subapartado_titulo = item.get('subapartado')
        if not subapartado_titulo: continue
        
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
            col1, col2 = st.columns([1.5, 2])
            with col1:
                st.write(f"**{subapartado_titulo}**")

                if estado == "📄 Generado":
                    status_col, del_col = st.columns([3, 1])
                    status_col.caption(f"Estado: {estado}")
                    if del_col.button("🗑️", key=f"del_{i}", help="Eliminar guion y su carpeta en Drive"):
                        ejecutar_borrado(subapartado_titulo, subapartado_folder_id)
                else:
                    st.caption(f"Estado: {estado}")

                if estado == "⚪ No Generado":
                    st.file_uploader("Aportar documentación de apoyo", type=['pdf', 'docx', 'txt'], key=f"upload_{subapartado_titulo}", label_visibility="collapsed")

            with col2:
                btn_container = st.container()
                if estado == "📄 Generado" and file_info:
                    link = f"https://docs.google.com/document/d/{file_info['id']}/edit"
                    btn_container.link_button("Revisar en Drive", link, use_container_width=True)
                    if btn_container.button("Re-Generar con Feedback", key=f"regen_{i}", type="primary", use_container_width=True):
                        ejecutar_regeneracion(subapartado_titulo, file_info['id'])
                else:
                    if btn_container.button("Generar Borrador", key=f"gen_{i}", use_container_width=True):
                        indicaciones = next((m for m in matices if m['subapartado'] == subapartado_titulo), None)
                        ejecutar_generacion(subapartado_titulo, indicaciones)

    # --- AQUÍ EMPIEZA LA PARTE AÑADIDA ---
    # (Justo después de que termine el bucle for)
    st.markdown("---")
    # Botones de navegación al final de la página
    col_nav1, col_nav2 = st.columns(2)
    with col_nav1:
        st.button("← Volver a Revisión de Índice (F1)", on_click=go_to_phase1_results, use_container_width=True)
    with col_nav2:
        st.button("Ir a Plan de Prompts (F3) →", on_click=go_to_phase3, use_container_width=True)

# =============================================================================
#           NUEVA PÁGINA: FASE 3 - CENTRO DE MANDO DE PROMPTS (VERSIÓN FINAL COMPLETA)
# =============================================================================

def phase_3_page():
    """Página interactiva para generar el plan de prompts subapartado por subapartado."""
    st.markdown("<h3>FASE 3: Centro de Mando de Prompts</h3>", unsafe_allow_html=True)
    st.markdown("Selecciona para qué subapartados deseas generar un plan de prompts detallado. La IA utilizará los guiones y el contexto que preparaste en la Fase 2.")
    st.markdown("---")

    # --- SETUP ROBUSTO (COMO EN FASE 2) ---
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

    matices = st.session_state.generated_structure.get('matices_desarrollo', [])
    
    # --- CARGA DEL PLAN DE PROMPTS EXISTENTE ---
    prompt_plan_file_id = find_file_by_name(service, "plan_de_prompts.json", docs_app_folder_id)
    if 'prompt_plan' not in st.session_state or not prompt_plan_file_id:
        if prompt_plan_file_id:
            with st.spinner("Cargando plan de prompts existente..."):
                json_content_bytes = download_file_from_drive(service, prompt_plan_file_id).getvalue()
                st.session_state.prompt_plan = json.loads(json_content_bytes.decode('utf-8'))
        else:
            st.session_state.prompt_plan = {"plan_de_prompts": []}

    # --- FUNCIÓN INTERNA DE GENERACIÓN ---
    def handle_individual_generation(matiz_info):
        apartado_titulo = matiz_info.get("apartado", "N/A")
        subapartado_titulo = matiz_info.get("subapartado", "N/A")
        
        # Obtenemos el service y project_folder_id del scope superior
        service = st.session_state.drive_service
        project_folder_id = st.session_state.selected_project['id']
        docs_app_folder_id = find_or_create_folder(service, "Documentos aplicación", parent_id=project_folder_id)
        prompt_plan_file_id = find_file_by_name(service, "plan_de_prompts.json", docs_app_folder_id)

        with st.spinner(f"Generando prompts para: '{subapartado_titulo}'..."):
            try:
                guiones_main_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
                
                # 1. RECOLECTAR CONTEXTO DE FASE 2
                nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", subapartado_titulo)
                subapartado_folder_id = find_file_by_name(service, nombre_limpio, guiones_main_folder_id)
                
                contexto_adicional_str = ""
                if subapartado_folder_id:
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

                # 2. PREPARAR CONTENIDO PARA LA IA
                pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
                pliegos_files_info = get_files_in_project(service, pliegos_folder_id)
                pliegos_content_for_ia = [{"mime_type": f['mimeType'], "data": download_file_from_drive(service, f['id']).getvalue()} for f in pliegos_files_info]

                prompt_final = PROMPT_DESARROLLO.format(
                    apartado_titulo=apartado_titulo,
                    subapartado_titulo=subapartado_titulo,
                    indicaciones=matiz_info.get("indicaciones", ""),
                    contexto_adicional=contexto_adicional_str
                )

                contenido_ia = [prompt_final] + pliegos_content_for_ia
                generation_config = genai.GenerationConfig(response_mime_type="application/json")
                response = model.generate_content(contenido_ia, generation_config=generation_config)
                
                # 3. PROCESAR RESPUESTA Y ACTUALIZAR PLAN MAESTRO
                json_limpio_str = limpiar_respuesta_json(response.text)
                if json_limpio_str:
                    plan_parcial = json.loads(json_limpio_str)
                    nuevos_prompts = plan_parcial.get("plan_de_prompts", [])
                    
                    prompts_actuales = st.session_state.prompt_plan['plan_de_prompts']
                    prompts_filtrados = [p for p in prompts_actuales if p.get('subapartado_referencia') != subapartado_titulo]
                    st.session_state.prompt_plan['plan_de_prompts'] = prompts_filtrados + nuevos_prompts

                    # 4. GUARDAR PLAN MAESTRO ACTUALIZADO EN DRIVE
                    json_bytes = json.dumps(st.session_state.prompt_plan, indent=2, ensure_ascii=False).encode('utf-8')
                    mock_file_obj = io.BytesIO(json_bytes)
                    mock_file_obj.name = "plan_de_prompts.json"
                    mock_file_obj.type = "application/json"
                    
                    if prompt_plan_file_id: delete_file_from_drive(service, prompt_plan_file_id)
                    upload_file_to_drive(service, mock_file_obj, docs_app_folder_id)
                    
                    st.toast(f"Plan de prompts para '{subapartado_titulo}' generado y guardado.")

            except Exception as e:
                st.error(f"Error generando prompts para '{subapartado_titulo}': {e}")

    # --- INTERFAZ DE USUARIO MEJORADA ---
    with st.spinner("Verificando estado de los guiones de la Fase 2..."):
        guiones_main_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
        query_subcarpetas = f"'{guiones_main_folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        response_subcarpetas = service.files().list(q=query_subcarpetas, spaces='drive', fields='files(name)').execute()
        carpetas_de_guiones_generados = [f['name'] for f in response_subcarpetas.get('files', [])]

    for i, matiz in enumerate(matices):
        subapartado_titulo = matiz.get("subapartado")
        if not subapartado_titulo: continue

        nombre_limpio = re.sub(r'[\\/*?:"<>|]', "", subapartado_titulo)
        guion_generado = nombre_limpio in carpetas_de_guiones_generados
        prompts_existentes = [p for p in st.session_state.prompt_plan.get('plan_de_prompts', []) if p.get('subapartado_referencia') == subapartado_titulo]

        with st.container(border=True):
            col1, col2 = st.columns([2, 1])
            with col1:
                st.write(f"**{subapartado_titulo}**")
                if not guion_generado:
                    st.warning("⚠️ Guion no generado en Fase 2. No se puede crear un plan de prompts.")
                elif prompts_existentes:
                    st.success(f"✔️ Plan generado ({len(prompts_existentes)} prompts)")
                    with st.expander("Ver prompts generados"):
                        st.json(prompts_existentes)
                else:
                    st.info("⚪ Pendiente de generar plan de prompts")
            
            with col2:
                if prompts_existentes:
                    st.button("Re-generar Plan", key=f"gen_{i}", on_click=handle_individual_generation, args=(matiz,), use_container_width=True, type="secondary", disabled=not guion_generado)
                else:
                    st.button("Generar Plan de Prompts", key=f"gen_{i}", on_click=handle_individual_generation, args=(matiz,), use_container_width=True, type="primary", disabled=not guion_generado)

    st.markdown("---")
    if st.session_state.prompt_plan.get('plan_de_prompts'):
        json_total_bytes = json.dumps(st.session_state.prompt_plan, indent=2, ensure_ascii=False).encode('utf-8')
        st.download_button(
            label="📥 Descargar Plan de Prompts Completo (JSON)",
            data=json_total_bytes,
            file_name="plan_de_prompts.json",
            mime="application/json",
            use_container_width=True
        )

    st.button("← Volver al Centro de Mando (F2)", on_click=go_to_phase2, use_container_width=True)
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
    elif st.session_state.page == 'phase_2':
        phase_2_page()
    elif st.session_state.page == 'phase_3':  # <-- ESTA ES LA LÍNEA QUE FALTABA
        phase_3_page()                      # <-- Y ESTA TAMBIÉN
