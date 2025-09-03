import streamlit as st

# --- CONFIGURACIÓN DE LA PÁGINA ---
st.set_page_config(page_title="Asistente de Licitaciones AI", layout="wide", initial_sidebar_state="collapsed")

# --- INICIALIZACIÓN DEL ESTADO DE LA PÁGINA ---
if 'page' not in st.session_state:
    st.session_state.page = 'landing'

# --- FUNCIONES DE NAVEGÁCIÓN ---
def go_to_phases():
    st.session_state.page = 'phases'
def go_to_landing():
    st.session_state.page = 'landing'
def go_to_phase1():
    st.session_state.page = 'phase_1'

# --- FUNCIÓN DE CALLBACK PARA LIMPIAR Y VOLVER ---
def back_to_phases_and_cleanup():
    # Limpiamos el estado específico de la fase 1 al salir
    for key in ['generated_structure', 'word_file']:
        if key in st.session_state:
            del st.session_state[key]
    go_to_phases()


# =============================================================================
#                              PÁGINA 1: LANDING PAGE
# =============================================================================
def landing_page():
    col1, col_center, col3 = st.columns([1, 2, 1])
    with col_center:
        st.write("")
        inner_col1, inner_col2, inner_col3 = st.columns([1, 1, 1])
        with inner_col2:
            logo_url = "https://raw.githubusercontent.com/soporte2-tech/appfront/main/imagen.png"
            st.markdown(f'<div style="text-align: center;"><img src="{logo_url}" width="150"></div>', unsafe_allow_html=True)
        st.write("")
        st.markdown("<div style='text-align: center;'><h1>Asistente Inteligente para Memorias Técnicas</h1></div>", unsafe_allow_html=True)
        st.markdown("<div style='text-align: center;'><h3>Optimiza y acelera la creación de tus propuestas de licitación</h3></div>", unsafe_allow_html=True)
        st.write(""); st.write("")
        btn_col1, btn_col2, btn_col3 = st.columns([2, 1.5, 2])
        with btn_col2:
            st.button("¡Vamos allá!", on_click=go_to_phases, type="primary", use_container_width=True)

# =============================================================================
#                          PÁGINA 2: SELECCIÓN DE FASES
# =============================================================================
def phases_page():
    # --- CORRECCIÓN: CABECERA RESTAURADA Y CÓDIGO CORRECTAMENTE INDENTADO ---
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

    st.write(""); st.write("")
    _, col_back_center, _ = st.columns([2.5, 1, 2.5])
    with col_back_center:
        st.button("← Volver a Inicio", on_click=go_to_landing, use_container_width=True)

# =============================================================================
#                           PÁGINA 3: FASE 1
# =============================================================================
def phase_1_page():
    # ... (el código de esta página no necesita cambios)
    st.markdown("<h3>FASE 1: Análisis y Estructura</h3>", unsafe_allow_html=True)
    st.markdown("Carga los documentos base para que la IA genere y valide la estructura de la memoria técnica.")
    st.markdown("---")
    
    with st.container(border=True):
        st.subheader("PASO 1: Carga de Documentos")
        has_template = st.radio("¿Dispones de una plantilla?", ("No", "Sí"), horizontal=True, key="template_radio")
        if has_template == 'Sí':
            uploaded_template = st.file_uploader("Sube tu plantilla (DOCX/PDF)", type=['docx', 'pdf'], key="template_uploader")
        uploaded_pliegos = st.file_uploader("Sube los Pliegos (DOCX/PDF)", type=['docx', 'pdf'], accept_multiple_files=True, key="pliegos_uploader")
    
    st.write("")
    if st.button("Generar Estructura", type="primary", use_container_width=True):
        if not uploaded_pliegos:
            st.warning("Por favor, sube al menos un archivo de Pliegos.")
        else:
            # Lógica de generación...
            pass

    if 'generated_structure' in st.session_state:
        # Lógica de validación...
        pass
    
    if 'word_file' in st.session_state:
        # Lógica de descarga...
        pass

    st.write("")
    st.markdown("---")
    _, col_back_center, _ = st.columns([2.5, 1, 2.5])
    with col_back_center:
        st.button("← Volver al Menú de Fases", on_click=back_to_phases_and_cleanup, use_container_width=True, key="back_to_menu")

# --- LÓGICA PRINCIPAL (ROUTER) ---
if st.session_state.page == 'landing':
    landing_page()
elif st.session_state.page == 'phases':
    phases_page()
elif st.session_state.page == 'phase_1':
    phase_1_page()
