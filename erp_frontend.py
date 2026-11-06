"""Interfaz del ERP académico. Ejecutar: streamlit run erp_frontend.py."""
import base64
import html
import io
import json
import math
import uuid

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import graphviz
import folium
from streamlit_folium import st_folium
from geopy.geocoders import Nominatim

from erp_api_client import APIClient

st.set_page_config(page_title="ERP AgTech · Gestión integral", page_icon="🌱", layout="wide")

st.markdown("""<style>
.block-container {max-width:1440px; padding-top:5rem; padding-bottom:3rem;}
.agtech-hero {background:linear-gradient(120deg,#123d35,#176751);color:#fff;
 padding:1.65rem 1.9rem;border-radius:18px;margin-bottom:1.5rem;}
.agtech-hero h1 {color:#fff;font-size:clamp(1.8rem,3vw,2.6rem);padding:.25rem 0 .5rem;}
.agtech-hero p {color:#e1f3eb;max-width:860px;margin:0;line-height:1.6;}
.agtech-eyebrow {font-size:.76rem;font-weight:700;letter-spacing:.11em;color:#b5e9d3;}
.agtech-hero--compact {padding:1rem 1.4rem;border-radius:14px;margin-bottom:.6rem;}
.agtech-hero--compact h1 {font-size:clamp(1.65rem,2.5vw,2rem);padding:0 0 .35rem;}
.agtech-hero--compact .agtech-eyebrow {display:none;}
.block-container h3 {font-size:1.25rem;line-height:1.4;padding-top:.35rem;}
.agtech-insight {border-left:4px solid #3980a2;border-radius:10px;padding:1rem 1.1rem;
 background:#edf6fb;color:#193c50;margin:.25rem 0 .8rem;}
.agtech-insight--success {border-color:#13866b;background:#eaf6f0;color:#164c3e;}
.agtech-insight--warning {border-color:#b87818;background:#fff6e5;color:#654516;}
.agtech-insight strong,.agtech-empty strong {display:block;font-size:1.05rem;margin-bottom:.25rem;}
.agtech-insight p,.agtech-empty p {margin:0;line-height:1.55;font-size:.94rem;}
.agtech-empty {border:1px dashed #81958e70;border-radius:12px;padding:1.4rem;margin:.5rem 0 1rem;}
.agtech-task-icon {font-size:1.55rem;line-height:1.2;margin-bottom:.5rem;}
[data-testid="stMetric"] {border:1px solid #879a8e44;border-radius:14px;padding:1rem;}
[data-testid="stMetricLabel"] {height:auto;min-height:1.4rem;}
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"], [data-testid="stMetricLabel"] p {white-space:normal;overflow:visible;text-overflow:clip;}
[data-testid="stMetricValue"] {font-size:clamp(1.35rem,2.1vw,2rem);}
[data-testid="stMetricValue"] > div {white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere;}
[data-testid="stSidebar"] h1 {font-size:1.65rem;}
.st-key-navegacion_principal {gap:.25rem;}
.st-key-navegacion_principal button {justify-content:flex-start;text-align:left;}
.st-key-navegacion_principal button > div {justify-content:flex-start;padding-left:.75rem;}
.st-key-navegacion_principal button p {text-align:left;}
.st-key-navegacion_principal [data-testid="stMarkdownContainer"] {margin-bottom:0;}
.st-key-navegacion_principal .agtech-nav-group {font-size:.72rem;font-weight:700;
 letter-spacing:.09em;text-transform:uppercase;opacity:.75;padding:.6rem 0 .15rem;margin:0;}
.stButton button,.stDownloadButton button {border-radius:9px;min-height:2.6rem;}
.stTabs [role="tab"] {font-weight:600;}
@media(max-width:640px){.block-container{padding:5rem 1rem 2rem;}.agtech-hero{padding:1.2rem;}}
</style>""", unsafe_allow_html=True)

for key, value in {"autenticado": False, "token": "", "username": "", "permisos": [],
                   "operador_lat": 19.5119, "operador_lon": -98.8829,
                   "nueva_sede_lat": 19.5119, "nueva_sede_lon": -98.8829}.items():
    st.session_state.setdefault(key, value)
if "api_client" not in st.session_state:
    st.session_state.api_client = APIClient()
if "posicion_cajero" not in st.session_state:
    # Esta pareja no pertenece a un widget: se conserva al cambiar de módulo.
    st.session_state.posicion_cajero = (st.session_state.operador_lat, st.session_state.operador_lon)


def reiniciar_mapa_cajero():
    # Una clave nueva descarta last_clicked del mapa anterior al editar o centrar.
    st.session_state.mapa_cajero_revision = st.session_state.get("mapa_cajero_revision", 0) + 1


def fijar_posicion_cajero(latitud, longitud):
    st.session_state.posicion_cajero = (float(latitud), float(longitud))
    st.session_state.operador_lat = float(latitud)
    st.session_state.operador_lon = float(longitud)
    reiniciar_mapa_cajero()


def cambiar_coordenadas_cajero():
    fijar_posicion_cajero(st.session_state.operador_lat, st.session_state.operador_lon)


def reiniciar_mapa_sede():
    st.session_state.mapa_sede_revision = st.session_state.get("mapa_sede_revision", 0) + 1


def request(method, path, *, quiet=False, **kwargs):
    """Un solo punto para límites de espera, autenticación y errores visibles."""
    try:
        response = st.session_state.api_client.request(method, path, token=st.session_state.token, **kwargs)
    except Exception:
        if not quiet:
            st.error("No se pudo contactar al servicio. Revisa la conexión e inténtalo de nuevo.")
        return None
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", "La operación no se pudo completar.")
            if isinstance(detail, list):
                detail = "; ".join(f"{'.'.join(str(v) for v in d.get('loc', [])[1:])}: {d.get('msg', '')}" for d in detail)
        except Exception:
            detail = "Error del servicio; la operación no se completó."
        if not quiet:
            st.error(f"{response.status_code}: {detail}")
        if response.status_code == 401 and st.session_state.autenticado:
            st.session_state.autenticado = False
            st.session_state.token = ""
            st.warning("La sesión terminó. Vuelve a iniciar sesión.")
            st.rerun()
        return None
    return response


def api(method, path, default=None, **kwargs):
    res = request(method, path, **kwargs)
    if res is None:
        return default
    try:
        return res.json()
    except Exception:
        st.error("El servicio devolvió una respuesta que no se pudo leer.")
        return default


def money(value):
    return "No definido" if value is None else f"${value:,.2f} MXN"


def number(value, suffix=""):
    return "No definida" if value is None else f"{value:,.2f}{suffix}"


def hero(title, description, *, compact=False):
    style = "agtech-hero agtech-hero--compact" if compact else "agtech-hero"
    st.markdown(f'<div class="{style}"><div class="agtech-eyebrow">AGTECH · DEMOSTRACIÓN ACADÉMICA</div><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p></div>', unsafe_allow_html=True)


def section_intro(title, description):
    st.subheader(title)
    st.caption(description)


def insight(title, description, tone="info"):
    tone = tone if tone in {"info", "success", "warning"} else "info"
    st.markdown(f'<div class="agtech-insight agtech-insight--{tone}" role="status"><strong>{html.escape(str(title))}</strong><p>{html.escape(str(description))}</p></div>', unsafe_allow_html=True)


def empty_state(title, description):
    st.markdown(f'<div class="agtech-empty"><strong>{html.escape(str(title))}</strong><p>{html.escape(str(description))}</p></div>', unsafe_allow_html=True)


def ir_a_modulo(module):
    st.session_state.modulo_activo = module


# Los identificadores se conservan para los permisos, atajos y sesiones existentes.
NAVEGACION = [
    (None, [("Inicio", "Inicio", "home", ())]),
    ("Operación", [
        ("Punto de venta", "Punto de venta", "point_of_sale", ("tpv",)),
        ("Inventario y productos", "Inventario", "inventory_2", ("inventario",)),
    ]),
    ("Análisis", [
        ("Finanzas y tendencias", "Finanzas", "monitoring", ("simulador",)),
        ("Ingeniería y presupuestos", "Presupuestos", "construction", ("ingenieria",)),
    ]),
    ("Administración", [
        ("Sedes y ubicación", "Sedes y ubicación", "location_on", ("registrar_sede",)),
        ("Personal y usuarios", "Personal y accesos", "group", ("personal", "usuarios")),
        ("Configuración", "Configuración", "settings", ("usuarios",)),
    ]),
]
ETIQUETAS_MODULOS = {module: label for _, items in NAVEGACION for module, label, _, _ in items}


def nombre_presupuesto(value):
    return {"P1_ECONOMICO": "Kit económico · ESP32", "P2_OBJETIVO": "Kit objetivo · Radxa", "P3_PREMIUM": "Kit premium · Raspberry Pi"}.get(value, value)


def table(rows):
    if rows:
        labels = {"id": "Identificador", "producto_id": "Código", "componente_id": "Código", "producto": "Producto",
            "item": "Productos", "stock": "Existencias", "punto_reorden": "Punto de reorden", "cantidad_sugerida": "Compra sugerida (unidades)",
            "precio_publico": "Precio sin IVA (MXN)", "costo_unitario": "Costo unitario (MXN)", "total": "Total con IVA (MXN)",
            "subtotal": "Subtotal sin IVA (MXN)", "iva": "IVA (MXN)", "utilidad_bruta": "Utilidad bruta (MXN)",
            "ventas_netas": "Ventas sin IVA (MXN)", "costo_ventas": "Costo de ventas (MXN)", "sueldo_mensual": "Sueldo mensual (MXN)",
            "username": "Usuario", "activo": "Activo", "nombre_sede": "Sede", "distancia_operacion_km": "Distancia al cobrar (km)"}
        frame = pd.DataFrame(rows)
        frame = frame.rename(columns={col: labels.get(col, str(col).replace("_", " ").capitalize() if "_" in str(col) or str(col).islower() else col) for col in frame.columns})
        configs = {col: st.column_config.NumberColumn(format="$%.2f") for col in frame.columns if "(MXN)" in str(col) and pd.api.types.is_numeric_dtype(frame[col])}
        st.dataframe(frame, width="stretch", hide_index=True, column_config=configs)
    else:
        st.caption("Todavía no hay registros.")


def finish(message):
    st.session_state.pop("excel_data", None)
    st.session_state.pop("respaldo_data", None)
    st.session_state.flash = message
    st.rerun()


def creditos_foto(product):
    if product.get("foto_descripcion"):
        st.caption(product["foto_descripcion"])
    if product.get("foto_fuente"):
        st.link_button("Fuente de la fotografía", product["foto_fuente"])
    credit = " · ".join(str(product[k]) for k in ("foto_autor", "foto_licencia") if product.get(k))
    if credit:
        st.caption(credit)


@st.fragment(run_every=300)
def sincronizar_tipo_cambio():
    # Revisa la caché al entrar y cada cinco minutos con la sesión abierta.
    # El servicio consulta al proveedor como máximo cada seis horas.
    result = api("GET", "/datos-externos/tipo-cambio", default={}, quiet=True)
    if result:
        st.session_state.cambio_externo = result


if not st.session_state.autenticado:
    hero("Gestiona tu negocio con AgTech", "Vende, controla existencias y explora la rentabilidad desde un mismo lugar.")
    left, right = st.columns([1, 1])
    with left:
        st.subheader("Entrar al sistema")
        st.caption("Para explorar todas las funciones usa gerente y la contraseña 123.")
        with st.form("login"):
            username = st.text_input("Usuario", placeholder="gerente")
            password = st.text_input("Contraseña", type="password")
            if st.form_submit_button("Iniciar sesión", type="primary", width="stretch"):
                auth = api("POST", "/auth/login", json={"username": username.strip(), "password": password})
                if auth:
                    st.session_state.token = auth["access_token"]
                    st.session_state.autenticado = True
                    st.session_state.username = auth["username"]
                    st.session_state.rol = auth["rol"]
                    st.session_state.icono_rol = auth.get("icono", "👤")
                    st.session_state.permisos = auth["permisos"]
                    st.rerun()
    with right:
        st.subheader("Elige un perfil de prueba")
        st.table(pd.DataFrame([
            {"Usuario": "gerente", "Contraseña": "123", "Área": "Administración · acceso completo"},
            {"Usuario": "cajero", "Contraseña": "123", "Área": "Ventas · caja y comprobantes"},
            {"Usuario": "ingeniero", "Contraseña": "123", "Área": "Ingeniería · inventario y análisis"},
        ]))
        st.caption("Estos accesos son exclusivamente de la demostración; utiliza datos ficticios. El gerente puede registrar usuarios individuales.")
    with st.expander("Qué puedes demostrar con este sistema"):
        st.markdown("**Ventas e inventario:** registra ventas, descuenta productos y descarga comprobantes.\n\n**Ubicación:** marca una posición en el mapa y demuestra el bloqueo fuera del radio.\n\n**Finanzas:** compara lo vendido con escenarios de inversión y costos.")
        st.info("GPS, lector, pagos y facturación fiscal se simulan. El programa sí guarda las operaciones que registres.")
    st.stop()

me = api("GET", "/auth/me")
if not me:
    st.stop()
st.session_state.permisos = me.get("permisos", st.session_state.permisos)
st.session_state.rol = me.get("rol", st.session_state.rol)
permisos_usuario = st.session_state.permisos
sincronizar_tipo_cambio()
negocios_db = api("GET", "/negocios", default={})
datos_inventario = api("GET", "/inventario/componentes", default={})
catalogo_comp = datos_inventario.get("catalogo_diccionario", {})
datos_presupuestos = api("GET", "/ingenieria/presupuestos-tabulares", default={}) if ("ingenieria" in permisos_usuario or "registrar_sede" in permisos_usuario) else {}

with st.sidebar:
    st.title("🌱 AgTech")
    if negocios_db:
        nueva_sede = st.session_state.pop("seleccionar_sede_nueva", None)
        if nueva_sede in negocios_db:
            st.session_state.sede_activa = nueva_sede
        if st.session_state.get("sede_activa") not in negocios_db:
            st.session_state.sede_activa = next(iter(negocios_db))
        sucursal_activa_id = st.selectbox("Sede activa", list(negocios_db), format_func=lambda k: negocios_db[k]["nombre"], key="sede_activa", help="Las ventas y los reportes corresponden a esta sede. El inventario es compartido.")
        datos_sucursal = negocios_db[sucursal_activa_id]
    else:
        sucursal_activa_id, datos_sucursal = None, None
        st.warning("Registra una sede para comenzar.")
    grupos_visibles = [(group, [item for item in items if not item[3] or any(p in permisos_usuario for p in item[3])])
                      for group, items in NAVEGACION]
    menu = [item[0] for _, items in grupos_visibles for item in items]
    if st.session_state.get("modulo_activo") not in menu:
        st.session_state.modulo_activo = "Inicio"
    pagina = st.session_state.modulo_activo
    with st.container(key="navegacion_principal"):
        for group, items in grupos_visibles:
            if not items:
                continue
            if group:
                st.markdown(f'<h3 class="agtech-nav-group">{group}</h3>', unsafe_allow_html=True)
            for module, label, icon, _ in items:
                st.button(label, key=f"nav_{module}", icon=f":material/{icon}:",
                          type="primary" if pagina == module else "tertiary",
                          help="Página actual" if pagina == module else None,
                          on_click=ir_a_modulo, args=(module,), width="stretch")
    st.divider()
    if "exportar" in permisos_usuario:
        if st.button("Preparar reporte Excel", width="stretch"):
            result = request("GET", "/exportar/excel")
            if result is not None:
                st.session_state.excel_data = result.content
        if st.session_state.get("excel_data"):
            st.download_button("Descargar Excel", st.session_state.excel_data, "Reporte_ERP_AgTech.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
            st.caption("Vuelve a preparar el reporte después de registrar cambios.")
    with st.expander("Tu cuenta y la demostración"):
        st.caption(f"{st.session_state.username} · {st.session_state.rol}")
        st.caption("MODO ACADÉMICO · Usa datos ficticios. El inventario es compartido entre sedes.")
        if st.button("Cerrar sesión", width="stretch"):
            request("POST", "/auth/logout", quiet=True)
            client = st.session_state.api_client
            st.session_state.clear()
            st.session_state.api_client = client
            st.rerun()

descriptions = {
    "Inicio": "Tu operación de un vistazo. Elige una tarea para empezar.",
    "Punto de venta": "Verifica tu ubicación, elige productos y revisa el total antes de cobrar.",
    "Inventario y productos": "Consulta existencias, identifica faltantes y administra tus productos.",
    "Sedes y ubicación": "Define dónde opera cada sede y el radio permitido para registrar ventas.",
    "Finanzas y tendencias": "Consulta resultados registrados o prueba escenarios de inversión.",
    "Ingeniería y presupuestos": "Compara alternativas de equipamiento y conoce cómo se produce cada kit.",
    "Personal y usuarios": "Organiza tu equipo y decide quién puede entrar a cada módulo.",
    "Configuración": "Consulta el tipo de cambio, ajusta el IVA y conserva una copia de tus datos.",
}
grupo_activo = next(group for group, items in grupos_visibles if any(item[0] == pagina for item in items))
if grupo_activo:
    st.caption(f"Estás en: {grupo_activo} / {ETIQUETAS_MODULOS[pagina]}")
hero(ETIQUETAS_MODULOS[pagina], descriptions[pagina], compact=True)
if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))

if pagina == "Inicio":
    low_products = [p for p in catalogo_comp.values() if p["stock"] <= p.get("punto_reorden", 0)]
    if datos_sucursal:
        st.caption(f"Tu sede activa: {datos_sucursal['nombre']} · {st.session_state.rol}")
        a, b, c = st.columns(3)
        a.metric("Productos en catálogo", len(catalogo_comp))
        b.metric("Productos por reabastecer", len(low_products))
        c.metric("Radio permitido para vender", f"{datos_sucursal['radio_operacion_km']:g} km")
    if low_products:
        accion_reorden = "Abre Inventario para revisar los productos y registrar una entrada cuando recibas mercancía." if "inventario" in permisos_usuario else "Avisa al gerente para que revise los productos por reabastecer."
        insight(f"Requieren atención: {len(low_products)} productos", accion_reorden, "warning")
    elif catalogo_comp:
        insight("Inventario sin alertas de reabastecimiento", "Todos los productos están por encima de su punto de reorden. Elige abajo la tarea que necesitas hacer.", "success")
    else:
        empty_state("El catálogo está vacío", "Solicita al gerente que revise el catálogo antes de registrar una venta.")
    section_intro("¿Qué quieres hacer?", "Abre una tarea. La sede elegida se mantiene al cambiar de módulo.")
    shortcuts = [("Punto de venta", "Registrar una venta", "Elige productos, revisa el total y genera un ticket."),
                 ("Inventario y productos", "Revisar inventario", "Consulta existencias, precios y productos por reabastecer."),
                 ("Finanzas y tendencias", "Consultar finanzas", "Revisa ventas registradas y prueba escenarios de inversión."),
                 ("Ingeniería y presupuestos", "Comparar presupuestos", "Explora equipos, costos y procesos de producción.")]
    visible_shortcuts = [item for item in shortcuts if item[0] in menu]
    card_columns = 2 if len(visible_shortcuts) == 4 else max(1, min(3, len(visible_shortcuts)))
    for start in range(0, len(visible_shortcuts), card_columns):
        for column, (module, label, description) in zip(st.columns(min(card_columns, len(visible_shortcuts) - start)), visible_shortcuts[start:start + card_columns]):
            with column, st.container(border=True):
                st.markdown(f"**{label}**")
                st.caption(description)
                task_icon = next(icon for _, items in NAVEGACION for item_module, _, icon, _ in items if item_module == module)
                st.button(f"Abrir {ETIQUETAS_MODULOS[module].lower()}", icon=f":material/{task_icon}:", key=f"atajo_{module}", on_click=ir_a_modulo, args=(module,), width="stretch")
    with st.expander("Guía rápida para la demostración", expanded=False):
        st.markdown("1. Usa la sede de ejemplo o registra otra en **Administración → Sedes y ubicación**.\n2. Revisa productos y existencias en **Operación → Inventario**.\n3. En **Operación → Punto de venta**, alterna dentro/fuera del radio para demostrar el bloqueo.\n4. Vuelve dentro, revisa el total y registra una venta.\n5. Descarga el ticket y consulta **Análisis → Finanzas**.")
        st.caption("Las opciones disponibles dependen de tu perfil. El gerente puede explorar todos los módulos.")
    with st.expander("Qué se guarda y qué se simula"):
        st.markdown("**Se guarda:** ventas, inventario, sedes, personal y cuentas de usuario.\n\n**Se simula:** ubicación GPS, lector de códigos, pagos, facturación fiscal y escenarios financieros. Los comprobantes se descargan para imprimir desde el navegador.")
    if sucursal_activa_id and ("reportes" in permisos_usuario or "inventario" in permisos_usuario):
        recommendations = api("GET", f"/analisis/recomendaciones/{sucursal_activa_id}", default={})
        section_intro("Productos sugeridos para tu zona", "Sugerencias del escenario geográfico de demostración; no son un estudio de mercado en tiempo real.")
        recommendations_rows = recommendations.get("recomendaciones", [])
        for start in range(0, len(recommendations_rows), 3):
            for column, row in zip(st.columns(min(3, len(recommendations_rows) - start)), recommendations_rows[start:start + 3]):
                with column, st.container(border=True):
                    st.markdown(f"**{row['producto']}**")
                    suggested = row.get("cantidad_sugerida", 0)
                    st.caption(f"Compra sugerida: {suggested:g} unidades" if suggested > 0 else "Sin reposición sugerida con el mínimo configurado")
        if recommendations_rows:
            with st.expander("Por qué se sugieren estos productos"):
                st.caption(recommendations.get("fuente", "Reglas geográficas de demostración."))
                table([{k: v for k, v in row.items() if k != "producto_id"} for row in recommendations_rows])
        else:
            empty_state("Sin sugerencias para mostrar", "Selecciona una sede con catálogo disponible para consultar sugerencias por zona.")

if pagina == "Sedes y ubicación":
    resumen_sedes, alta_sede = st.tabs(["Mis sedes", "Agregar sede"])
    with resumen_sedes:
        if datos_sucursal:
            a, b, c = st.columns(3)
            a.metric("Sedes registradas", len(negocios_db))
            b.metric("Radio permitido", f"{datos_sucursal['radio_operacion_km']:g} km")
            c.metric("Precio del kit sin IVA", money(datos_sucursal["precio_venta_unitario"]))
            section_intro(datos_sucursal["nombre"], "Esta es la sede activa. Para consultar otra, cámbiala en la barra lateral.")
            with st.container(border=True):
                a, b = st.columns(2)
                with a:
                    st.markdown("**Ubicación y actividad**")
                    st.write(datos_sucursal.get("ciudad_referencia") or "Ciudad no especificada")
                    st.caption(datos_sucursal.get("giro", "Sin giro registrado"))
                    st.write(datos_sucursal.get("actividades", "Sin actividades registradas"))
                with b:
                    st.markdown("**Kit que se vende en esta sede**")
                    st.write(nombre_presupuesto(datos_sucursal["presupuesto_seleccionado"]))
                    st.caption("El precio indicado no incluye IVA. El inventario se comparte entre todas las sedes.")
            insight("¿Dónde se permite vender?", f"Dentro de un radio de {datos_sucursal['radio_operacion_km']:g} km alrededor de esta sede. En Punto de venta puedes simular estar dentro o fuera para comprobar el bloqueo.")
            with st.expander("Ver ubicación y supuestos guardados"):
                st.caption(f"Coordenadas: {datos_sucursal['latitud']:.5f}, {datos_sucursal['longitud']:.5f}. La ubicación del cajero se simula por separado.")
                if st.checkbox("Mostrar mapa de la sede activa", key="mostrar_mapa_sede_resumen"):
                    m_resumen = folium.Map(location=[datos_sucursal["latitud"], datos_sucursal["longitud"]], zoom_start=12, control_scale=True)
                    folium.Circle([datos_sucursal["latitud"], datos_sucursal["longitud"]], radius=datos_sucursal["radio_operacion_km"] * 1000, color="#13866B", fill=True, fill_opacity=0.12).add_to(m_resumen)
                    folium.Marker([datos_sucursal["latitud"], datos_sucursal["longitud"]], tooltip=html.escape(datos_sucursal["nombre"])).add_to(m_resumen)
                    st_folium(m_resumen, height=300, use_container_width=True, returned_objects=[], key=f"mapa_sede_resumen_{sucursal_activa_id}")
                a, b, c = st.columns(3)
                a.metric("Inversión inicial", money(datos_sucursal["inversion_inicial"]))
                b.metric("Costos fijos mensuales", money(datos_sucursal["costos_fijos_mensuales"]))
                c.metric("Costo variable por kit", money(datos_sucursal["costo_variable_unitario"]))
                st.caption("Estos valores son los supuestos iniciales del simulador financiero; no son gastos calculados a partir de las ventas.")
            with st.expander("Comparar todas las sedes", expanded=len(negocios_db) > 1):
                table([{"Sede": row["nombre"], "Ciudad / zona": row.get("ciudad_referencia", ""), "Giro": row.get("giro", ""),
                       "Radio permitido (km)": row["radio_operacion_km"], "Kit": nombre_presupuesto(row["presupuesto_seleccionado"]),
                       "Precio del kit sin IVA (MXN)": row["precio_venta_unitario"]} for row in negocios_db.values()])
        else:
            empty_state("Empieza con tu primera sede", "Abre Agregar sede para definir el negocio, su ubicación y el radio donde se podrá vender.")
    with alta_sede:
        section_intro("Registrar una nueva sede", "Revisa los tres apartados y confirma una sola vez. Al guardar, la nueva sede quedará seleccionada.")
        with st.expander("Buscar dirección o seleccionar en mapa"):
            location_text = st.text_input("Dirección o lugar", placeholder="Texcoco, Estado de México")
            if st.button("Buscar dirección") and location_text.strip():
                try:
                    location = Nominatim(user_agent="erp-agtech-academico", timeout=10).geocode(location_text)
                    if location:
                        st.session_state.nueva_sede_lat = float(location.latitude)
                        st.session_state.nueva_sede_lon = float(location.longitude)
                        reiniciar_mapa_sede()
                        st.success(location.address)
                    else:
                        st.warning("No se encontró la dirección. Puedes capturar coordenadas manualmente.")
                except Exception:
                    st.warning("El geocodificador no está disponible. Usa las coordenadas manuales.")
            if st.checkbox("Mostrar mapa (requiere conexión)", on_change=reiniciar_mapa_sede):
                m = folium.Map(location=[st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon], zoom_start=12)
                folium.Marker([st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon]).add_to(m)
                clicked = st_folium(m, height=300, use_container_width=True, returned_objects=["last_clicked"], key=f"mapa_sede_{st.session_state.get('mapa_sede_revision', 0)}")
                if clicked and clicked.get("last_clicked"):
                    try:
                        pair = (float(clicked["last_clicked"]["lat"]), float(clicked["last_clicked"]["lng"]))
                        valid_pair = all(math.isfinite(value) for value in pair) and -90 <= pair[0] <= 90 and -180 <= pair[1] <= 180
                    except (KeyError, TypeError, ValueError, OverflowError):
                        valid_pair = False
                    if valid_pair and pair != (st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon):
                        st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon = pair
                        reiniciar_mapa_sede()
                        st.rerun()
        budgets = {p["id_presupuesto"]: p for p in datos_presupuestos.get("detalle_presupuestos", [])}
        pres = st.selectbox("Presupuesto base", list(budgets) or ["P2_OBJETIVO"], format_func=lambda k: budgets.get(k, {}).get("nombre_nivel", k))
        budget = budgets.get(pres, {})
        with st.form("nueva_sede"):
            identidad_sede, ubicacion_sede, costos_sede = st.tabs(["1 · Negocio", "2 · Ubicación", "3 · Inversión y precio"])
            with identidad_sede:
                st.caption("Describe el negocio que operará en esta sede.")
                a, b = st.columns(2)
                nombre = a.text_input("Nombre de la sede", "AgTech Planta Texcoco")
                ciudad = b.text_input("Ciudad / zona", "Texcoco, Estado de México")
                c1, c2, c3 = st.columns(3)
                sector = c1.selectbox("Sector", ["Agroindustrial", "Comercial", "Servicios", "Industrial"])
                giro = c2.text_input("Giro comercial", "Tecnología agrícola")
                actividades = c3.text_input("Actividades", "Ensamble y venta de sensores y kits agrícolas")
            with ubicacion_sede:
                st.caption("La geocerca es el círculo alrededor de la sede dentro del cual se permite vender. Aquí defines su tamaño; el GPS se simula.")
                a, b, c = st.columns(3)
                lat = a.number_input("Latitud", -90.0, 90.0, float(st.session_state.nueva_sede_lat), format="%.5f", key=f"lat_sede_{st.session_state.get('mapa_sede_revision', 0)}")
                lon = b.number_input("Longitud", -180.0, 180.0, float(st.session_state.nueva_sede_lon), format="%.5f", key=f"lon_sede_{st.session_state.get('mapa_sede_revision', 0)}")
                radius = c.number_input("Radio de geocerca (km)", 0.01, 1000.0, 5.0)
            with costos_sede:
                st.caption("Los costos son supuestos para el simulador. El precio del kit sí se usa en caja; el IVA se agrega al cobrar.")
                a, b = st.columns(2)
                capex = a.number_input("Inversión inicial (MXN)", min_value=0.0, value=float(budget.get("capex_total_mxn", 1775000)), key=f"capex_{pres}")
                fixed = b.number_input("Costos fijos / mes (MXN)", min_value=0.0, value=580000.0)
                variable = a.number_input("Costo variable / kit (MXN)", min_value=0.0, value=float(budget.get("costo_produccion_kit_mxn", 2750)), key=f"variable_{pres}")
                price = b.number_input("Precio / kit sin IVA (MXN)", min_value=0.01, value=float(budget.get("precio_publico_kit_mxn", 10500)), key=f"price_{pres}")
            st.caption("Revisa nombre, ubicación, radio y precio antes de guardar. El formulario contiene valores de ejemplo que puedes cambiar.")
            if st.form_submit_button("Registrar sede", type="primary"):
                result = api("POST", "/negocios", json={"nombre": nombre, "ciudad_referencia": ciudad, "sector": sector, "giro": giro, "actividades": actividades,
                    "latitud": lat, "longitud": lon, "radio_operacion_km": radius, "presupuesto_seleccionado": pres,
                    "inversion_inicial": capex, "costos_fijos_mensuales": fixed, "costo_variable_unitario": variable, "precio_venta_unitario": price})
                if result:
                    st.session_state.seleccionar_sede_nueva = result["id_negocio"]
                    fijar_posicion_cajero(lat, lon)
                    finish("Sede registrada y seleccionada. El cajero se ubicó en su centro para la demostración.")

if pagina == "Punto de venta":
    if not datos_sucursal:
        empty_state("Primero necesitas una sede", "El gerente puede crearla en Administración → Sedes y ubicación. Después selecciónala en la barra lateral para abrir caja.")
    else:
        venta_tab, historial_tab = st.tabs(["Nueva venta", "Historial y comprobantes"])
        with venta_tab:
            st.caption(f"Sede activa: {datos_sucursal['nombre']} · Cajero: {st.session_state.username}")
            st.markdown("**1 · Confirma tu ubicación**")
            estado_ubicacion = st.container()
            st.session_state.operador_lat, st.session_state.operador_lon = st.session_state.posicion_cajero
            if st.session_state.get("mapa_cajero_sede") != sucursal_activa_id:
                st.session_state.mapa_cajero_sede = sucursal_activa_id
                reiniciar_mapa_cajero()
            with st.expander("Ver mapa y cambiar ubicación · GPS simulado", expanded=False):
                st.caption("Haz clic en el mapa para marcar la ubicación simulada del cajero. El círculo verde es el radio permitido de la sede. Esta selección no detecta la ubicación real del equipo.")
                if st.button("Centrar ubicación en la sede"):
                    fijar_posicion_cajero(datos_sucursal["latitud"], datos_sucursal["longitud"])
                    st.rerun()
                if st.checkbox("Mostrar mapa del cajero", value=True, key="mostrar_mapa_cajero", on_change=reiniciar_mapa_cajero):
                    sede_lat, sede_lon = float(datos_sucursal["latitud"]), float(datos_sucursal["longitud"])
                    cajero_lat, cajero_lon = st.session_state.posicion_cajero
                    radio_km = float(datos_sucursal["radio_operacion_km"])
                    mapa_cajero = folium.Map(location=[sede_lat, sede_lon], zoom_start=12, control_scale=True)
                    folium.Circle(
                        [sede_lat, sede_lon], radius=radio_km * 1000,
                        color="#169B62", fill=True, fill_opacity=0.12,
                        tooltip=f"Radio permitido: {radio_km:g} km",
                    ).add_to(mapa_cajero)
                    folium.Marker(
                        [sede_lat, sede_lon], tooltip=f"Sede: {html.escape(datos_sucursal['nombre'])}",
                        icon=folium.Icon(color="green", icon="home"),
                    ).add_to(mapa_cajero)
                    folium.CircleMarker(
                        [cajero_lat, cajero_lon], radius=9, color="#1647B0",
                        fill=True, fill_color="#4C8EFF", fill_opacity=1,
                        tooltip="Cajero: ubicación simulada seleccionada",
                    ).add_to(mapa_cajero)
                    # Incluir el radio y el cajero en el encuadre inicial.
                    lat_delta = radio_km / 110.574
                    lon_delta = min(180.0, radio_km / (111.320 * max(abs(math.cos(math.radians(sede_lat))), 0.01)))
                    mapa_cajero.fit_bounds([
                        [max(-90.0, min(sede_lat - lat_delta, cajero_lat)), max(-180.0, min(sede_lon - lon_delta, cajero_lon))],
                        [min(90.0, max(sede_lat + lat_delta, cajero_lat)), min(180.0, max(sede_lon + lon_delta, cajero_lon))],
                    ], padding=(25, 25), max_zoom=16)
                    seleccion = st_folium(
                        mapa_cajero, height=380, use_container_width=True,
                        returned_objects=["last_clicked"],
                        key=f"mapa_cajero_{sucursal_activa_id}_{st.session_state.mapa_cajero_revision}",
                    )
                    clic = (seleccion or {}).get("last_clicked")
                    if clic:
                        try:
                            nueva_lat, nueva_lon = float(clic["lat"]), float(clic["lng"])
                            valida = math.isfinite(nueva_lat) and math.isfinite(nueva_lon) and -90 <= nueva_lat <= 90 and -180 <= nueva_lon <= 180
                        except (KeyError, TypeError, ValueError, OverflowError):
                            valida = False
                        if valida and (nueva_lat, nueva_lon) != st.session_state.posicion_cajero:
                            fijar_posicion_cajero(nueva_lat, nueva_lon)
                            st.rerun()
                    st.caption("Verde: sede y geocerca · Azul: cajero. Si el mapa no carga por falta de conexión, usa los campos de coordenadas.")
                a, b = st.columns(2)
                lat_operador = a.number_input("Latitud del cajero", -90.0, 90.0, key="operador_lat", format="%.5f", on_change=cambiar_coordenadas_cajero)
                lon_operador = b.number_input("Longitud del cajero", -180.0, 180.0, key="operador_lon", format="%.5f", on_change=cambiar_coordenadas_cajero)
            geo = api("POST", "/negocios/validar-geocerca", default={}, json={"negocio_id": sucursal_activa_id, "latitud_operador": lat_operador, "longitud_operador": lon_operador})
            allowed = geo.get("operacion_permitida", False)
            with estado_ubicacion:
                estado_geo, accion_geo = st.columns([2.5, 1])
                if allowed:
                    estado_geo.success(f"Ubicación permitida · A {geo.get('distancia_km', 0):.2f} km de la sede.")
                elif geo:
                    estado_geo.error(f"Venta bloqueada · A {geo.get('distancia_km', 0):.2f} km; máximo {datos_sucursal['radio_operacion_km']:g} km. Vuelve dentro del radio para cobrar.")
                else:
                    estado_geo.error("No se pudo comprobar tu ubicación. El cobro permanece bloqueado; vuelve a intentarlo.")
                destino_lat, destino_lon = float(datos_sucursal["latitud"]), float(datos_sucursal["longitud"])
                if allowed:
                    radio_demo = float(datos_sucursal["radio_operacion_km"])
                    # Alejar hacia el ecuador: válido también en polos y radios de hasta 1000 km.
                    salto_lat = math.degrees(max(2 * radio_demo, radio_demo + 1) / 6371.0)
                    destino_lat += -salto_lat if destino_lat > 0 else salto_lat
                accion_geo.button(
                    "Simular fuera del radio" if allowed else "Simular dentro del radio",
                    key="alternar_radio_cajero", on_click=fijar_posicion_cajero,
                    args=(destino_lat, destino_lon),
                    help="Cambia la ubicación simulada del cajero para demostrar el bloqueo. No registra ventas ni modifica el radio de la sede.",
                )
            seleccion_col, resumen_col = st.columns([1.25, 1], gap="large")
            with seleccion_col, st.container(border=True):
                section_intro("2 · Prepara la venta", "Elige qué vas a vender y cuántas unidades necesita el cliente.")
                mode = st.radio("Tipo de venta", ["Kit estándar de la sede", "Refacción / código de barras", "Combo personalizado"], horizontal=False)
                ids, quote = [], None
                sale_type = "Estándar"
                if mode == "Refacción / código de barras":
                    sale_type = "Componentes"
                    barcode = st.text_input("Simular lector: escribe o pega el código de barras y presiona Enter", placeholder="Ejemplo: AGT00000001").strip()
                    found = next((key for key, item in catalogo_comp.items() if barcode and barcode in (key, item.get("codigo_barras"))), None)
                    if barcode and not found:
                        st.warning("Código no encontrado. Corrígelo o borra el campo para elegir un producto de la lista. El cobro queda bloqueado.")
                    keys = list(catalogo_comp)
                    if not keys:
                        empty_state("No hay refacciones disponibles", "Pide al gerente que revise el catálogo. No se puede cobrar hasta que haya productos disponibles.")
                    if keys and (not barcode or found):
                        product_id = st.selectbox("Producto", keys, index=keys.index(found) if found else 0, format_func=lambda k: catalogo_comp[k]["nombre"], key=f"producto_{found or 'manual'}")
                        st.caption(f"{money(catalogo_comp[product_id]['precio_publico'])} sin IVA por unidad · {catalogo_comp[product_id]['stock']} disponibles")
                        ids = [product_id]
                        if catalogo_comp[product_id].get("foto_url"):
                            st.image(catalogo_comp[product_id]["foto_url"], width=180)
                elif mode == "Combo personalizado":
                    sale_type = "Combo"
                    plates = [k for k, d in catalogo_comp.items() if d["categoria"] == "Placa Base"]
                    storage = [k for k, d in catalogo_comp.items() if d["categoria"] == "Almacenamiento"]
                    sensors = [k for k, d in catalogo_comp.items() if d["categoria"] == "Sensor"]
                    if plates and storage:
                        placa = st.selectbox("Placa base", plates, format_func=lambda k: catalogo_comp[k]["nombre"])
                        almacenamiento = st.selectbox("Almacenamiento", storage, format_func=lambda k: catalogo_comp[k]["nombre"])
                        sens = st.multiselect("Sensores", sensors, default=sensors, format_func=lambda k: catalogo_comp[k]["nombre"])
                        include = st.checkbox(f"Incluir chasis y fuente ({money(catalogo_comp.get('FUENTE_CHASIS', {}).get('precio_publico', 0))})", value=True)
                        ids = [placa, almacenamiento] + sens + (["FUENTE_CHASIS"] if include else [])
                        st.caption("Cuatro o más componentes distintos reciben 8 % de descuento antes del IVA.")
                    else:
                        empty_state("Faltan componentes para armar un combo", "El catálogo necesita al menos una placa base y un almacenamiento. Pide al gerente que revise esos productos o elige otro tipo de venta.")
                else:
                    st.markdown(f"**{nombre_presupuesto(datos_sucursal['presupuesto_seleccionado'])}**")
                    st.caption(f"{money(datos_sucursal['precio_venta_unitario'])} sin IVA por kit. El resumen incluye el impuesto.")
                a, b = st.columns(2)
                quantity = a.number_input("Cantidad", min_value=1, max_value=10000, value=1, step=1)
                payment = b.selectbox("Método de pago", ["efectivo", "transferencia", "tarjeta"])
                sale_payload = {"negocio_id": sucursal_activa_id, "latitud_operador": lat_operador,
                    "longitud_operador": lon_operador, "tipo_venta": sale_type, "componentes_ids": ids, "cantidad": quantity, "metodo_pago": payment}
                if mode == "Kit estándar de la sede" or ids:
                    quote = api("POST", "/tpv/cotizar-venta", json=sale_payload)
            with resumen_col, st.container(border=True):
                section_intro("3 · Revisa y cobra", "Comprueba el total antes de confirmar. Importes en pesos mexicanos (MXN).")
                if quote:
                    with st.container():
                        st.metric("Total a cobrar", f"${quote['total']:,.2f}")
                        a, b = st.columns(2)
                        a.metric("Subtotal sin IVA", f"${quote['subtotal']:,.2f}")
                        b.metric(f"IVA ({quote['iva_tasa'] * 100:g} %)", f"${quote['iva']:,.2f}")
                        st.caption(f"Cantidad: {quantity} · Disponibilidad: {quote['unidades_disponibles']} {('kits' if mode == 'Kit estándar de la sede' else 'combos' if mode == 'Combo personalizado' else 'unidades')} · Pago: {payment}")
                        if quote.get("descuento_pct"):
                            st.success(f"Descuento de combo incluido: {quote['descuento_pct']:g} % antes de IVA.")
                        with st.expander("Ver productos incluidos"):
                            table([{"Producto": row["nombre"], "Unidades a descontar": row["cantidad"]} for row in quote["detalle"]])
                    if not quote["stock_suficiente"]:
                        stock_action = "registra una entrada en inventario cuando recibas mercancía" if "inventario" in permisos_usuario else "pide al gerente que reabastezca los productos"
                        st.warning(f"No hay existencias suficientes para esta cantidad. Reduce la cantidad o {stock_action}.")
                        table([{"Producto": row["nombre"], "Unidades necesarias": row["requerido"], "Disponibles": row["disponible"]} for row in quote["faltantes"]])
                else:
                    st.info("Selecciona productos válidos para consultar el total antes de cobrar.")
                st.caption("Al confirmar se registra la venta y se descuenta el inventario. El pago es simulado: no se cobra a una tarjeta ni a una cuenta bancaria.")
                if st.button("Cobrar y registrar venta", type="primary", disabled=not allowed or not quote or not quote.get("stock_suficiente", False), width="stretch"):
                    fingerprint = json.dumps(sale_payload, sort_keys=True)
                    pending = st.session_state.get("venta_pendiente", {})
                    if pending.get("fingerprint") != fingerprint:
                        pending = {"fingerprint": fingerprint, "key": uuid.uuid4().hex}
                        st.session_state.venta_pendiente = pending
                    sale_payload["idempotency_key"] = pending["key"]
                    result = api("POST", "/tpv/venta", json=sale_payload)
                    if result:
                        st.session_state.pop("venta_pendiente", None)
                        st.session_state.ultimo_ticket = result.get("ticket", result)
                        finish("Venta registrada. Abre la pestaña Historial y comprobantes para descargar el ticket.")
        with historial_tab:
            history = api("GET", f"/ventas/historial/{sucursal_activa_id}", default={})
            sales = history.get("historial_detallado", [])
            st.subheader("Historial y comprobantes")
            if sales:
                a, b, c = st.columns(3)
                a.metric("Ventas registradas", len(sales))
                b.metric("Total cobrado con IVA", money(sum(v.get("total", v.get("ingreso_bruto", 0)) for v in sales)))
                c.metric("Utilidad bruta sin IVA", money(sum(v.get("utilidad_bruta", 0) for v in sales)))
                section_intro("Recupera un comprobante", "Selecciona una venta y descarga el ticket o la factura de demostración.")
                sales_by_id = {v["folio"]: v for v in sales}
                folio = st.selectbox("Venta para ticket / factura", [v["folio"] for v in reversed(sales)], format_func=lambda value: f"{value} · {sales_by_id[value]['tipo_venta']} · {money(sales_by_id[value]['total'])}")
                for kind, label in [("ticket", "Ticket"), ("factura", "Factura simulada")]:
                    with st.expander(label, expanded=kind == "ticket"):
                        result = request("GET", f"/ventas/{folio}/{kind}")
                        if result is not None:
                            try:
                                document = result.json()
                                content = document.get("texto", document.get("ticket", json.dumps(document, ensure_ascii=False, indent=2))) if isinstance(document, dict) else str(document)
                            except Exception:
                                content = result.text
                            if not isinstance(content, str):
                                content = json.dumps(content, ensure_ascii=False, indent=2)
                            with st.expander("Vista previa del " + label.lower()):
                                st.code(content, language=None)
                            printable = '<!doctype html><html lang="es"><meta charset="utf-8"><title>Comprobante AgTech</title><style>body{font:16px monospace;padding:32px}pre{white-space:pre-wrap}@media print{button{display:none}}</style><button onclick="window.print()">Imprimir / guardar PDF</button><pre>' + html.escape(content) + '</pre></html>'
                            st.download_button(f"Descargar {label.lower()} para imprimir", printable, f"{kind}_{folio}.html", "text/html", key=f"download_{kind}")
                            if kind == "factura":
                                st.warning("Documento académico simulado: sin timbrado SAT ni validez fiscal.")
                st.caption("Abre el archivo descargado y usa Imprimir / guardar PDF. No requiere impresora física.")
                with st.expander("Consultar todas las ventas y sus importes"):
                    table([{"Folio": v["folio"], "Fecha (UTC)": v["fecha"].replace("T", " ")[:19], "Cajero": v["vendedor"],
                            "Tipo": v["tipo_venta"], "Cantidad": v["cantidad"], "Subtotal (MXN)": v["subtotal"],
                            "IVA (MXN)": v["iva"], "Total (MXN)": v["total"], "Pago": v["metodo_pago"]} for v in reversed(sales)])
                    st.caption("Cantidad = kits, combos o refacciones según el tipo de venta. Utilidad bruta = subtotal menos costo de productos; todavía no resta gastos fijos.")
            else:
                empty_state("Aquí aparecerán tus comprobantes", "Abre Nueva venta, confirma una operación y vuelve a esta pestaña para descargar el ticket. Sólo se muestran las ventas de la sede seleccionada.")

if pagina == "Inventario y productos":
    st.caption("Existencias compartidas entre sedes · Las ventas descuentan sus componentes automáticamente.")
    low = [p for p in catalogo_comp.values() if p["stock"] <= p.get("punto_reorden", 0)]
    a, b, c = st.columns(3)
    a.metric("Productos en catálogo", len(catalogo_comp))
    b.metric("Productos por reabastecer", len(low), help="Su existencia llegó al punto de reorden: el nivel mínimo elegido para volver a comprar.")
    c.metric("Valor del inventario al costo", f"${sum(p['stock'] * p['costo_unitario'] for p in catalogo_comp.values()):,.2f}", help="Valor en MXN: existencias por costo actual. No es dinero cobrado ni utilidad.")
    catalog_tab, add_tab, edit_tab, stock_tab = st.tabs(["Catálogo y alertas", "Agregar producto", "Editar producto", "Entradas y salidas"])
    with catalog_tab:
        if not catalogo_comp:
            empty_state("El catálogo está vacío", "Abre Agregar producto para registrar tu primer artículo, su precio y sus existencias iniciales.")
        elif low:
            insight("Hay productos que necesitan reposición", f"{len(low)} de {len(catalogo_comp)} productos llegaron a su nivel mínimo. Activa Solo por reabastecer y registra la compra en Entradas y salidas.", tone="warning")
        section_intro("Encuentra un producto", "La lista muestra lo necesario para operar. Los costos y códigos están en el detalle ampliado.")
        a, b = st.columns([2, 1])
        search_product = a.text_input("Buscar producto", placeholder="Nombre, categoría o código de barras")
        category_filter = b.selectbox("Categoría del catálogo", ["Todas"] + sorted({item["categoria"] for item in catalogo_comp.values()}))
        only_low = st.checkbox("Solo por reabastecer")
        catalog_rows = []
        for product_id, item in catalogo_comp.items():
            needs_stock = item["stock"] <= item.get("punto_reorden", 0)
            searchable = " ".join(str(item.get(k, "")) for k in ("nombre", "categoria", "codigo_barras")) + " " + product_id
            if search_product.strip().casefold() not in searchable.casefold() or (only_low and not needs_stock):
                continue
            if category_filter != "Todas" and item["categoria"] != category_filter:
                continue
            state = "Sin existencias" if item["stock"] == 0 else "Reabastecer" if needs_stock else "Disponible"
            catalog_rows.append({"Foto": item.get("foto_url", "") or None, "Producto": item["nombre"], "Categoría": item["categoria"], "Existencias": item["stock"],
                "Estado": state, "Punto de reorden": item.get("punto_reorden", 0),
                "Costo unitario (MXN)": item["costo_unitario"], "Precio sin IVA (MXN)": item["precio_publico"],
                "Código de barras": item.get("codigo_barras", product_id)})
        if catalog_rows:
            catalog_rows.sort(key=lambda row: ({"Sin existencias": 0, "Reabastecer": 1, "Disponible": 2}[row["Estado"]], row["Producto"]))
            st.caption(f"{len(catalog_rows)} de {len(catalogo_comp)} productos · Primero aparecen los que requieren atención.")
            compact_rows = [{"Foto": row["Foto"], "Producto": row["Producto"], "Existencias": row["Existencias"],
                "Estado": {"Sin existencias": "🔴 Sin existencias", "Reabastecer": "🟠 Reabastecer", "Disponible": "🟢 Disponible"}[row["Estado"]],
                "Precio sin IVA (MXN)": row["Precio sin IVA (MXN)"]} for row in catalog_rows]
            st.dataframe(pd.DataFrame(compact_rows), width="stretch", hide_index=True, row_height=72, column_config={
                "Foto": st.column_config.ImageColumn("Foto", width=90, help="Doble clic para ampliar. Puedes cambiar o quitar la foto en Editar producto."),
                "Existencias": st.column_config.ProgressColumn("Existencias", min_value=0, max_value=max(1, max(row["Existencias"] for row in catalog_rows)), format="%d"),
                "Precio sin IVA (MXN)": st.column_config.NumberColumn(format="$%.2f"),
            })
            st.caption("La barra compara cantidades disponibles; el estado indica si alcanzaron el mínimo de reposición.")
            with st.expander("Ver costos, categorías, mínimos y códigos"):
                table([{k: v for k, v in row.items() if k != "Foto"} for row in catalog_rows])
        elif catalogo_comp:
            empty_state("No hay coincidencias", "Borra la búsqueda o elige Todas las categorías. Desactiva Solo por reabastecer para volver a ver el catálogo completo.")
    with add_tab:
        section_intro("Registra un producto", "Quedará disponible en el catálogo y en Punto de venta. El código de barras se genera si lo dejas vacío.")
        with st.form("alta_producto", clear_on_submit=False):
            a, b = st.columns([2, 1])
            new_name = a.text_input("Nombre del nuevo producto", max_chars=200)
            new_category = b.selectbox("Categoría del nuevo producto", ["Sensor", "Placa Base", "Almacenamiento", "Producción/Chasis", "Accesorio", "Otro"])
            new_specs = st.text_area("Descripción o especificaciones", max_chars=2000, height=80)
            a, b, c = st.columns(3)
            new_currency = a.selectbox("Moneda de compra del nuevo producto", ["MXN", "USD"])
            new_cost = b.number_input("Costo de compra por unidad", min_value=0.0, max_value=1e9, value=0.0, help="En la moneda elegida: pesos o dólares.")
            new_freight = c.number_input("Gastos por unidad en MXN", min_value=0.0, max_value=1e9, value=0.0, help="Flete y otros gastos adicionales; se suman al costo de compra.")
            a, b, c = st.columns(3)
            new_price = a.number_input("Precio de venta del nuevo producto sin IVA (MXN)", min_value=0.01, max_value=1e9, value=100.0)
            new_stock = b.number_input("Existencias iniciales", min_value=0, max_value=1000000, value=0)
            new_reorder = c.number_input("Mínimo para reabastecer", min_value=0, max_value=1000000, value=20)
            new_barcode = st.text_input("Código de barras (opcional)", max_chars=60, help="Letras, números, guion o guion bajo. No se permiten códigos repetidos.")
            with st.expander("Agregar fotografía (opcional)"):
                new_link = st.text_input("Enlace de la foto del nuevo producto (https)")
                new_upload = st.file_uploader("Foto del nuevo producto (PNG/JPG, máximo 1 MB)", type=["png", "jpg", "jpeg"], key="foto_nuevo_producto")
                st.caption("Elige un archivo o un enlace. Después podrás reemplazar o quitar la imagen desde Editar producto.")
            st.caption("Los productos comprados en USD usan el tipo de cambio guardado. Las existencias iniciales generan un movimiento de inventario.")
            if st.form_submit_button("Registrar producto", type="primary"):
                if not new_name.strip():
                    st.error("Escribe el nombre del producto.")
                elif new_upload and new_upload.size > 1_000_000:
                    st.error("La imagen supera 1 MB. Reduce su tamaño antes de cargarla.")
                elif new_upload and new_link.strip():
                    st.error("Elige un archivo o un enlace para la foto, no ambos.")
                else:
                    new_photo = new_link.strip()
                    if new_upload:
                        new_photo = f"data:{new_upload.type};base64," + base64.b64encode(new_upload.getvalue()).decode("ascii")
                    payload = {"nombre": new_name.strip(), "categoria": new_category, "especificaciones": new_specs,
                        "moneda_origen": new_currency, "costo_origen": new_cost, "costo_unitario": new_cost,
                        "gastos_importacion_unitarios": new_freight, "precio_publico": new_price,
                        "stock_inicial": int(new_stock), "punto_reorden": int(new_reorder), "foto_url": new_photo}
                    if new_barcode.strip():
                        payload["codigo_barras"] = new_barcode.strip()
                    created = api("POST", "/inventario/componentes", json=payload)
                    if created:
                        finish(f"Producto registrado: {new_name.strip()}. Ya puedes buscarlo en el catálogo y venderlo como refacción.")
    if catalogo_comp:
        with edit_tab:
            section_intro("1 · Elige el producto", "Consulta su estado actual y cambia sólo los campos que necesitas. Los cambios se aplican al pulsar Guardar producto.")
            pid = st.selectbox("Producto a administrar", list(catalogo_comp), format_func=lambda k: catalogo_comp[k]["nombre"])
            product = catalogo_comp[pid]
            a, b, c = st.columns(3)
            a.metric("Stock actual", product["stock"])
            b.metric("Precio sin IVA", money(product["precio_publico"]))
            margin = (product["precio_publico"] - product["costo_unitario"]) / product["precio_publico"] * 100 if product["precio_publico"] else None
            c.metric("Margen bruto", number(margin, " %"), help="Parte del precio que queda después del costo del producto. Aún no descuenta gastos fijos.")
            if margin is not None and margin < 0:
                st.warning("El precio está por debajo del costo: cada unidad vendida genera una pérdida bruta.")
            with st.form("producto_detalle"):
                a, b = st.columns([2, 1])
                product_name = a.text_input("Nombre del producto", product["nombre"], key=f"nombre_producto_{pid}")
                product_category = b.text_input("Categoría", product["categoria"], key=f"categoria_producto_{pid}")
                product_specs = st.text_area("Especificaciones", product.get("especificaciones", ""), height=80, key=f"especificaciones_producto_{pid}")
                section_intro("2 · Ajusta precio y reposición", "El costo es lo que pagas; el precio sin IVA es lo que cobras antes del impuesto.")
                a, b, c = st.columns(3)
                cost = a.number_input("Costo unitario en MXN", min_value=0.0, value=float(product["costo_unitario"]), disabled=product.get("moneda_origen") == "USD", key=f"costo_producto_{pid}")
                price = b.number_input("Precio sin IVA en MXN", min_value=0.01, value=float(product["precio_publico"]), key=f"precio_producto_{pid}")
                reorder = c.number_input("Punto de reorden", min_value=0, value=int(product.get("punto_reorden", 20)), help="El sistema sugiere comprar cuando las existencias llegan a este número o quedan por debajo.", key=f"reorden_producto_{pid}")
                barcode = st.text_input("Código de barras / identificador", product.get("codigo_barras", pid), key=f"codigo_producto_{pid}")
                if product.get("moneda_origen") == "USD":
                    st.caption("Este producto se compra en dólares. Cambia su costo en Origen y costo de importación; la conversión a pesos es automática.")
                with st.expander("Cambiar foto (opcional)"):
                    photo_link = st.text_input("Enlace de una foto nueva (https)", placeholder="https://...", key=f"foto_link_{pid}")
                    upload = st.file_uploader("Cargar foto propia del producto (PNG/JPG, máximo 1 MB)", type=["png", "jpg", "jpeg"], key=f"foto_archivo_{pid}")
                    remove_photo = st.checkbox("Quitar la foto actual", key=f"quitar_foto_{pid}")
                    st.caption("Si dejas estos campos vacíos se conserva la foto guardada. Usa un enlace o un archivo; para quitarla, marca únicamente la casilla.")
                if st.form_submit_button("Guardar producto", type="primary"):
                    if upload and upload.size > 1_000_000:
                        st.error("La imagen supera 1 MB (1,000,000 bytes). Reduce su tamaño.")
                    elif (upload and photo_link.strip()) or (remove_photo and (upload or photo_link.strip())):
                        st.error("Elige una sola acción para la foto: enlace, archivo o quitarla.")
                    else:
                        photo = "" if remove_photo else (photo_link.strip() or product.get("foto_url", ""))
                        if upload:
                            photo = f"data:{upload.type};base64," + base64.b64encode(upload.getvalue()).decode("ascii")
                        result = api("PUT", f"/inventario/componentes/{pid}", json={"nombre": product_name, "categoria": product_category, "especificaciones": product_specs, "costo_unitario": cost, "precio_publico": price, "punto_reorden": reorder, "codigo_barras": barcode, "foto_url": photo})
                        if result:
                            finish("Producto actualizado.")
            with st.expander("Origen y costo de importación"):
                with st.form("importacion_producto"):
                    a, b, c = st.columns(3)
                    currency = a.selectbox("Moneda de compra", ["MXN", "USD"], index=1 if product.get("moneda_origen") == "USD" else 0, key=f"moneda_producto_{pid}")
                    origin_cost = b.number_input("Costo en moneda de compra", min_value=0.0, value=float(product.get("costo_origen", product["costo_unitario"])), key=f"origen_producto_{pid}")
                    import_cost = c.number_input("Flete y otros gastos por unidad (MXN)", min_value=0.0, value=float(product.get("gastos_importacion_unitarios", 0)), key=f"flete_producto_{pid}")
                    st.caption("Para compras en USD: costo en dólares × tipo de cambio guardado + flete y gastos en pesos. Las ventas anteriores conservan su costo histórico.")
                    if st.form_submit_button("Aplicar origen y recalcular costo"):
                        result = api("PUT", f"/inventario/componentes/{pid}", json={"moneda_origen": currency, "costo_origen": origin_cost, "gastos_importacion_unitarios": import_cost})
                        if result:
                            # El siguiente render debe mostrar el costo recalculado, no el valor anterior del widget.
                            st.session_state.pop(f"costo_producto_{pid}", None)
                            finish("Origen actualizado y costo del producto recalculado.")
            with st.expander("Foto y etiqueta para imprimir"):
                a, b = st.columns(2)
                with a:
                    if product.get("foto_url"):
                        st.image(product["foto_url"], caption=product["nombre"], width=220)
                        creditos_foto(product)
                    else:
                        st.info("Este producto todavía no tiene foto. Abre Cambiar foto (opcional) en el formulario de edición para añadirla.")
                with b:
                    from barcode import Code128
                    from barcode.writer import SVGWriter
                    barcode_image = io.BytesIO()
                    Code128(product.get("codigo_barras", pid), writer=SVGWriter()).write(barcode_image, options={"module_width": 0.25, "module_height": 12.0, "quiet_zone": 3.0, "font_size": 9, "text_distance": 3.0})
                    barcode_svg = barcode_image.getvalue()
                    st.image(barcode_svg.decode("utf-8"), caption="Etiqueta Code 128", width=320)
                    st.download_button("Descargar etiqueta de código de barras", barcode_svg, f"codigo_{pid}.svg", "image/svg+xml")
        with stock_tab:
            section_intro("Registra una compra, devolución o merma", "Elige el producto y explica el movimiento. Las salidas por ventas ya se registran automáticamente.")
            stock_pid = st.selectbox("Producto para entrada o salida", list(catalogo_comp), format_func=lambda k: f"{catalogo_comp[k]['nombre']} · {catalogo_comp[k]['stock']} disponibles")
            st.metric("Existencias antes del movimiento", catalogo_comp[stock_pid]["stock"])
            with st.expander("Cómo indicar una entrada o una salida"):
                st.markdown("**Entrada:** escribe una cantidad positiva, como **10**, para agregar diez unidades.\n\n**Salida:** escribe una cantidad negativa, como **−2**, para retirar dos. No se permiten existencias negativas.")
            with st.form("movimiento_stock"):
                amount = st.number_input("Cantidad: positiva para entrada, negativa para salida", min_value=-100000, max_value=100000, value=1, step=1, help="Ejemplo: 10 agrega diez unidades; -2 retira dos. No se permite dejar existencias negativas.")
                reason = st.text_input("Motivo", placeholder="Compra a proveedor / devolución / merma")
                if st.form_submit_button("Registrar movimiento", type="primary", width="stretch"):
                    if amount == 0 or not reason.strip():
                        st.error("Indica una cantidad distinta de cero y escribe el motivo del movimiento.")
                    else:
                        result = api("POST", "/inventario/movimiento", json={"componente_id": stock_pid, "cantidad": amount, "motivo": reason.strip()})
                        if result:
                            finish("Movimiento de inventario registrado.")
    else:
        with edit_tab:
            empty_state("No hay productos para editar", "Cuando el catálogo tenga productos registrados, aquí podrás ajustar precios, mínimos y fotos.")
        with stock_tab:
            empty_state("Primero necesitas un producto", "Los movimientos se aplican a productos existentes. Revisa el catálogo con el gerente antes de registrar una entrada o salida.")
    with stock_tab:
        st.subheader("Últimos movimientos")
        moves = api("GET", "/inventario/movimientos", default={})
        move_rows = moves.get("movimientos", []) if isinstance(moves, dict) else moves
        if move_rows:
            table(list(reversed(move_rows))[:5])
            if len(move_rows) > 5:
                with st.expander(f"Ver los {len(move_rows)} movimientos registrados"):
                    table(list(reversed(move_rows)))
        else:
            empty_state("Todavía no hay movimientos", "Las compras, devoluciones, mermas y salidas registradas aparecerán aquí para consultar su motivo.")

if pagina == "Finanzas y tendencias":
    if not datos_sucursal:
        empty_state("Selecciona una sede para comenzar", "Elige una sede en el menú lateral. Si aún no hay ninguna, el gerente puede crearla en Administración → Sedes y ubicación.")
    else:
        st.caption(f"Sede: {datos_sucursal['nombre']} · Importes en pesos mexicanos (MXN).")
        ventas_tab, escenario_tab, tendencia_tab = st.tabs(["Ventas registradas", "Simular inversión", "Mercado agrícola"])
        report = api("GET", f"/analisis/reportes/{sucursal_activa_id}", default={})
        metrics = report.get("indicadores", {})
        series = report.get("series_mensuales", [])
        with ventas_tab:
            section_intro("¿Cómo van las ventas?", "Resultados acumulados de las operaciones que sí se registraron en esta sede.")
            if series and metrics:
                gross_profit = metrics.get("utilidad_bruta", 0) or 0
                insight("Lo que queda después de pagar los productos", f"La utilidad bruta acumulada es {money(gross_profit)}. Todavía falta descontar gastos fijos, impuestos sobre la renta y financiamiento.", tone="success" if gross_profit >= 0 else "warning")
            elif not report:
                empty_state("No se pudo cargar el resumen", "Vuelve a abrir este módulo para consultar las ventas. No se modificaron tus registros.")
            elif not series:
                next_sale = "Registra una venta en Operación → Punto de venta" if "tpv" in permisos_usuario else "Pide al cajero o al gerente que registre una venta"
                empty_state("Aún no hay ventas en esta sede", f"{next_sale}. Después aparecerán aquí los importes y la evolución mensual. Puedes explorar un ejercicio ahora en Simular inversión.")
            if metrics:
                a, b, c = st.columns(3)
                a.metric("Ventas sin IVA", money(metrics.get("ventas_netas")), help="Suma de las ventas antes de agregar IVA.")
                b.metric("Utilidad bruta", money(metrics.get("utilidad_bruta")), help="Ventas sin IVA menos el costo histórico de los productos vendidos.")
                c.metric("Margen bruto", number(metrics.get("margen_bruto_pct"), " %"), help="Porcentaje de las ventas sin IVA que queda después del costo de los productos.")
            if series:
                frame = pd.DataFrame(series).rename(columns={"mes": "Mes", "ventas_netas": "Ventas sin IVA", "costo_ventas": "Costo de ventas", "utilidad_bruta": "Utilidad bruta", "unidades": "Unidades"})
                with st.container(border=True):
                    section_intro("Ventas y resultado por mes", "Compara lo vendido, el costo de los productos y la diferencia entre ambos.")
                    fig = px.bar(frame, x="Mes", y=["Ventas sin IVA", "Costo de ventas", "Utilidad bruta"], barmode="group",
                        labels={"value": "Importe (MXN)", "variable": "Concepto"},
                        color_discrete_map={"Ventas sin IVA": "#2563EB", "Costo de ventas": "#F59E0B", "Utilidad bruta": "#13866B"})
                    fig.update_layout(legend_title_text="", yaxis_tickprefix="$", hovermode="x unified", height=340, margin=dict(t=15, b=30), legend=dict(orientation="h", y=-0.22))
                    st.plotly_chart(fig, width="stretch")
                with st.expander("Ver cifras mensuales y ventas por cajero"):
                    table(frame.to_dict("records"))
                    st.markdown("**Ventas por cajero · sin IVA**")
                    by_cashier = metrics.get("ventas_por_cajero", {})
                    table([{"Cajero": k, **(v if isinstance(v, dict) else {"Ventas sin IVA (MXN)": v})} for k, v in by_cashier.items()] if isinstance(by_cashier, dict) else by_cashier)
            if metrics:
                with st.expander("Desglose de cobros e inventario"):
                    a, b, c = st.columns(3)
                    a.metric("IVA cobrado", money(metrics.get("iva_cobrado")))
                    b.metric("Total cobrado con IVA", money(metrics.get("total_cobrado")))
                    c.metric("Costo de lo vendido", money(metrics.get("costo_ventas")))
                    a, b = st.columns(2)
                    a.metric("Inventario central a costo", money(metrics.get("valor_inventario_costo")))
                    b.metric("Productos por reponer", metrics.get("productos_reorden", 0))
                    st.caption("El inventario es compartido entre sedes y usa los costos actuales. Las ventas conservan el costo de la fecha en que se cobraron.")
        with escenario_tab:
            section_intro("Prueba cuánto tendrías que vender", "Ejercicio a 3 años con ventas iguales cada mes, sin IVA. Cambiar estos valores no modifica productos, sedes ni ventas registradas.")
            controls, results = st.columns([1, 1.5], gap="large")
            with controls, st.container(border=True):
                st.markdown("**1 · Define tu escenario**")
                units = st.number_input("Unidades proyectadas por mes", min_value=0, max_value=1000000, value=85, step=1, help="Cantidad de kits que supones vender cada mes, no ventas ya registradas.")
                st.caption("Empieza cambiando esta cantidad. El resultado se recalcula automáticamente.")
                with st.expander("Modificar supuestos del escenario (no cambia la sede)"):
                    st.caption("Valores iniciales de la sede en MXN. Revisa estos supuestos: no se actualizan al cambiar productos, tipo de cambio o personal.")
                    investment = st.number_input("Inversión inicial", min_value=0.0, value=float(datos_sucursal["inversion_inicial"]), help="Desembolso inicial total del proyecto.")
                    fixed = st.number_input("Costos fijos mensuales", min_value=0.0, value=float(datos_sucursal["costos_fijos_mensuales"]), help="Gastos mensuales aunque no haya ventas, como renta o nómina.")
                    cost = st.number_input("Costo variable por unidad", min_value=0.0, value=float(datos_sucursal["costo_variable_unitario"]), help="Costo supuesto de producir un kit.")
                    price = st.number_input("Precio por unidad sin IVA", min_value=0.01, value=float(datos_sucursal["precio_venta_unitario"]), help="Precio supuesto de un kit antes de agregar IVA.")
                with st.expander("Tasas para evaluar la inversión"):
                    discount = st.number_input("Tasa de descuento anual (%)", min_value=0.0, max_value=100.0, value=15.0, help="Rendimiento mínimo supuesto para comparar dinero futuro con dinero de hoy.")
                    benchmark = st.number_input("Tasa de referencia anual supuesta (%)", min_value=0.0, max_value=100.0, value=11.0, help="Comparación elegida para el ejercicio. No es una cotización de CETES en tiempo real.")
                st.caption(f"Precio supuesto: {money(price)} por kit · Costo variable: {money(cost)} por kit.")
            simulated = api("POST", "/analisis/simulador", json={"unidades_vendidas_mes": units, "inversion_inicial": investment,
                "costos_fijos_mensuales": fixed, "costo_variable_unitario": cost, "precio_venta_unitario": price,
                "tasa_descuento": discount, "tasa_cetes": benchmark})
            with results:
                st.markdown("**2 · Entiende el resultado**")
                if simulated:
                    indicators = simulated["indicadores_duros"]
                    contribution = price - cost
                    monthly_flow = indicators.get("flujo_caja_mensual", 0)
                    if monthly_flow > 0:
                        insight("El escenario cubre los gastos mensuales", f"Con {units:,} kits al mes quedan {money(monthly_flow)} después de costos fijos y variables.", tone="success")
                    elif monthly_flow < 0:
                        insight("El escenario aún no cubre los gastos", f"Con {units:,} kits al mes faltan {money(abs(monthly_flow))} para cubrir costos fijos y variables.", tone="warning")
                    else:
                        insight("Ingresos y gastos quedan iguales", "El resultado mensual de este escenario es cero.")
                    a, b = st.columns(2)
                    a.metric("Resultado operativo mensual", money(monthly_flow), help="Ingresos menos costos variables y fijos. No incluye IVA, ISR ni financiamiento.")
                    b.metric("Mínimo para cubrir gastos", f"{math.ceil(fixed / contribution):,} kits/mes" if contribution > 0 else "No alcanzable", help="Unidades completas necesarias para cubrir costos fijos y variables con este precio.")
                    st.caption(f"Cada kit aporta {money(contribution)} para cubrir los gastos fijos. El resultado es hipotético; no es una venta registrada.")
                    if st.button("Generar dictamen financiero del escenario", type="primary", width="stretch"):
                        result = api("POST", "/analisis/dictamen", json={"nombre_negocio": datos_sucursal["nombre"], "unidades_vendidas": units,
                            "punto_equilibrio_uds": indicators.get("punto_equilibrio_uds"), "vpn": indicators.get("vpn"), "tir": indicators.get("tir"),
                            "spread": indicators.get("spread_cetes"), "estado_inversion": indicators.get("estado", "")})
                        if result:
                            st.session_state.dictamen = result.get("dictamen_ia", result.get("dictamen", ""))
                            st.session_state.dictamen_escenario = (sucursal_activa_id, units, discount, benchmark, investment, fixed, cost, price)
                    st.caption("Genera una explicación escrita de los números de este ejercicio.")
                else:
                    empty_state("No se pudo calcular el escenario", "Revisa los valores y vuelve a intentarlo. Las ventas registradas no se modificaron.")
            if simulated:
                with st.container(border=True):
                    section_intro("¿En qué se van los ingresos?", "Los ingresos deben alcanzar para cubrir ambos tipos de costo.")
                    bars_frame = pd.DataFrame({"Concepto": ["Ingresos", "Costos variables", "Costos fijos"], "MXN por mes": [units * price, units * cost, fixed]})
                    bars = px.bar(bars_frame, x="Concepto", y="MXN por mes", color="Concepto",
                        color_discrete_map={"Ingresos": "#13866B", "Costos variables": "#F59E0B", "Costos fijos": "#64748B"})
                    bars.update_layout(showlegend=False, yaxis_tickprefix="$", height=300, margin=dict(t=15, b=25))
                    st.plotly_chart(bars, width="stretch")
                if st.session_state.get("dictamen") and st.session_state.get("dictamen_escenario") == (sucursal_activa_id, units, discount, benchmark, investment, fixed, cost, price):
                    with st.container(border=True):
                        section_intro("Explicación de tu escenario", "Interpretación automática basada en los valores que acabas de probar.")
                        st.markdown(st.session_state.dictamen)
                with st.expander("Rentabilidad de la inversión: VAN, TIR y recuperación"):
                    st.caption("Indicadores del ejercicio a 3 años. Abre la ayuda de cada cifra para conocer su significado.")
                    a, b, c = st.columns(3)
                    a.metric("VAN / VPN a 3 años", money(indicators.get("vpn")), help="Flujos futuros a valor de hoy, menos la inversión inicial, usando tu tasa de descuento.")
                    b.metric("TIR anual", number(indicators.get("tir"), " %"), help="Tasa que hace que el VAN sea cero. No siempre puede calcularse.")
                    c.metric("Recuperación simple", number(indicators.get("recuperacion_meses"), " meses"), help="Inversión inicial entre resultado mensual positivo; no ajusta por el valor del dinero en el tiempo.")
                    a, b = st.columns(2)
                    a.metric("ROI anual simple", number(indicators.get("roi_anual_pct"), " %"), help="Resultado operativo anual entre inversión inicial, como porcentaje.")
                    b.metric("TIR menos tasa de referencia", number(indicators.get("spread_cetes"), " puntos"), help="Diferencia en puntos porcentuales frente a la tasa que elegiste.")
                    if indicators.get("tir") is None:
                        st.info("La TIR no está definida para estos flujos. Puede ocurrir sin inversión inicial o sin resultados positivos.")
                    for warning in simulated.get("advertencias", []):
                        if "TIR" not in warning:
                            st.warning(warning)
                    st.caption("Modelo simplificado: tres flujos anuales iguales. No incluye financiamiento, depreciación, ISR ni valor residual. Los resultados dependen de los supuestos capturados.")
        with tendencia_tab:
            section_intro("Precios reales del mercado agrícola", "Precios internacionales mensuales de referencia. Ayudan a observar el contexto del sector; no son ventas de AgTech ni precios locales de México.")
            market = api("GET", "/analisis/mercado", default={})
            if market.get("available") and market.get("series"):
                if market.get("status") == "stale":
                    st.warning(market.get("message", "Se muestran los últimos datos reales guardados; no se pudo actualizar la consulta."))
                series_by_id = {row["id"]: row for row in market["series"]}
                a, b = st.columns([2, 1])
                crop = a.selectbox("Producto agrícola", list(series_by_id), format_func=lambda key: series_by_id[key]["name"])
                months = b.selectbox("Periodo mostrado", [12, 24, 36], index=1, format_func=lambda n: f"Últimos {n} meses")
                chosen = series_by_id[crop]
                if chosen.get("note"):
                    st.info(chosen["note"])
                points = chosen["points"][-months:]
                latest = points[-1]
                previous = chosen["points"][-2] if len(chosen["points"]) > 1 else None
                year_ago = chosen["points"][-13] if len(chosen["points"]) > 12 else None
                monthly = (latest["value"] / previous["value"] - 1) * 100 if previous and previous["value"] else None
                annual = (latest["value"] / year_ago["value"] - 1) * 100 if year_ago and year_ago["value"] else None
                a, b, c = st.columns(3)
                a.metric("Último precio (USD / tonelada)", f"${latest['value']:,.2f}")
                b.metric("Cambio mensual", number(monthly, " %"))
                c.metric("Cambio frente al mismo mes del año anterior", number(annual, " %"))
                st.caption(f"Mes del último dato: {latest['date'][:7]} · Unidad: {chosen.get('unit', market.get('unit', 'USD por tonelada métrica'))}. No incluye flete ni impuestos de una compra particular.")
                price_frame = pd.DataFrame(points).rename(columns={"date": "Mes", "value": "Precio (USD por tonelada)"})
                price_frame["Mes"] = pd.to_datetime(price_frame["Mes"])
                fig = px.line(price_frame, x="Mes", y="Precio (USD por tonelada)", markers=True, color_discrete_sequence=["#13866B"])
                fig.update_layout(height=350, margin=dict(t=20, b=20), yaxis_tickprefix="$", hovermode="x unified")
                st.plotly_chart(fig, width="stretch")
                st.caption("Una variación positiva significa un precio mayor, no necesariamente más demanda. Esta serie no predice ventas de sensores o kits.")
                st.link_button("Consultar la fuente: Banco Mundial", market["source_url"])
                st.caption(f"Fuente: {market['source']} · Última consulta (UTC): {market.get('last_checked', 'No disponible')} · Se revisan nuevas publicaciones cada 24 horas al usar este módulo.")
                with st.expander("Datos y descarga"):
                    table(price_frame.assign(Mes=price_frame["Mes"].dt.strftime("%Y-%m")).to_dict("records"))
                    export = price_frame.copy()
                    export["Fuente"] = market["source_url"]
                    st.download_button("Descargar precios consultados (CSV)", export.to_csv(index=False).encode("utf-8-sig"), f"precios_{crop}.csv", "text/csv")
            else:
                empty_state("No hay precios disponibles en este momento", market.get("message", "No se pudo consultar la fuente. Vuelve a abrir Finanzas para reintentar; no se sustituyen precios reales por datos inventados."))

if pagina == "Personal y usuarios":
    st.caption("Personal registra a tu equipo y sus sueldos. Cuentas de acceso controla quién puede entrar al sistema.")
    personnel_sections = (["Personal"] if "personal" in permisos_usuario else []) + (["Cuentas de acceso"] if "usuarios" in permisos_usuario else [])
    personnel_tabs = dict(zip(personnel_sections, st.tabs(personnel_sections)))
    if "personal" in permisos_usuario:
        with personnel_tabs["Personal"]:
            staff_data = api("GET", "/personal", default={})
            staff = staff_data.get("personal", [])
            active_staff = [p for p in staff if p.get("activo", True)]
            a, b, c = st.columns(3)
            a.metric("Empleados activos", len(active_staff))
            b.metric("Áreas con personal activo", len({p["area"] for p in active_staff}))
            c.metric("Nómina mensual registrada", money(staff_data.get("nomina_mensual", 0)))
            st.caption("La nómina de empleados activos no se suma automáticamente a los costos fijos. Revisa que esté contemplada en tu escenario financiero sin contarla dos veces.")
            directorio_tab, alta_personal_tab, editar_personal_tab = st.tabs(["Directorio", "Agregar empleado", "Actualizar empleado"])
            with directorio_tab:
                section_intro("Tu equipo", "Consulta quién trabaja en cada área. Las altas y los cambios están en las pestañas de al lado.")
                if staff:
                    area_options = sorted({person["area"] for person in staff})
                    staff_area = st.selectbox("Filtrar equipo por área", ["Todas las áreas"] + area_options)
                    staff_query = st.text_input("Buscar en el equipo", placeholder="Nombre o puesto").strip().casefold()
                    staff_filtered = [person for person in staff if (staff_area == "Todas las áreas" or person["area"] == staff_area)
                                      and staff_query in f"{person['nombre']} {person['puesto']}".casefold()]
                    if not staff_filtered:
                        st.info("No hay personas con esos filtros. Prueba otra búsqueda o elige Todas las áreas.")
                    else:
                        table([{"Nombre": p["nombre"], "Puesto": p["puesto"], "Área": p["area"], "Turno": p["turno"],
                            "Salario mensual (MXN)": p["salario_mensual"], "Estado": "Activo" if p.get("activo", True) else "Inactivo"} for p in staff_filtered])
                else:
                    empty_state("Todavía no hay empleados", "Abre Agregar empleado para registrar el primer integrante del equipo. Crear su acceso al sistema es un paso independiente.")
            with alta_personal_tab:
                st.caption("Registrar un empleado no crea una cuenta para iniciar sesión; eso se hace en Cuentas de acceso.")
                with st.form("nuevo_empleado"):
                    st.markdown("**1 · Identidad y función**")
                    a, b, c = st.columns(3)
                    name = a.text_input("Nombre del empleado")
                    position = b.text_input("Puesto", "Operador")
                    area = c.selectbox("Área del empleado", staff_data.get("areas") or ["Administración", "Ventas", "Inventario", "Producción", "Ingeniería", "Finanzas"])
                    st.markdown("**2 · Jornada y sueldo**")
                    a, b = st.columns(2)
                    salary = a.number_input("Salario mensual (MXN)", min_value=0.0, value=10000.0)
                    shift = b.selectbox("Turno", ["Matutino", "Vespertino", "Nocturno", "Mixto"])
                    if st.form_submit_button("Registrar empleado", type="primary"):
                        if not name.strip() or not position.strip():
                            st.error("Escribe el nombre y el puesto del empleado.")
                        else:
                            result = api("POST", "/personal", json={"nombre": name.strip(), "puesto": position.strip(), "area": area, "salario_mensual": salary, "turno": shift})
                            if result:
                                finish("Empleado registrado.")
            with editar_personal_tab:
                if staff:
                    people = {str(p["id"]): p for p in staff}
                    person_id = st.selectbox("Empleado", list(people), format_func=lambda k: people[k]["nombre"])
                    person = people[person_id]
                    with st.form("editar_empleado"):
                        a, b = st.columns(2)
                        name = a.text_input("Nombre", person["nombre"], key=f"nombre_empleado_{person_id}")
                        position = b.text_input("Puesto actual", person["puesto"], key=f"puesto_empleado_{person_id}")
                        area = a.text_input("Área actual", person["area"], key=f"area_empleado_{person_id}")
                        shift = b.text_input("Turno actual", person["turno"], key=f"turno_empleado_{person_id}")
                        salary = a.number_input("Salario actualizado (MXN)", min_value=0.0, value=float(person["salario_mensual"]), key=f"salario_empleado_{person_id}")
                        active = b.checkbox("Empleado activo", bool(person.get("activo", True)), key=f"activo_empleado_{person_id}", help="Un empleado inactivo permanece en el historial, pero su sueldo deja de sumarse a la nómina.")
                        if st.form_submit_button("Actualizar empleado"):
                            if not all(value.strip() for value in (name, position, area, shift)):
                                st.error("Completa nombre, puesto, área y turno.")
                            else:
                                result = api("PUT", f"/personal/{person_id}", json={"nombre": name.strip(), "puesto": position.strip(), "area": area.strip(), "turno": shift.strip(), "salario_mensual": salary, "activo": active})
                                if result:
                                    finish("Empleado actualizado.")
                else:
                    empty_state("Aún no hay empleados para actualizar", "Registra primero una persona en Agregar empleado. Después podrás modificar su puesto, sueldo o estado.")
    if "usuarios" in permisos_usuario:
        with personnel_tabs["Cuentas de acceso"]:
            users_data = api("GET", "/usuarios", default={})
            users = users_data.get("usuarios", [])
            roles_data = users_data.get("roles", {})
            roles = list(roles_data) or ["gerente", "cajero", "ingeniero"]
            areas = users_data.get("areas", []) or ["Administración", "Ventas", "Ingeniería"]
            a, b, c = st.columns(3)
            a.metric("Cuentas activas", sum(bool(user.get("activo", True)) for user in users))
            b.metric("Cuentas inactivas", sum(not user.get("activo", True) for user in users))
            c.metric("Perfiles de acceso", len(roles))
            lista_cuentas_tab, alta_cuenta_tab, editar_cuenta_tab = st.tabs(["Cuentas registradas", "Crear cuenta", "Modificar acceso"])
            with lista_cuentas_tab:
                section_intro("Quién puede entrar", "Revisa el usuario, el perfil y el estado antes de modificar un acceso.")
                with st.expander("Qué permite cada perfil"):
                    st.markdown("**Gerente:** administra toda la aplicación.\n\n**Cajero:** registra ventas y descarga comprobantes.\n\n**Ingeniero:** administra el inventario y consulta finanzas y presupuestos.")
                if users:
                    table([{"Usuario": u["username"], "Nombre": u.get("nombre", ""), "Rol": u.get("rol", u.get("rol_codigo", "")),
                            "Área": u.get("area", ""), "Estado": "Activa" if u.get("activo", True) else "Inactiva"} for u in users])
                else:
                    empty_state("No hay cuentas para mostrar", "Abre Crear cuenta para dar acceso a una persona y asignarle un perfil.")
            with alta_cuenta_tab:
                st.caption("Usa un usuario único y asigna el perfil que corresponda a sus tareas.")
                with st.form("nuevo_usuario"):
                    st.markdown("**1 · Persona y credenciales**")
                    a, b = st.columns(2)
                    username = a.text_input("Nuevo usuario", help="Nombre que se escribirá al iniciar sesión; usa letras, números, punto, guion o guion bajo.")
                    fullname = b.text_input("Nombre de la persona")
                    password = a.text_input("Contraseña nueva (mínimo 8 caracteres)", type="password")
                    st.markdown("**2 · Perfil y área**")
                    a, b = st.columns(2)
                    role = a.selectbox("Rol de acceso", roles)
                    area = b.selectbox("Área de la cuenta", areas)
                    if st.form_submit_button("Crear usuario", type="primary"):
                        if not username.strip() or not fullname.strip() or len(password) < 8:
                            st.error("Completa el usuario, el nombre y una contraseña de al menos 8 caracteres.")
                        else:
                            result = api("POST", "/usuarios", json={"username": username.strip(), "nombre": fullname.strip(), "password": password, "rol": role, "area": area})
                            if result:
                                finish("Usuario creado. Ya puede iniciar sesión con sus credenciales.")
            with editar_cuenta_tab:
                if users:
                    usernames = {u["username"]: u for u in users}
                    selected = st.selectbox("Cuenta", list(usernames))
                    user = usernames[selected]
                    own_account = selected == st.session_state.username
                    if own_account:
                        st.caption("Puedes cambiar tu área. Tu propia cuenta de gerente debe permanecer activa y conservar su rol.")
                    with st.form("editar_usuario"):
                        active = st.checkbox("Cuenta activa", bool(user.get("activo", True)), disabled=own_account, key=f"activa_cuenta_{selected}")
                        role = st.selectbox("Nuevo rol", roles, index=roles.index(user.get("rol_codigo")) if user.get("rol_codigo") in roles else 0, disabled=own_account, key=f"rol_cuenta_{selected}")
                        area = st.text_input("Área asignada", user.get("area", "Administración"), key=f"area_cuenta_{selected}")
                        if st.form_submit_button("Guardar acceso"):
                            if not area.strip():
                                st.error("Escribe el área de la cuenta.")
                            else:
                                result = api("PUT", f"/usuarios/{selected}", json={"activo": active, "rol": role, "area": area.strip()})
                                if result:
                                    finish("Acceso actualizado.")
                else:
                    empty_state("Aún no hay cuentas para modificar", "Crea una cuenta primero y después podrás cambiar su área, perfil o estado.")

if pagina == "Configuración":
    config = api("GET", "/configuracion", default={})
    saved_rate = float(config.get("tipo_cambio_usd_mxn", 20.0))
    saved_tax = float(config.get("iva_tasa", 0.16)) * 100
    a, b = st.columns(2)
    a.metric("Tipo de cambio guardado", f"${saved_rate:,.4f} MXN / USD")
    b.metric("IVA guardado", f"{saved_tax:g} %")
    st.caption("Valores compartidos por todas las sedes. El tipo de cambio automático usa la última referencia publicada, no una cotización de compra o venta de un banco.")
    parameters_tab, calculator_tab, backup_tab = st.tabs(["Parámetros", "Calculadora de importación", "Respaldo de datos"])
    with parameters_tab:
        automatic_rate = st.toggle("Actualizar tipo de cambio automáticamente", value=config.get("tipo_cambio_automatico", True))
        st.caption("Se consulta una nueva referencia cada 6 horas mientras usas la aplicación y al volver a abrirla si corresponde. El proveedor publica datos en días hábiles.")
        if config.get("tipo_cambio_fecha"):
            st.caption(f"Fecha de la referencia: {config['tipo_cambio_fecha']} · Fuente: {config.get('fuente_tipo_cambio', '')}")
        else:
            st.caption(f"Origen del valor guardado: {config.get('fuente_tipo_cambio', 'Manual')}.")
        if config.get("tipo_cambio_fuente_url"):
            st.link_button("Consultar fuente del tipo de cambio", config["tipo_cambio_fuente_url"])
        if config.get("tipo_cambio_estado") in {"stale", "unavailable"}:
            st.warning(config.get("tipo_cambio_mensaje") or "No se pudo actualizar la referencia. Se conserva el último valor guardado.")
        if st.button("Actualizar tipo de cambio ahora", disabled=not config.get("tipo_cambio_automatico", True)):
            with st.spinner("Consultando la última referencia publicada…"):
                updated_rate = api("POST", "/configuracion/actualizar-tipo-cambio", default={})
            if updated_rate:
                finish("Consulta terminada. Revisa la fecha y el estado de actualización del tipo de cambio.")
        section_intro("Valores que usa el sistema", "Consulta sus efectos y abre el formulario sólo cuando necesites cambiarlos.")
        a, b = st.columns(2)
        with a, st.container(border=True):
            st.markdown("**Tipo de cambio → costos de importación**")
            st.write(f"Por cada USD de compra, el sistema calcula ${saved_rate:,.2f} MXN antes de flete y otros gastos.")
            st.caption("Al guardar otro valor, se recalculan los costos actuales de productos comprados en USD.")
        with b, st.container(border=True):
            st.markdown("**IVA → total de ventas nuevas**")
            st.write(f"A cada $100.00 MXN del catálogo se añaden ${saved_tax:,.2f} MXN de IVA.")
            st.caption("Las ventas y comprobantes anteriores conservan sus importes originales.")
        with st.expander("Guardar modo de actualización e IVA", expanded=automatic_rate != config.get("tipo_cambio_automatico", True)):
            with st.form("configuracion"):
                a, b = st.columns(2)
                rate = a.number_input("Tipo de cambio manual: MXN por USD", min_value=0.01, max_value=1000.0, value=saved_rate, disabled=automatic_rate, format="%.4f", help="Sólo se utiliza al desactivar la actualización automática y guardar. Ejemplo: 20 significa veinte pesos por dólar.")
                tax = b.number_input("IVA (%)", min_value=0.0, max_value=100.0, value=saved_tax, help="Tasa del supuesto académico. Los precios del catálogo no incluyen este impuesto.")
                st.caption("Los cambios se aplican a todas las sedes al pulsar Guardar parámetros.")
                if st.form_submit_button("Guardar parámetros", type="primary"):
                    settings = {"tipo_cambio_automatico": automatic_rate, "iva_tasa": tax / 100}
                    if not automatic_rate:
                        settings["tipo_cambio_usd_mxn"] = rate
                    result = api("PUT", "/configuracion", json=settings)
                    if result:
                        finish("Parámetros guardados. Los comprobantes anteriores mantienen sus importes originales.")
    with calculator_tab:
        section_intro("¿Cuánto cuesta importar una unidad?", "Captura el precio y los gastos por unidad para ver el costo estimado en pesos. Esta calculadora no modifica productos.")
        with st.container(border=True):
            st.markdown("**1 · Datos de la compra**")
            a, b, c = st.columns(3)
            foreign = a.number_input("Precio de compra (USD)", min_value=0.0, value=50.0)
            freight = b.number_input("Flete por unidad (MXN)", min_value=0.0, value=100.0)
            extra = c.number_input("Otros costos por unidad (MXN)", min_value=0.0, value=0.0)
            st.caption(f"Conversión con el valor guardado: 1 USD = ${saved_rate:,.2f} MXN.")
        converted = foreign * saved_rate
        section_intro("2 · Costo estimado", "Compra convertida a pesos + flete + otros gastos. Importes por unidad, sin IVA.")
        a, b, c = st.columns(3)
        a.metric("Compra convertida a pesos", money(converted))
        b.metric("Flete y otros gastos", money(freight + extra))
        c.metric("Costo unitario estimado sin IVA", money(converted + freight + extra))
        costs_chart = pd.DataFrame({"Concepto": ["Compra en pesos", "Flete", "Otros gastos"], "Costo (MXN)": [converted, freight, extra]})
        if converted + freight + extra > 0:
            fig = px.bar(costs_chart, x="Costo (MXN)", y="Concepto", orientation="h", color="Concepto",
                         color_discrete_sequence=["#13866B", "#527A8D", "#D79B36"])
            fig.update_layout(showlegend=False, height=240, margin=dict(l=0, r=10, t=10, b=0), xaxis_tickprefix="$", yaxis_title="")
            st.plotly_chart(fig, width="stretch")
        with st.expander("Aplicar este cálculo a un producto"):
            st.markdown("1. Abre **Operación → Inventario → Editar producto**.\n2. Despliega **Origen y costo de importación** y elige USD.\n3. Captura el precio original en dólares; suma flete y otros gastos en pesos.\n4. Pulsa **Aplicar origen y recalcular costo**.")
    with backup_tab:
        section_intro("Conserva una copia de tus registros", "Prepara una copia actualizada y descárgala al terminar la demostración.")
        a, b = st.columns(2)
        with a, st.container(border=True):
            st.markdown("**1 · Preparar la copia**")
            st.caption("Incluye sedes, ventas, inventario, movimientos, personal y parámetros. Excluye cuentas, contraseñas y sesiones.")
            if st.button("Preparar respaldo JSON", type="primary", width="stretch"):
                backup = api("GET", "/respaldo")
                if backup:
                    st.session_state.respaldo_data = json.dumps(backup, ensure_ascii=False, indent=2)
        with b, st.container(border=True):
            st.markdown("**2 · Guardar el archivo**")
            if st.session_state.get("respaldo_data"):
                st.success("Tu copia está lista para descargar.")
                st.download_button("Descargar respaldo", st.session_state.respaldo_data, "respaldo_agtech.json", "application/json", width="stretch")
                st.caption("Si registras más cambios, prepara otra copia. Guárdala en un lugar privado: contiene datos de personal.")
            else:
                st.caption("Pulsa Preparar respaldo JSON. Aquí aparecerá la descarga.")
        with st.expander("Qué debes saber de esta copia"):
            st.write("El alojamiento puede perder los datos locales al reconstruir la aplicación. Conserva el archivo descargado y el reporte Excel de la barra lateral.")
            st.caption("El archivo JSON sirve como copia de los datos; la aplicación todavía no tiene una opción para restaurarlo automáticamente.")

if pagina == "Ingeniería y presupuestos":
    if "ingenieria" not in permisos_usuario:
        st.error("No tienes acceso a este módulo con tu cuenta actual.")
    else:
        st.caption("Propuestas de planta y procesos del ejercicio académico. Importes en MXN; capacidades y consumos estimados.")
        comparacion_tab, detalle_tab, proceso_tab, operacion_tab = st.tabs(["Comparar presupuestos", "Detalle del presupuesto", "Proceso de producción", "Costos de operación"])
        budgets = datos_presupuestos.get("detalle_presupuestos", [])
        with comparacion_tab:
            section_intro("Compara antes de elegir", "Empieza por la inversión inicial y el costo por kit. Abre Detalle del presupuesto para revisar qué incluye cada alternativa.")
            if budgets:
                budget_cards = st.columns(len(budgets))
                for column, budget in zip(budget_cards, budgets):
                    with column.container(border=True):
                        st.markdown(f"**{nombre_presupuesto(budget['id_presupuesto'])}**")
                        if datos_sucursal and budget["id_presupuesto"] == datos_sucursal.get("presupuesto_seleccionado"):
                            st.caption("✓ Presupuesto base de la sede activa")
                        else:
                            st.caption("Alternativa de referencia")
                        st.metric("Inversión inicial (MXN)", f"${budget['capex_total_mxn']:,.0f}")
                        st.markdown(f"**{money(budget['costo_produccion_kit_mxn'])}** por kit producido")
                        st.caption(f"Precio sugerido sin IVA: {money(budget['precio_publico_kit_mxn'])}")
                st.caption("Consultar una alternativa no cambia la sede. El presupuesto base se elige al registrar una sede en Administración → Sedes y ubicación.")
                with st.container(border=True):
                    section_intro("¿En qué se invierte el dinero?", "Cada barra suma maquinaria, instalaciones y productos del lote inicial.")
                    comparison = pd.DataFrame([{"Alternativa": nombre_presupuesto(p["id_presupuesto"]), "Maquinaria": p["inversion_maquinaria_mxn"], "Almacén y planta": p["inversion_almacenamiento_planta_mxn"] + p["inversion_produccion_instalacion_mxn"], "Inventario de arranque": p["costo_inventario_inicial_mxn"]} for p in budgets])
                    fig = px.bar(comparison, x="Alternativa", y=["Maquinaria", "Almacén y planta", "Inventario de arranque"], barmode="stack",
                        labels={"value": "Inversión (MXN)", "variable": "Concepto"}, color_discrete_sequence=["#2563EB", "#13866B", "#F59E0B"])
                    fig.update_layout(legend_title_text="", yaxis_tickprefix="$", height=360, margin=dict(t=15, b=25), legend=dict(orientation="h", y=-0.25))
                    st.plotly_chart(fig, width="stretch")
                    st.caption("El inventario de arranque forma parte de la inversión, pero no es un activo fijo.")
                with st.expander("Ver comparación completa y criterios de evaluación"):
                    comparison_rows = [{("Inversión inicial total (MXN)" if k == "CAPEX Total (MXN)" else k): v for k, v in row.items()} for row in datos_presupuestos.get("resumen_disparidad", [])]
                    table(comparison_rows)
                    st.markdown("**Criterios y calificaciones del ejercicio**")
                    table(datos_presupuestos.get("tabla_multicriterio", []))
                    st.caption("Los puntajes son valoraciones académicas. CPH significa componentes colocados por hora; no equivale a kits terminados por hora.")
            else:
                empty_state("No se pudieron cargar los presupuestos", "Vuelve a abrir este módulo para consultar las propuestas de referencia.")
        with detalle_tab:
            section_intro("Revisa qué incluye cada propuesta", "Elige un presupuesto y abre sólo el detalle que necesites.")
            if budgets:
                selected_budget = st.selectbox("Presupuesto a consultar", range(len(budgets)), format_func=lambda i: budgets[i]["nombre_corto"])
                p_obj = budgets[selected_budget]
                a, b, c = st.columns(3)
                a.metric("Inversión inicial total", money(p_obj["capex_total_mxn"]))
                b.metric("Costo estimado por kit", money(p_obj["costo_produccion_kit_mxn"]))
                c.metric("Precio sugerido sin IVA", money(p_obj["precio_publico_kit_mxn"]))
                with st.container(border=True):
                    st.markdown(f"**{p_obj['arquitectura_base']}**")
                    st.caption(f"Capacidad de referencia: {p_obj['capacidad_planta']}")
                    st.caption("Estos importes pertenecen al presupuesto. Las ventas utilizan los precios y costos actuales de Inventario, que pueden ser distintos.")
                with st.expander("Ver maquinaria, adecuaciones e inventario de arranque"):
                    table(p_obj["tabla_maquinaria_y_produccion"])
                with st.expander("Ver componentes y cantidades del lote inicial"):
                    table(p_obj["tabla_inventario_kit"])
                    st.caption("Las cantidades del presupuesto no se agregan automáticamente al inventario disponible para venta.")
                with st.expander("Comparar materiales de los tres kits"):
                    st.caption("Lista de materiales, también llamada BOM. Los importes corresponden al presupuesto de referencia.")
                    table(datos_presupuestos.get("tabla_bom_kits", []))
            else:
                empty_state("No hay un presupuesto disponible", "Vuelve a abrir este módulo para intentar cargar las propuestas.")
        with proceso_tab:
            section_intro("Del componente al kit terminado", "Elige una línea para conocer sus etapas y tiempos estimados. Puedes abrir el diagrama técnico al final.")
            linea_sel_flujo = st.selectbox("Línea de producción", options=["P1_ECONOMICO", "P2_OBJETIVO", "P3_PREMIUM"],
                format_func=lambda x: {"P1_ECONOMICO": "Económica · ESP32", "P2_OBJETIVO": "Objetivo · Radxa", "P3_PREMIUM": "Premium · Raspberry Pi 5"}[x])
            flujo_data = api("GET", f"/ingenieria/flujo-produccion?presupuesto_id={linea_sel_flujo}", default={})
            if flujo_data:
                steps = flujo_data.get("tabla_pasos", [])
                a, b = st.columns(2)
                a.metric("Tiempo estimado del ciclo", f"{flujo_data['tiempo_total_optimo_min']} min")
                b.metric("Etapas del proceso", len(steps))
                st.caption("Tiempos del proceso de referencia; no se están midiendo máquinas reales.")
                step_chart_rows = []
                for index, row in enumerate(steps, start=1):
                    duration = row.get("Tiempo (min)")
                    if isinstance(duration, (int, float)) and math.isfinite(duration) and duration >= 0:
                        step_chart_rows.append({"Etapa": f"{row.get('Paso', index)}. {row.get('Etapa', 'Etapa sin nombre')}", "Minutos": duration})
                if step_chart_rows:
                    with st.container(border=True):
                        section_intro("Tiempo por etapa", "Lee de arriba hacia abajo para seguir el orden de producción.")
                        step_frame = pd.DataFrame(step_chart_rows)
                        step_chart = px.bar(step_frame, x="Minutos", y="Etapa", orientation="h", text="Minutos", color_discrete_sequence=["#13866B"])
                        step_chart.update_layout(yaxis=dict(autorange="reversed", title=""), height=max(300, len(step_chart_rows) * 48), margin=dict(t=15, b=20), showlegend=False)
                        st.plotly_chart(step_chart, width="stretch")
                        if len(step_chart_rows) != len(steps):
                            st.caption("La gráfica incluye sólo etapas con duración válida. Revisa la tabla para ver el resto.")
                else:
                    empty_state("Faltan tiempos para graficar", "Puedes consultar las etapas y sus responsables en el detalle del proceso.")
                with st.expander("Ver pasos, tiempos y responsables"):
                    table(steps)
                with st.expander("Ver diagrama técnico del proceso"):
                    st.caption("Las flechas indican el recorrido; los rombos marcan decisiones y revisiones de calidad.")
                    dot = graphviz.Digraph(comment="Proceso de producción simulado")
                    dot.attr(bgcolor="#F8FAFC", rankdir="TB")
                    dot.attr("node", fontname="sans-serif", fontcolor="#FFFFFF", style="filled,rounded")
                    dot.attr("edge", color="#475569", fontcolor="#475569", fontname="sans-serif", fontsize="11")
                    shape_colors = {"oval": "#2563EB", "box": "#334155", "diamond": "#9A3412", "parallelogram": "#047857"}
                    for nodo in flujo_data.get("nodos", []):
                        dot.node(nodo["id"], nodo["label"], shape=nodo["shape"], fillcolor=shape_colors.get(nodo["shape"], "#334155"), color="#64748B")
                    for arista in flujo_data.get("aristas", []):
                        dot.edge(arista["origen"], arista["destino"], label=arista["label"])
                    st.graphviz_chart(dot, width="stretch")
                with st.expander("Equipo y almacenamiento de esta línea"):
                    st.metric("Velocidad de colocación", flujo_data["velocidad_smt"])
                    st.caption("SMT es el montaje de componentes sobre una placa. CPH cuenta componentes por hora; no es la producción final de kits.")
                    st.write(f"**Horno de soldadura:** {flujo_data['horno_reflujo']}")
                    st.write(f"**Almacenamiento y proceso:** {flujo_data['almacenamiento_proceso']}")
            else:
                empty_state("No se pudo cargar el proceso", "Selecciona otra línea o vuelve a abrir este módulo.")
        with operacion_tab:
            section_intro("¿Cuánto cuesta mantener la operación?", "Gastos y consumos del presupuesto académico. No se actualizan al registrar empleados ni sustituyen los costos configurados para la sede.")
            monthly_rows = datos_presupuestos.get("tabla_nomina_opex", [])
            consumption = api("GET", "/ingenieria/consumo-electrico", default=[])
            a, b = st.columns(2)
            a.metric("Presupuesto mensual de operación", money(sum(row.get("Costo Total Mensual (MXN)", 0) for row in monthly_rows)))
            b.metric("Energía estimada · línea Objetivo", f"{sum(row.get('kwh_p2', 0) for row in consumption):,.1f} kWh/mes" if consumption else "No disponible")
            if monthly_rows:
                cost_frame = pd.DataFrame(monthly_rows).groupby("Categoría", as_index=False)["Costo Total Mensual (MXN)"].sum()
                with st.container(border=True):
                    section_intro("Distribución del gasto mensual", "Compara el presupuesto de sueldos con los otros gastos de operación.")
                    cost_chart = px.bar(cost_frame, x="Categoría", y="Costo Total Mensual (MXN)", color="Categoría", color_discrete_sequence=["#2563EB", "#13866B"])
                    cost_chart.update_layout(showlegend=False, height=290, yaxis_tickprefix="$", margin=dict(t=15, b=20))
                    st.plotly_chart(cost_chart, width="stretch")
                with st.expander("Ver puestos, cantidades y gastos mensuales"):
                    table(monthly_rows)
                    st.caption("OPEX significa gastos de operación. Los sueldos de esta tabla son referencias del ejercicio, independientes del personal registrado.")
            else:
                empty_state("No se cargó el detalle de gastos", "Vuelve a abrir el módulo para consultar el presupuesto mensual.")
            if consumption:
                with st.container(border=True):
                    section_intro("Energía estimada por línea", "La comparación usa los equipos y tiempos de cada presupuesto; no hay sensores conectados.")
                    energy_frame = pd.DataFrame([{"Línea": label, "Energía (kWh/mes)": sum(row.get(key, 0) for row in consumption)} for label, key in [("Económica", "kwh_p1"), ("Objetivo", "kwh_p2"), ("Premium", "kwh_p3")]])
                    energy_chart = px.bar(energy_frame, x="Línea", y="Energía (kWh/mes)", color="Línea", color_discrete_sequence=["#64748B", "#13866B", "#2563EB"])
                    energy_chart.update_layout(showlegend=False, height=290, margin=dict(t=15, b=20))
                    st.plotly_chart(energy_chart, width="stretch")
                    st.caption("kW mide potencia; kWh mide energía consumida durante un periodo.")
                with st.expander("Ver consumo por equipo"):
                    table([{"Equipo": row["equipo"], "Económica (kWh/mes)": row["kwh_p1"], "Objetivo (kWh/mes)": row["kwh_p2"], "Premium (kWh/mes)": row["kwh_p3"]} for row in consumption])
                with st.expander("Ver potencia y horas utilizadas en la línea Objetivo"):
                    table([{"Equipo": row["equipo"], "Potencia (kW)": row["potencia_kw"], "Horas por día": row["horas_dia"], "Energía (kWh/mes)": row["consumo_mensual_kwh"]} for row in consumption])
                    st.caption("La estimación de esta línea usa 24 días de operación por mes: potencia × horas diarias × 24.")
            else:
                empty_state("No se cargaron los consumos estimados", "Vuelve a abrir el módulo para consultar la comparación de energía.")
