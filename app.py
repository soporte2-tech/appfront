import streamlit as st

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Asistente de Licitaciones AI",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- NUEVA CABECERA CON HTML FLEXBOX ---
# Este método es universal y no depende de la versión de Streamlit

logo_url = "https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png"

st.markdown(f"""
<div style="display: flex; align-items: center; justify-content: flex-start;">
    
    <!-- Columna del Logo -->
    <div style="flex: 1; margin-right: 20px;">
        <img src="{logo_url}" width="120">
    </div>
    
    <!-- Columna del Texto -->
    <div style="flex: 4;">
        <h1 style="margin: 0; padding: 0;">Asistente Inteligente para Memorias Técnicas</h1>
        <p style="margin: 0; padding: 0;">Optimiza y acelera la creación de tus propuestas de licitación</p>
    </div>

</div>
""", unsafe_allow_html=True)


# Añadimos una línea divisoria para separar claramente la cabecera del contenido
st.markdown("---")

# --- SELECCIÓN DE FASES ---
# Creamos tres columnas para los "cuadrados interactivos"
col1, col2, col3 = st.columns(3, gap="large")

# --- FASE 1: Análisis y Estructura ---
with col1:
    with st.container(border=True):
        st.subheader("FASE 1: Análisis y Estructura")
        st.markdown("""
        **Objetivo:** Preparar toda la información base y definir el esqueleto de la memoria técnica.

        - **Análisis de Documentos:** Sube los pliegos y la plantilla.
        - **Estructura Inteligente:** La IA propone una estructura optimizada basada en los documentos.
        - **Guion Estratégico:** Se genera un Word con preguntas clave para guiar la redacción.
        """)
        st.write("")
        if st.button("Iniciar Fase 1", type="primary", use_container_width=True):
            st.success("Navegando a la Fase 1...")

# --- FASE 2: Redacción Asistida ---
with col2:
    with st.container(border=True):
        st.subheader("FASE 2: Redacción Asistida")
        st.markdown("""
        **Objetivo:** Generar los borradores iniciales de contenido para cada apartado de la memoria.

        - **Contexto Empresarial:** Aporta información sobre tu empresa para personalizar las respuestas.
        - **Generación de Borradores:** La IA redacta el contenido para cada sección siguiendo el guion estratégico.
        - **Iteración y Mejora:** Revisa y solicita mejoras en los textos generados.
        """)
        st.write("")
        if st.button("Iniciar Fase 2", type="primary", use_container_width=True):
            st.info("La Fase 2 estará disponible próximamente.")

# --- FASE 3: Revisión y Exportación ---
with col3:
    with st.container(border=True):
        st.subheader("FASE 3: Revisión y Exportación")
        st.markdown("""
        **Objetivo:** Pulir el documento final, asegurar la coherencia y exportarlo en el formato requerido.

        - **Revisión Final:** Realiza una última lectura y ajuste fino del documento completo.
        - **Validación de Requisitos:** Un checklist final para asegurar que se cumple con todo lo exigido en los pliegos.
        - **Exportación a Word:** Descarga la memoria técnica final en formato `.docx`, lista para presentar.
        """)
        st.write("")
        if st.button("Iniciar Fase 3", type="primary", use_container_width=True):
            st.info("La Fase 3 estará disponible próximamente.")
