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


# --- FUNCIONES DE INTERACCIÓN CON GOOGLE DRIVE ---

def find_or_create_folder(service, folder_name, parent_id=None, folder_id=None, retries=3):
    """Busca/crea una carpeta con reintentos. Si se da un folder_id, lo devuelve directamente."""
    
    if folder_id:
        return folder_id

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
        except TimeoutError:
            if attempt < retries - 1:
                st.toast(f"Timeout al conectar con Drive. Reintentando ({attempt + 1}/{retries-1})...")
                time.sleep(2) 
            else:
                st.error("No se pudo conectar con Google Drive después de varios intentos.")
                raise
        except Exception as e:
            st.error(f"Ocurrió un error inesperado con Google Drive: {e}")
            raise

def upload_file_to_drive(service, file_object, folder_id):
    """Sube un objeto de archivo a una carpeta de Drive."""
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
    
def send_gmail_notification(credentials, file_name, file_drive_link, user_email):
    """Envía una notificación por Gmail cuando un archivo está listo."""
    try:
        # Construimos el servicio de Gmail
        gmail_service = build('gmail', 'v1', credentials=credentials)
        
        # Obtenemos la información del usuario para personalizar el email
        oauth2_service = build('oauth2', 'v2', credentials=credentials)
        user_info = oauth2_service.userinfo().get().execute()
        user_name = user_info.get('given_name', 'Usuario') # Usamos el nombre de pila o 'Usuario' por defecto

        message = MIMEText(
            f"""
            <p>¡Hola, {user_name}!</p>
            <p>El guion estratégico para tu proyecto <b>"{file_name}"</b> ha sido generado con éxito.</p>
            <p>Puedes acceder a él, editarlo y compartirlo desde el siguiente enlace a Google Drive:</p>
            <p style="text-align: center; margin: 20px 0;">
                <a href="{file_drive_link}" style="font-size: 16px; font-weight: bold; color: #ffffff; background-color: #4285F4; padding: 12px 24px; border-radius: 5px; text-decoration: none;">
                    Abrir Guion en Google Drive
                </a>
            </p>
            <br>
            <p>¡Un saludo!</p>
            <p><em>Tu Asistente de Licitaciones AI</em></p>
            """,
            'html'
        )
        
        message['to'] = user_email
        message['from'] = "me" # "me" es un alias para la cuenta autenticada
        message['subject'] = f"✅ Tu Guion Estratégico para '{file_name}' está listo"
        
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        body = {'raw': raw_message}
        
        gmail_service.users().messages().send(userId='me', body=body).execute()
        st.toast("📧 Notificación por email enviada con éxito.")
    
    except HttpError as error:
        st.warning(f"No se pudo enviar la notificación por email: {error}.")
    except Exception as e:
        st.error(f"Ocurrió un error inesperado al enviar el email: {e}")
    
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

# =============================================================================
#           REEMPLAZA phase_2_page() POR ESTA VERSIÓN COMPLETA
# =============================================================================

# =============================================================================
#           VERSIÓN FINAL Y COMPLETA DE phase_2_page
# =============================================================================
# =============================================================================
#           VERSIÓN FINAL de phase_2_page CON SUB-CARPETA PARA GUIONES
# =============================================================================
# =============================================================================
#           VERSIÓN FINAL Y COMPLETA de phase_2_page (con la carpeta corregida)
# =============================================================================
# =============================================================================
#           VERSIÓN FINAL de phase_2_page (guarda docs de apoyo)
# =============================================================================
# =============================================================================
#           VERSIÓN AVANZADA de phase_2_page (CON ESTADOS Y RE-GENERACIÓN)
# =============================================================================
def phase_2_page():
    """Centro de mando para la generación y re-generación de guiones."""
    st.markdown("<h3>FASE 2: Centro de Mando de Guiones</h3>", unsafe_allow_html=True)
    st.markdown("Genera los borradores iniciales, revísalos en Drive y luego re-genéralos con el feedback incorporado.")
    st.markdown("---")

    # --- SETUP INICIAL ---
    if 'generated_structure' not in st.session_state:
        st.warning("No se ha cargado un índice. Volviendo a Fase 1.")
        if st.button("Ir a Fase 1"): go_to_phase1(); st.rerun()
        return

    service = st.session_state.drive_service
    project_folder_id = st.session_state.selected_project['id']
    matices = st.session_state.generated_structure.get('matices_desarrollo', [])
    
    # --- BUSCAR CARPETAS Y ARCHIVOS ---
    with st.spinner("Sincronizando con Google Drive..."):
        pliegos_folder_id = find_or_create_folder(service, "Pliegos", parent_id=project_folder_id)
        guiones_folder_id = find_or_create_folder(service, "Guiones de Subapartados", parent_id=project_folder_id)
        
        pliegos_en_drive = get_files_in_project(service, pliegos_folder_id)
        guiones_en_drive = get_files_in_project(service, guiones_folder_id)
        nombres_guiones_existentes = [f['name'] for f in guiones_en_drive]

    # --- INTERFAZ DE GESTIÓN DE GUIONES ---
    st.subheader("Gestión de Guiones de Subapartados")

    for i, item in enumerate(matices):
        subapartado_titulo = item.get('subapartado')
        if not subapartado_titulo: continue
        
        nombre_archivo_esperado = re.sub(r'[\\/*?:"<>|]', "", subapartado_titulo) + ".docx"
        
        # Determinamos el estado del guion
        estado = "⚪ No Generado"
        if nombre_archivo_esperado in nombres_guiones_existentes:
            estado = "📄 Generado"
            file_info = next((f for f in guiones_en_drive if f['name'] == nombre_archivo_esperado), None)
            
        with st.container(border=True):
            col1, col2, col3 = st.columns([4, 1, 2])
            with col1:
                st.write(f"**{subapartado_titulo}**")
                st.caption(f"Estado: {estado}")
            
            with col2:
                if estado == "📄 Generado":
                    link = f"https://docs.google.com/document/d/{file_info['id']}/edit"
                    st.link_button("Revisar en Drive", link)
            
            with col3:
                # --- Lógica de los botones de acción ---
                if estado == "⚪ No Generado":
                    if st.button("Generar Borrador", key=f"gen_{i}", use_container_width=True):
                        # (Aquí iría la lógica de la generación inicial que ya teníamos)
                        st.info("Lógica de generación inicial pendiente de conectar.")

                elif estado == "📄 Generado":
                    if st.button("Re-Generar con Feedback", key=f"regen_{i}", type="primary", use_container_width=True):
                        # (Aquí irá la lógica de re-generación con el nuevo prompt)
                        st.info("Lógica de re-generación pendiente de conectar.")

    st.markdown("---")
    # Botones de navegación al final de la página
    col_nav1, col_nav2, col_nav3 = st.columns(3)
    with col_nav1:
        st.button("← Volver a Revisión de Índice (F1)", on_click=go_to_phase1_results, use_container_width=True)
    with col_nav2:
        # Placeholder para un botón de "Generar todos"
        st.button("Generar Todos los Borradores", disabled=True, use_container_width=True)
    with col_nav3:
        st.button("Ir a Plan de Prompts (F3) →", on_click=go_to_phase3, use_container_width=True)
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
        
    # La página 'phases' ya no existe en este nuevo flujo, por eso no se incluye.
