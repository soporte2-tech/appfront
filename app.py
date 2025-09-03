import streamlit as st

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(
    page_title="Asistente de Licitaciones AI",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# --- INICIALIZACIÓN DEL ESTADO DE LA PÁGINA ---
if 'page' not in st.session_state:
    st.session_state.page = 'landing'

# --- FUNCIONES DE NAVEGACIÓN ---
def go_to_phases():
    st.session_state.page = 'phases'

def go_to_landing():
    st.session_state.page = 'landing'

# =============================================================================
#                              PÁGINA 1: LANDING PAGE
# =============================================================================
def landing_page():
    col1, col_center, col3 = st.columns([1, 2, 1])
    with col_center:
        st.write(""); st.write(""); st.write("")
        inner_col1, inner_col2, inner_col3 = st.columns([1, 1, 1])
        with inner_col2:
            logo_url = "https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png"
            st.image(logo_url, width=150)
        st.write("")
        st.markdown("<h1 style='text-align: center;'>Asistente Inteligente para Memorias Técnicas</h1>", unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center;'>Optimiza y acelera la creación de tus propuestas de licitación</h3>", unsafe_allow_html=True)
        st.write(""); st.write("")
        btn_col1, btn_col2, btn_col3 = st.columns([2, 1.5, 2])
        with btn_col2:
            st.button("¡Vamos allá!", on_click=go_to_phases, type="primary", use_container_width=True)

# =============================================================================
#                          PÁGINA 2: SELECCIÓN DE FASES
# =============================================================================
def phases_page():
    # --- CABECERA ---
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

    # --- Las tres cajas de las fases ---
    col1, col2, col3 = st.columns(3, gap="large")
    with col1:
        with st.container(border=True):
            st.subheader("FASE 1: Análisis y Estructura")
            st.write("Prepara los documentos base y define el esqueleto de la memoria técnica.")
            st.write("")
            if st.button("Iniciar Fase 1", type="primary", use_container_width=True):
                st.success("Cargando Fase 1...")
    with col2:
        with st.container(border=True):
            st.subheader("FASE 2: Redacción Asistida")
            st.write("Genera los borradores iniciales de contenido para cada apartado.")
            st.write("")
            if st.button("Iniciar Fase 2", type="primary", use_container_width=True):
                st.info("La Fase 2 estará disponible próximamente.")
    with col3:
        with st.container(border=True):
            st.subheader("FASE 3: Revisión y Exportación")
            st.write("Pule el documento final, valida requisitos y expórtalo a Word.")
            st.write("")
            if st.button("Iniciar Fase 3", type="primary", use_container_width=True):
                st.info("La Fase 3 estará disponible próximamente.")
    
    # --- BOTÓN DE VOLVER (MOVIDO Y CENTRADO AQUÍ) ---
    st.write("") # Espacio vertical
    st.markdown("---") # Línea divisoria

    # Columnas para centrar el botón de volver
    _, col_back_center, _ = st.columns([2.5, 1, 2.5])
    with col_back_center:
        st.button("← Volver a Inicio", on_click=go_to_landing, use_container_width=True)

# --- LÓGICA PRINCIPAL (ROUTER) ---
if st.session_state.page == 'landing':
    landing_page()
elif st.session_state.page == 'phases':
    phases_page()
