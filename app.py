import streamlit as st

# --- CONFIGURACIÓN DE LA PÁGINA ---
# Usamos un layout ancho para aprovechar el espacio y le damos un título a la pestaña del navegador.
st.set_page_config(
    page_title="Asistente de Licitaciones AI",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- TÍTULO Y LOGO DE LA EMPRESA ---

# Creamos columnas para centrar el logo y el título en la pantalla
# El ratio [1, 2, 1] significa que la columna del medio es el doble de ancha que las de los lados.
col_logo1, col_logo2, col_logo3 = st.columns([1, 2, 1])

with col_logo2:
    # IMPORTANTE: Reemplaza la URL de abajo con la URL directa (raw) de tu logo en GitHub.
    # Para obtenerla, ve a la imagen en tu repositorio de GitHub y haz clic en "Download" o "Raw". Copia esa URL.
    logo_url = "https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png" # <-- REEMPLAZA ESTA URL
    st.image(logo_url, width=150) # Puedes ajustar el tamaño del logo con el parámetro 'width'

    st.title("Asistente Inteligente para Memorias Técnicas")
    st.markdown("### Optimiza y acelera la creación de tus propuestas de licitación")


st.markdown("---") # Una línea divisoria para separar secciones

# --- SELECCIÓN DE FASES ---

st.header("Selecciona una fase para comenzar")
st.write("") # Un poco de espacio vertical

# Creamos tres columnas para los "cuadrados interactivos"
col1, col2, col3 = st.columns(3, gap="large")

# --- FASE 1: Análisis y Estructura (Corresponde a tu FASE 0 del código) ---
with col1:
    with st.container(border=True): # El 'border=True' crea el efecto de "cuadrado" o tarjeta
        st.subheader("FASE 1: Análisis y Estructura")
        st.markdown("""
        **Objetivo:** Preparar toda la información base y definir el esqueleto de la memoria técnica.

        - **Análisis de Documentos:** Sube los pliegos y la plantilla.
        - **Estructura Inteligente:** La IA propone una estructura optimizada basada en los documentos.
        - **Guion Estratégico:** Se genera un Word con preguntas clave para guiar la redacción.
        """)
        st.write("") # Espacio
        if st.button("Iniciar Fase 1", type="primary", use_container_width=True):
            # Aquí irá la lógica para ejecutar la Fase 1 en el futuro
            st.success("Navegando a la Fase 1...")
            # st.switch_page("pages/fase1.py") # Ejemplo de cómo podrías navegar a otra página

# --- FASE 2: Redacción Asistida (Corresponde a tu FASE 1 y 2 del código) ---
with col2:
    with st.container(border=True):
        st.subheader("FASE 2: Redacción Asistida")
        st.markdown("""
        **Objetivo:** Generar los borradores iniciales de contenido para cada apartado de la memoria.

        - **Contexto Empresarial:** Aporta información sobre tu empresa para personalizar las respuestas.
        - **Generación de Borradores:** La IA redacta el contenido para cada sección siguiendo el guion estratégico.
        - **Iteración y Mejora:** Revisa y solicita mejoras en los textos generados.
        """)
        st.write("") # Espacio
        if st.button("Iniciar Fase 2", type="primary", use_container_width=True):
            # Aquí irá la lógica para ejecutar la Fase 2 en el futuro
            st.info("La Fase 2 estará disponible próximamente.")

# --- FASE 3: Revisión y Exportación (Corresponde a tu FASE 3 del código) ---
with col3:
    with st.container(border=True):
        st.subheader("FASE 3: Revisión y Exportación")
        st.markdown("""
        **Objetivo:** Pulir el documento final, asegurar la coherencia y exportarlo en el formato requerido.

        - **Revisión Final:** Realiza una última lectura y ajuste fino del documento completo.
        - **Validación de Requisitos:** Un checklist final para asegurar que se cumple con todo lo exigido en los pliegos.
        - **Exportación a Word:** Descarga la memoria técnica final en formato `.docx`, lista para presentar.
        """)
        st.write("") # Espacio
        if st.button("Iniciar Fase 3", type="primary", use_container_width=True):
            # Aquí irá la lógica para ejecutar la Fase 3 en el futuro
            st.info("La Fase 3 estará disponible próximamente.")
