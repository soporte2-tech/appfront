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
    # --- CABECERA RESTAURADA ---
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
            # --- CAMBIO: Usamos on_click en lugar de if ---
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
        # --- CAMBIO: Usamos on_click en lugar de if ---
        st.button("← Volver a Inicio", on_click=go_to_landing, use_container_width=True)


# =============================================================================
#                           PÁGINA 3: FASE 1
# =============================================================================
def phase_1_page():
    # --- CABECERA ---
    st.markdown("<h3>FASE 1: Análisis y Estructura</h3>", unsafe_allow_html=True)
    st.markdown("Carga los documentos base para que la IA genere y valide la estructura de la memoria técnica.")
    st.markdown("---")
    
    # --- PASO 1: CARGA DE DOCUMENTOS ---
    with st.container(border=True):
        st.subheader("PASO 1: Carga de Documentos")
        has_template = st.radio("¿Dispones de una plantilla?", ("No", "Sí"), horizontal=True, key="template_radio")
        if has_template == 'Sí':
            uploaded_template = st.file_uploader("Sube tu plantilla (DOCX/PDF)", type=['docx', 'pdf'], key="template_uploader")
        
        uploaded_pliegos = st.file_uploader("Sube los Pliegos (DOCX/PDF)", type=['docx', 'pdf'], accept_multiple_files=True, key="pliegos_uploader")

    # --- PASO 2: GENERACIÓN ---
    st.write("")
    if st.button("Generar Estructura", type="primary", use_container_width=True):
        if not uploaded_pliegos:
            st.warning("Por favor, sube al menos un archivo de Pliegos.")
        else:
            with st.status("Analizando documentos...", expanded=True) as status:
                st.write("Llamando a la IA para analizar los documentos...")
                st.session_state.generated_structure = {
                    "estructura_memoria": [{"apartado": "1. Análisis", "subapartados": ["1.1. Contexto", "1.2. DAFO"]}],
                    "matices_desarrollo": [{"apartado": "1. Análisis", "subapartado": "1.1. Contexto", "indicaciones": "Descripción..."}]
                }
                status.update(label="¡Análisis completado!", state="complete")
            st.success("Estructura generada con éxito. Por favor, revísala a continuación.")
    
    # --- PASO 3: VALIDACIÓN Y RESULTADO ---
    if 'generated_structure' in st.session_state:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("PASO 2: Validación de la Estructura")
            st.json(st.session_state.generated_structure['estructura_memoria'])
            
            with st.expander("Ver detalles y matices de la estructura"):
                 st.json(st.session_state.generated_structure['matices_desarrollo'])
            
            feedback = st.text_area("Si necesitas cambios, indícalos aquí para regenerar la estructura:", key="feedback_area")

            col_val_1, col_val_2 = st.columns(2)
            with col_val_1:
                if st.button("Regenerar con Feedback", use_container_width=True, disabled=not feedback):
                    st.info("Funcionalidad de regeneración pendiente.")
            with col_val_2:
                if st.button("Aceptar y Generar Guion →", type="primary", use_container_width=True):
                    with st.status("Generando guion estratégico...", expanded=True) as status:
                        st.write("Llamando a la IA para crear las preguntas guía...")
                        fake_word_file = b"Contenido simulado del documento Word."
                        st.session_state.word_file = fake_word_file
                        status.update(label="¡Guion generado!", state="complete")
                    st.success("¡Documento Word listo para descargar!")

    if 'word_file' in st.session_state:
        st.markdown("---")
        with st.container(border=True):
            st.subheader("PASO 3: Descarga del Resultado")
            st.download_button(
                label="📥 Descargar Guion Estratégico (.docx)",
                data=st.session_state.word_file,
                file_name="guion_estrategico.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True
            )

    # --- BOTÓN DE VOLVER (MOVIDO Y CENTRADO AQUÍ) ---
    st.write("")
    st.markdown("---")
    _, col_back_center, _ = st.columns([2.5, 1, 2.5])
     with col_back_center:
        # --- CAMBIO: Usamos on_click y la nueva función de callback ---
        st.button("← Volver al Menú de Fases", on_click=back_to_phases_and_cleanup, use_container_width=True, key="back_to_menu")
        
# --- LÓGICA PRINCIPAL (ROUTER) ---
if st.session_state.page == 'landing':
    landing_page()
elif st.session_state.page == 'phases':
    phases_page()
elif st.session_state.page == 'phase_1':
    phase_1_page()
