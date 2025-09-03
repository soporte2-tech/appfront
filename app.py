import streamlit as st

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Asistente de Licitaciones AI",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- TÍTULO Y LOGO DE LA EMPRESA ---
col_logo1, col_logo2, col_logo3 = st.columns([1, 2, 1])

with col_logo2:
    # Creamos columnas DENTRO de la columna central para centrar la imagen
    inner_col1, inner_col2, inner_col3 = st.columns([1, 1, 1])
    with inner_col2:
        logo_url = "https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png"
        st.image(logo_url, width=150)

    # Centramos el texto usando st.markdown con estilo CSS
    st.markdown("<h1 style='text-align: center;'>Asistente Inteligente para Memorias Técnicas</h1>", unsafe_allow_html=True)
    st.markdown("<h3 style='text-align: center;'>Optimiza y acelera la creación de tus propuestas de licitación</h3>", unsafe_allow_html=True)


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
