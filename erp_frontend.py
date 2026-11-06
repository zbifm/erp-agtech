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
[data-testid="stMetric"] {border:1px solid #879a8e44;border-radius:14px;padding:1rem;}
[data-testid="stMetricValue"] {font-size:clamp(1.35rem,2.1vw,2rem);}
[data-testid="stMetricValue"] > div {white-space:normal;overflow:visible;text-overflow:clip;overflow-wrap:anywhere;}
[data-testid="stSidebar"] h1 {font-size:1.65rem;}
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


def hero(title, description):
    st.markdown(f'<div class="agtech-hero"><div class="agtech-eyebrow">AGTECH · DEMOSTRACIÓN ACADÉMICA</div><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p></div>', unsafe_allow_html=True)


def ir_a_modulo(module):
    st.session_state.modulo_activo = module


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
negocios_db = api("GET", "/negocios", default={})
datos_inventario = api("GET", "/inventario/componentes", default={})
catalogo_comp = datos_inventario.get("catalogo_diccionario", {})
datos_presupuestos = api("GET", "/ingenieria/presupuestos-tabulares", default={}) if ("ingenieria" in permisos_usuario or "registrar_sede" in permisos_usuario) else {}

with st.sidebar:
    st.title("🌱 AgTech")
    st.caption(f"{st.session_state.username} · {st.session_state.rol}")
    if st.button("Cerrar sesión", width="stretch"):
        request("POST", "/auth/logout", quiet=True)
        client = st.session_state.api_client
        st.session_state.clear()
        st.session_state.api_client = client
        st.rerun()
    st.divider()
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
    menu = ["Inicio"]
    if "tpv" in permisos_usuario:
        menu.append("Punto de venta")
    if "inventario" in permisos_usuario:
        menu.append("Inventario y productos")
    if "registrar_sede" in permisos_usuario:
        menu.append("Sedes y ubicación")
    if "simulador" in permisos_usuario:
        menu.append("Finanzas y tendencias")
    if "ingenieria" in permisos_usuario:
        menu.append("Ingeniería y presupuestos")
    if "personal" in permisos_usuario or "usuarios" in permisos_usuario:
        menu.append("Personal y usuarios")
    if "usuarios" in permisos_usuario:
        menu.append("Configuración")
    if st.session_state.get("modulo_activo") not in menu:
        st.session_state.modulo_activo = "Inicio"
    pagina = st.radio("Módulos", menu, key="modulo_activo")
    st.divider()
    st.caption("MODO ACADÉMICO · Operaciones con datos de demostración. Inventario central compartido entre sedes.")
    if "exportar" in permisos_usuario:
        if st.button("Preparar reporte Excel", width="stretch"):
            result = request("GET", "/exportar/excel")
            if result is not None:
                st.session_state.excel_data = result.content
        if st.session_state.get("excel_data"):
            st.download_button("Descargar Excel", st.session_state.excel_data, "Reporte_ERP_AgTech.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", width="stretch")
            st.caption("Vuelve a preparar el reporte después de registrar cambios.")

descriptions = {
    "Inicio": "Tu operación de un vistazo. Elige una tarea para empezar.",
    "Punto de venta": "Verifica tu ubicación, elige productos y revisa el total antes de cobrar.",
    "Inventario y productos": "Consulta existencias, identifica faltantes y administra tus productos.",
    "Sedes y ubicación": "Define dónde opera cada sede y el radio permitido para registrar ventas.",
    "Finanzas y tendencias": "Consulta resultados registrados o prueba escenarios de inversión.",
    "Ingeniería y presupuestos": "Compara alternativas de equipamiento y conoce cómo se produce cada kit.",
    "Personal y usuarios": "Organiza tu equipo y decide quién puede entrar a cada módulo.",
    "Configuración": "Ajusta los valores de demostración y descarga una copia de tus datos.",
}
hero(pagina, descriptions[pagina])
if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))

if pagina == "Inicio":
    low_products = [p for p in catalogo_comp.values() if p["stock"] <= p.get("punto_reorden", 0)]
    if datos_sucursal:
        a, b, c = st.columns(3)
        a.metric("Productos en catálogo", len(catalogo_comp))
        b.metric("Productos por reabastecer", len(low_products))
        c.metric("Radio permitido para vender", f"{datos_sucursal['radio_operacion_km']:g} km")
        st.markdown(f"**Sede activa:** {datos_sucursal['nombre']} · **Giro:** {datos_sucursal.get('giro', 'Tecnología agrícola')}")
        st.caption(datos_sucursal.get("actividades", "Producción y comercialización de kits y sensores"))
    st.subheader("¿Qué quieres hacer?")
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
                st.button(f"Abrir {module.lower()}", key=f"atajo_{module}", on_click=ir_a_modulo, args=(module,), width="stretch")
    if low_products:
        accion_reorden = "Revisa sus existencias en Inventario y productos." if "inventario" in permisos_usuario else "Avisa al gerente para reabastecerlos."
        st.warning(f"{len(low_products)} productos llegaron al punto de reorden. {accion_reorden}")
    with st.expander("Guía rápida para la demostración", expanded=False):
        st.markdown("1. Usa la sede de ejemplo o registra otra en **Sedes y ubicación**.\n2. Revisa productos y existencias en **Inventario y productos**.\n3. En **Punto de venta**, alterna dentro/fuera del radio para demostrar el bloqueo.\n4. Vuelve dentro, revisa el total y registra una venta.\n5. Descarga el ticket y consulta **Finanzas y tendencias**.")
        st.caption("Las opciones disponibles dependen de tu perfil. El gerente puede explorar todos los módulos.")
    with st.expander("Qué se guarda y qué se simula"):
        st.markdown("**Se guarda:** ventas, inventario, sedes, personal y cuentas de usuario.\n\n**Se simula:** ubicación GPS, lector de códigos, pagos, facturación fiscal y escenarios financieros. Los comprobantes se descargan para imprimir desde el navegador.")
    if sucursal_activa_id and ("reportes" in permisos_usuario or "inventario" in permisos_usuario):
        recommendations = api("GET", f"/analisis/recomendaciones/{sucursal_activa_id}", default={})
        st.subheader("Productos sugeridos para tu zona")
        st.caption(recommendations.get("fuente", "Reglas de demostración con geolocalización simulada; no son datos de mercado en vivo."))
        recommendations_rows = recommendations.get("recomendaciones", [])
        table([{k: v for k, v in row.items() if k != "producto_id"} for row in recommendations_rows])
        st.caption("Una compra sugerida de 0 indica que hay existencias suficientes; el producto se muestra por su relación con la zona.")

if pagina == "Sedes y ubicación":
    st.subheader("Registrar una nueva sede")
    st.caption("Puedes usar la sede de ejemplo que ya está registrada. Para crear otra, elige su ubicación y completa los datos de abajo.")
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
        st.markdown("**1. Datos del negocio**")
        a, b = st.columns(2)
        nombre = a.text_input("Nombre de la sede", "AgTech Planta Texcoco")
        ciudad = b.text_input("Ciudad / zona", "Texcoco, Estado de México")
        c1, c2, c3 = st.columns(3)
        sector = c1.selectbox("Sector", ["Agroindustrial", "Comercial", "Servicios", "Industrial"])
        giro = c2.text_input("Giro comercial", "Tecnología agrícola")
        actividades = c3.text_input("Actividades", "Ensamble y venta de sensores y kits agrícolas")
        st.markdown("**2. Ubicación y zona permitida**")
        st.caption("La geocerca es el círculo alrededor de la sede dentro del cual se permite vender. Aquí defines su tamaño; el GPS se simula.")
        a, b, c = st.columns(3)
        lat = a.number_input("Latitud", -90.0, 90.0, float(st.session_state.nueva_sede_lat), format="%.5f", key=f"lat_sede_{st.session_state.get('mapa_sede_revision', 0)}")
        lon = b.number_input("Longitud", -180.0, 180.0, float(st.session_state.nueva_sede_lon), format="%.5f", key=f"lon_sede_{st.session_state.get('mapa_sede_revision', 0)}")
        radius = c.number_input("Radio de geocerca (km)", 0.01, 1000.0, 5.0)
        st.markdown("**3. Inversión, costos y precio del kit**")
        st.caption("Los costos son supuestos para el simulador. El precio del kit sí se usa en caja; el IVA se agrega al cobrar.")
        a, b, c, d = st.columns(4)
        capex = a.number_input("Inversión inicial (MXN)", min_value=0.0, value=float(budget.get("capex_total_mxn", 1775000)), key=f"capex_{pres}")
        fixed = b.number_input("Costos fijos / mes (MXN)", min_value=0.0, value=580000.0)
        variable = c.number_input("Costo variable / kit (MXN)", min_value=0.0, value=float(budget.get("costo_produccion_kit_mxn", 2750)), key=f"variable_{pres}")
        price = d.number_input("Precio / kit sin IVA (MXN)", min_value=0.01, value=float(budget.get("precio_publico_kit_mxn", 10500)), key=f"price_{pres}")
        if st.form_submit_button("Registrar sede", type="primary"):
            result = api("POST", "/negocios", json={"nombre": nombre, "ciudad_referencia": ciudad, "sector": sector, "giro": giro, "actividades": actividades,
                "latitud": lat, "longitud": lon, "radio_operacion_km": radius, "presupuesto_seleccionado": pres,
                "inversion_inicial": capex, "costos_fijos_mensuales": fixed, "costo_variable_unitario": variable, "precio_venta_unitario": price})
            if result:
                st.session_state.seleccionar_sede_nueva = result["id_negocio"]
                fijar_posicion_cajero(lat, lon)
                finish("Sede registrada y seleccionada. El cajero se ubicó en su centro para la demostración.")
    st.subheader("Sedes registradas")
    table([{"Sede": row["nombre"], "Ciudad / zona": row.get("ciudad_referencia", ""), "Giro": row.get("giro", ""),
            "Radio permitido (km)": row["radio_operacion_km"], "Kit": nombre_presupuesto(row["presupuesto_seleccionado"]),
            "Precio del kit sin IVA (MXN)": row["precio_venta_unitario"]} for row in negocios_db.values()])

if pagina == "Punto de venta":
    if not datos_sucursal:
        st.info("El gerente debe registrar una sede antes de operar caja.")
    else:
        venta_tab, historial_tab = st.tabs(["Nueva venta", "Historial y comprobantes"])
        with venta_tab:
            st.caption(f"Sede activa: {datos_sucursal['nombre']} · Cajero: {st.session_state.username}")
            st.markdown("**1 · Verifica tu ubicación**")
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
            if allowed:
                st.success(f"Dentro del radio permitido · A {geo.get('distancia_km', 0):.2f} km de la sede. Puedes registrar ventas.")
            elif geo:
                st.error(f"Venta bloqueada · Estás a {geo.get('distancia_km', 0):.2f} km de la sede y el máximo es {datos_sucursal['radio_operacion_km']:g} km. Vuelve dentro del radio para cobrar.")
            else:
                st.error("No se pudo comprobar tu ubicación. El cobro permanece bloqueado; vuelve a intentarlo.")
            destino_lat, destino_lon = float(datos_sucursal["latitud"]), float(datos_sucursal["longitud"])
            if allowed:
                radio_demo = float(datos_sucursal["radio_operacion_km"])
                # Alejar hacia el ecuador: válido también en polos y radios de hasta 1000 km.
                salto_lat = math.degrees(max(2 * radio_demo, radio_demo + 1) / 6371.0)
                destino_lat += -salto_lat if destino_lat > 0 else salto_lat
            st.button(
                "Simular fuera del radio" if allowed else "Simular dentro del radio",
                key="alternar_radio_cajero", on_click=fijar_posicion_cajero,
                args=(destino_lat, destino_lon),
                help="Cambia la ubicación simulada del cajero para demostrar el bloqueo. No registra ventas ni modifica el radio de la sede.",
            )
            st.divider()
            st.markdown("**2 · Elige productos y cantidad**")
            mode = st.radio("Tipo de venta", ["Kit estándar de la sede", "Refacción / código de barras", "Combo personalizado"], horizontal=True)
            ids, quote = [], None
            sale_type = "Estándar"
            if mode == "Refacción / código de barras":
                sale_type = "Componentes"
                barcode = st.text_input("Simular lector: escribe o pega el código de barras y presiona Enter", placeholder="Ejemplo: AGT00000001").strip()
                found = next((key for key, item in catalogo_comp.items() if barcode and barcode in (key, item.get("codigo_barras"))), None)
                if barcode and not found:
                    st.warning("Código no encontrado. Corrígelo o borra el campo para elegir un producto de la lista. El cobro queda bloqueado.")
                keys = list(catalogo_comp)
                if keys and (not barcode or found):
                    product_id = st.selectbox("Producto", keys, index=keys.index(found) if found else 0, format_func=lambda k: f"{catalogo_comp[k]['nombre']} · {money(catalogo_comp[k]['precio_publico'])} · stock {catalogo_comp[k]['stock']}", key=f"producto_{found or 'manual'}")
                    ids = [product_id]
                    if catalogo_comp[product_id].get("foto_url"):
                        st.image(catalogo_comp[product_id]["foto_url"], width=180)
            elif mode == "Combo personalizado":
                sale_type = "Combo"
                plates = [k for k, d in catalogo_comp.items() if d["categoria"] == "Placa Base"]
                storage = [k for k, d in catalogo_comp.items() if d["categoria"] == "Almacenamiento"]
                sensors = [k for k, d in catalogo_comp.items() if d["categoria"] == "Sensor"]
                if plates and storage:
                    a, b = st.columns(2)
                    placa = a.selectbox("Placa base", plates, format_func=lambda k: catalogo_comp[k]["nombre"])
                    almacenamiento = b.selectbox("Almacenamiento", storage, format_func=lambda k: catalogo_comp[k]["nombre"])
                    sens = st.multiselect("Sensores", sensors, default=sensors, format_func=lambda k: catalogo_comp[k]["nombre"])
                    include = st.checkbox(f"Incluir chasis y fuente ({money(catalogo_comp.get('FUENTE_CHASIS', {}).get('precio_publico', 0))})", value=True)
                    ids = [placa, almacenamiento] + sens + (["FUENTE_CHASIS"] if include else [])
                    st.caption("Cuatro o más componentes distintos reciben 8 % de descuento antes del IVA.")
            else:
                st.info(f"{nombre_presupuesto(datos_sucursal['presupuesto_seleccionado'])}. Precio por kit sin IVA: {money(datos_sucursal['precio_venta_unitario'])}.")
            a, b = st.columns(2)
            quantity = a.number_input("Cantidad", min_value=1, max_value=10000, value=1, step=1)
            payment = b.selectbox("Método de pago", ["efectivo", "transferencia", "tarjeta"])
            sale_payload = {"negocio_id": sucursal_activa_id, "latitud_operador": lat_operador,
                "longitud_operador": lon_operador, "tipo_venta": sale_type, "componentes_ids": ids, "cantidad": quantity, "metodo_pago": payment}
            if mode == "Kit estándar de la sede" or ids:
                quote = api("POST", "/tpv/cotizar-venta", json=sale_payload)
            st.markdown("**3 · Revisa el total y registra la venta**")
            if quote:
                with st.container(border=True):
                    a, b, c = st.columns(3)
                    a.metric("Subtotal sin IVA", money(quote["subtotal"]))
                    b.metric(f"IVA ({quote['iva_tasa'] * 100:g} %)", money(quote["iva"]))
                    c.metric("Total a cobrar", money(quote["total"]))
                    st.caption(f"Cantidad: {quantity} · Disponibilidad: {quote['unidades_disponibles']} {('kits' if mode == 'Kit estándar de la sede' else 'combos' if mode == 'Combo personalizado' else 'unidades')} · Pago: {payment}")
                    if quote.get("descuento_pct"):
                        st.success(f"Descuento de combo incluido: {quote['descuento_pct']:g} % antes de IVA.")
                    with st.expander("Ver productos incluidos"):
                        table([{"Producto": row["nombre"], "Unidades a descontar": row["cantidad"]} for row in quote["detalle"]])
                if not quote["stock_suficiente"]:
                    st.warning("No hay existencias suficientes para esta cantidad. Reduce la cantidad o registra una entrada en inventario.")
                    table([{"Producto": row["nombre"], "Unidades necesarias": row["requerido"], "Disponibles": row["disponible"]} for row in quote["faltantes"]])
            else:
                st.info("Selecciona productos válidos para consultar el total antes de cobrar.")
            st.caption("El pago se registra como demostración: no se carga una tarjeta ni se hace una transferencia bancaria. Al confirmar se descuenta el inventario.")
            if st.button("Cobrar y registrar venta", type="primary", disabled=not allowed or not quote or not quote.get("stock_suficiente", False)):
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
                table([{"Folio": v["folio"], "Fecha (UTC)": v["fecha"].replace("T", " ")[:19], "Cajero": v["vendedor"],
                        "Tipo": v["tipo_venta"], "Cantidad": v["cantidad"], "Subtotal (MXN)": v["subtotal"],
                        "IVA (MXN)": v["iva"], "Total (MXN)": v["total"], "Pago": v["metodo_pago"]} for v in reversed(sales)])
                st.caption("Cantidad = kits, combos o refacciones según el tipo de venta. Utilidad bruta = subtotal menos costo de productos; todavía no resta gastos fijos.")
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
                            st.code(content, language=None)
                            printable = '<!doctype html><html lang="es"><meta charset="utf-8"><title>Comprobante AgTech</title><style>body{font:16px monospace;padding:32px}pre{white-space:pre-wrap}@media print{button{display:none}}</style><button onclick="window.print()">Imprimir / guardar PDF</button><pre>' + html.escape(content) + '</pre></html>'
                            st.download_button(f"Descargar {label.lower()} para imprimir", printable, f"{kind}_{folio}.html", "text/html", key=f"download_{kind}")
                            if kind == "factura":
                                st.warning("Documento académico simulado: sin timbrado SAT ni validez fiscal.")
                st.caption("Abre el archivo descargado y usa Imprimir / guardar PDF. No requiere impresora física.")
            else:
                st.info("Aún no hay ventas en esta sede.")

if pagina == "Inventario y productos":
    st.caption("Inventario central compartido por todas las sedes. Cada venta descuenta sus componentes automáticamente.")
    low = [p for p in catalogo_comp.values() if p["stock"] <= p.get("punto_reorden", 0)]
    a, b, c = st.columns(3)
    a.metric("Productos en catálogo", len(catalogo_comp))
    b.metric("Productos por reabastecer", len(low), help="Su existencia llegó al punto de reorden: el nivel mínimo elegido para volver a comprar.")
    c.metric("Valor del inventario al costo", money(sum(p["stock"] * p["costo_unitario"] for p in catalogo_comp.values())))
    catalog_tab, edit_tab, stock_tab = st.tabs(["Catálogo y alertas", "Editar producto", "Entradas y salidas"])
    with catalog_tab:
        a, b = st.columns([3, 1])
        search_product = a.text_input("Buscar producto", placeholder="Nombre, categoría o código de barras")
        only_low = b.checkbox("Solo por reabastecer")
        if low:
            st.warning(f"Hay {len(low)} producto(s) por reabastecer. Filtra la lista para revisarlos.")
        catalog_rows = []
        for product_id, item in catalogo_comp.items():
            needs_stock = item["stock"] <= item.get("punto_reorden", 0)
            searchable = " ".join(str(item.get(k, "")) for k in ("nombre", "categoria", "codigo_barras")) + " " + product_id
            if search_product.strip().casefold() not in searchable.casefold() or (only_low and not needs_stock):
                continue
            catalog_rows.append({"Producto": item["nombre"], "Categoría": item["categoria"], "Existencias": item["stock"],
                "Estado": "Reabastecer" if needs_stock else "Disponible", "Punto de reorden": item.get("punto_reorden", 0),
                "Costo unitario (MXN)": item["costo_unitario"], "Precio sin IVA (MXN)": item["precio_publico"],
                "Código de barras": item.get("codigo_barras", product_id)})
        if catalog_rows:
            table(catalog_rows)
        else:
            st.info("No hay productos que coincidan con estos filtros.")
        st.caption("Para cambiar precios o registrar una compra, abre las pestañas Editar producto o Entradas y salidas.")
    if catalogo_comp:
        with edit_tab:
            pid = st.selectbox("Producto a administrar", list(catalogo_comp), format_func=lambda k: catalogo_comp[k]["nombre"])
            product = catalogo_comp[pid]
            a, b, c = st.columns(3)
            a.metric("Stock actual", product["stock"])
            b.metric("Precio sin IVA", money(product["precio_publico"]))
            margin = (product["precio_publico"] - product["costo_unitario"]) / product["precio_publico"] * 100 if product["precio_publico"] else None
            c.metric("Margen bruto", number(margin, " %"), help="Parte del precio que queda después del costo del producto. Aún no descuenta gastos fijos.")
            if margin is not None and margin < 0:
                st.warning("El precio está por debajo del costo: cada unidad vendida genera una pérdida bruta.")
            with st.expander("Foto y etiqueta para imprimir"):
                a, b = st.columns(2)
                with a:
                    if product.get("foto_url"):
                        st.image(product["foto_url"], caption=product["nombre"], width=220)
                    else:
                        st.info("Este producto todavía no tiene foto. Puedes añadirla en el formulario de abajo.")
                with b:
                    from barcode import Code128
                    from barcode.writer import SVGWriter
                    barcode_image = io.BytesIO()
                    Code128(product.get("codigo_barras", pid), writer=SVGWriter()).write(barcode_image, options={"module_width": 0.25, "module_height": 12.0, "quiet_zone": 3.0, "font_size": 9, "text_distance": 3.0})
                    barcode_svg = barcode_image.getvalue()
                    st.image(barcode_svg.decode("utf-8"), caption="Etiqueta Code 128", width=320)
                    st.download_button("Descargar etiqueta de código de barras", barcode_svg, f"codigo_{pid}.svg", "image/svg+xml")
            with st.form("producto_detalle"):
                st.markdown("**Precio y nivel de reabastecimiento**")
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
                        result = api("PUT", f"/inventario/componentes/{pid}", json={"costo_unitario": cost, "precio_publico": price, "punto_reorden": reorder, "codigo_barras": barcode, "foto_url": photo})
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
        with stock_tab:
            stock_pid = st.selectbox("Producto para entrada o salida", list(catalogo_comp), format_func=lambda k: f"{catalogo_comp[k]['nombre']} · {catalogo_comp[k]['stock']} disponibles")
            st.caption("Las ventas ya descuentan inventario. Usa este formulario para compras, devoluciones o mermas, sin duplicar una salida por venta.")
            with st.form("movimiento_stock"):
                amount = st.number_input("Cantidad: positiva para entrada, negativa para salida", min_value=-100000, max_value=100000, value=1, step=1, help="Ejemplo: 10 agrega diez unidades; -2 retira dos. No se permite dejar existencias negativas.")
                reason = st.text_input("Motivo", placeholder="Compra a proveedor / devolución / merma")
                if st.form_submit_button("Registrar movimiento"):
                    if amount == 0 or not reason.strip():
                        st.error("Indica una cantidad distinta de cero y escribe el motivo del movimiento.")
                    else:
                        result = api("POST", "/inventario/movimiento", json={"componente_id": stock_pid, "cantidad": amount, "motivo": reason.strip()})
                        if result:
                            finish("Movimiento de inventario registrado.")
    with stock_tab:
        st.subheader("Historial de movimientos")
        moves = api("GET", "/inventario/movimientos", default={})
        move_rows = moves.get("movimientos", []) if isinstance(moves, dict) else moves
        table(list(reversed(move_rows)))

if pagina == "Finanzas y tendencias":
    if not datos_sucursal:
        st.info("Registra o selecciona una sede para analizar sus finanzas.")
    else:
        st.caption(f"Consulta las ventas de {datos_sucursal['nombre']} o prueba un escenario sin modificar sus datos.")
        ventas_tab, escenario_tab, tendencia_tab = st.tabs(["Ventas registradas", "Simular inversión", "Tendencia de ejemplo"])
        report = api("GET", f"/analisis/reportes/{sucursal_activa_id}", default={})
        with ventas_tab:
            st.subheader("Resultados de esta sede")
            st.caption("Acumulado de todas las ventas registradas. Importes en pesos mexicanos (MXN).")
            metrics = report.get("indicadores", {})
            if metrics:
                a, b, c = st.columns(3)
                a.metric("Ventas sin IVA", money(metrics.get("ventas_netas")), help="Suma de las ventas antes de agregar IVA.")
                b.metric("Utilidad bruta", money(metrics.get("utilidad_bruta")), help="Ventas sin IVA menos el costo histórico de los productos vendidos.")
                c.metric("Margen bruto", number(metrics.get("margen_bruto_pct"), " %"), help="Porcentaje de las ventas sin IVA que queda después del costo de los productos.")
                st.caption("La utilidad bruta todavía no descuenta costos fijos, impuestos sobre la renta ni financiamiento.")
                with st.expander("Desglose de cobros e inventario"):
                    a, b, c = st.columns(3)
                    a.metric("IVA cobrado", money(metrics.get("iva_cobrado")))
                    b.metric("Total cobrado con IVA", money(metrics.get("total_cobrado")))
                    c.metric("Costo de lo vendido", money(metrics.get("costo_ventas")))
                    a, b = st.columns(2)
                    a.metric("Inventario central a costo", money(metrics.get("valor_inventario_costo")))
                    b.metric("Productos por reponer", metrics.get("productos_reorden", 0))
                    st.caption("El inventario y las alertas de reposición son compartidos por todas las sedes. Su valor usa los costos actuales; las ventas conservan el costo de la fecha en que se cobraron.")
            series = report.get("series_mensuales", [])
            if series:
                frame = pd.DataFrame(series).rename(columns={"mes": "Mes", "ventas_netas": "Ventas sin IVA", "costo_ventas": "Costo de ventas", "utilidad_bruta": "Utilidad bruta", "unidades": "Unidades"})
                fig = px.line(frame, x="Mes", y=["Ventas sin IVA", "Costo de ventas", "Utilidad bruta"], markers=True,
                    labels={"value": "Importe (MXN)", "variable": "Concepto"}, title="Ventas y resultados por mes",
                    color_discrete_map={"Ventas sin IVA": "#2563EB", "Costo de ventas": "#F59E0B", "Utilidad bruta": "#10B981"})
                fig.update_layout(legend_title_text="", yaxis_tickprefix="$", hovermode="x unified")
                st.plotly_chart(fig, width="stretch")
                with st.expander("Ver cifras mensuales y ventas por cajero"):
                    table(frame.to_dict("records"))
                    st.markdown("**Ventas por cajero · sin IVA**")
                    by_cashier = metrics.get("ventas_por_cajero", {})
                    table([{"Cajero": k, **(v if isinstance(v, dict) else {"Ventas sin IVA (MXN)": v})} for k, v in by_cashier.items()] if isinstance(by_cashier, dict) else by_cashier)
            else:
                next_sale = "Registra una en Punto de venta" if "tpv" in permisos_usuario else "Pide al cajero o al gerente que registre una venta"
                st.info(f"Todavía no hay ventas en esta sede. {next_sale} para ver aquí sus resultados y su gráfica.")
        with escenario_tab:
            st.subheader("¿Cuántas unidades necesitas vender?")
            st.caption("Proyección hipotética a 3 años, con ventas iguales cada mes e importes sin IVA. Los cambios aquí no modifican la sede, el catálogo ni las ventas.")
            a, b, c = st.columns(3)
            units = a.number_input("Unidades proyectadas por mes", min_value=0, max_value=1000000, value=85, step=1, help="Cantidad de kits que supones vender cada mes, no ventas ya registradas.")
            discount = b.number_input("Tasa de descuento anual (%)", min_value=0.0, max_value=100.0, value=15.0, help="Rendimiento mínimo supuesto para comparar el dinero futuro con el dinero de hoy.")
            benchmark = c.number_input("Tasa de referencia anual supuesta (%)", min_value=0.0, max_value=100.0, value=11.0, help="Rendimiento de comparación elegido para el ejercicio. No es una cotización de CETES en tiempo real.")
            with st.expander("Modificar supuestos del escenario (no cambia la sede)"):
                st.caption("Valores iniciales tomados de la sede, en MXN. No se actualizan automáticamente al cambiar productos, tipo de cambio o personal; revisa estos supuestos para cada proyección.")
                a, b = st.columns(2)
                investment = a.number_input("Inversión inicial", min_value=0.0, value=float(datos_sucursal["inversion_inicial"]), help="Desembolso inicial total del proyecto.")
                fixed = b.number_input("Costos fijos mensuales", min_value=0.0, value=float(datos_sucursal["costos_fijos_mensuales"]), help="Gastos que se pagan cada mes aunque no haya ventas, como renta o nómina.")
                cost = a.number_input("Costo variable por unidad", min_value=0.0, value=float(datos_sucursal["costo_variable_unitario"]), help="Costo supuesto de producir un kit; aumenta con las unidades vendidas.")
                price = b.number_input("Precio por unidad sin IVA", min_value=0.01, value=float(datos_sucursal["precio_venta_unitario"]), help="Precio de un kit antes de agregar IVA.")
            simulated = api("POST", "/analisis/simulador", json={"unidades_vendidas_mes": units, "inversion_inicial": investment,
                "costos_fijos_mensuales": fixed, "costo_variable_unitario": cost, "precio_venta_unitario": price,
                "tasa_descuento": discount, "tasa_cetes": benchmark})
            if simulated:
                indicators = simulated["indicadores_duros"]
                contribution = price - cost
                monthly_flow = indicators.get("flujo_caja_mensual", 0)
                a, b, c = st.columns(3)
                a.metric("Mínimo para cubrir gastos", f"{math.ceil(fixed / contribution):,} kits/mes" if contribution > 0 else "No alcanzable", help="Unidades completas necesarias para cubrir costos fijos y variables con este precio.")
                b.metric("Resultado operativo mensual", money(monthly_flow), help="Ingresos menos costos variables y costos fijos. No incluye IVA, ISR ni financiamiento.")
                c.metric("Aporte de cada kit", money(contribution), help="Precio sin IVA menos costo variable. Este importe ayuda a cubrir los costos fijos.")
                if monthly_flow > 0:
                    st.success(f"Con {units:,} kits al mes, el escenario deja {money(monthly_flow)} después de los costos fijos y variables.")
                elif monthly_flow < 0:
                    st.warning(f"Con {units:,} kits al mes, faltan {money(abs(monthly_flow))} para cubrir los gastos mensuales.")
                else:
                    st.info("Con este escenario, los ingresos y los costos mensuales quedan iguales.")
                bars_frame = pd.DataFrame({"Concepto": ["Ingresos", "Costos variables", "Costos fijos"], "MXN por mes": [units * price, units * cost, fixed]})
                bars = px.bar(bars_frame, x="Concepto", y="MXN por mes", color="Concepto", title="Ingresos y costos del escenario",
                    color_discrete_map={"Ingresos": "#10B981", "Costos variables": "#F59E0B", "Costos fijos": "#64748B"})
                bars.update_layout(showlegend=False, yaxis_tickprefix="$")
                st.plotly_chart(bars, width="stretch")
                with st.expander("Rentabilidad de la inversión: VAN, TIR y recuperación", expanded=True):
                    a, b, c = st.columns(3)
                    a.metric("VAN / VPN a 3 años", money(indicators.get("vpn")), help="Valor de los flujos futuros a dinero de hoy, menos la inversión inicial, usando tu tasa de descuento.")
                    b.metric("TIR anual", number(indicators.get("tir"), " %"), help="Tasa que hace que el VAN sea cero para los flujos del escenario. No siempre puede calcularse.")
                    c.metric("Recuperación simple", number(indicators.get("recuperacion_meses"), " meses"), help="Inversión inicial dividida entre el resultado mensual positivo; no ajusta por el valor del dinero en el tiempo.")
                    a, b = st.columns(2)
                    a.metric("ROI anual simple", number(indicators.get("roi_anual_pct"), " %"), help="Resultado operativo anual dividido entre inversión inicial, expresado como porcentaje.")
                    b.metric("TIR menos tasa de referencia", number(indicators.get("spread_cetes"), " puntos"), help="Diferencia en puntos porcentuales frente a la tasa anual que elegiste.")
                    if indicators.get("tir") is None:
                        st.info("La TIR no está definida para estos flujos. Esto ocurre, por ejemplo, sin inversión inicial o sin resultados operativos positivos.")
                    for warning in simulated.get("advertencias", []):
                        if "TIR" not in warning:
                            st.warning(warning)
                    st.caption("Modelo simplificado: tres flujos anuales iguales. No incluye financiamiento, depreciación, ISR ni valor residual. Los resultados dependen de los supuestos capturados.")
                if st.button("Generar dictamen financiero del escenario"):
                    result = api("POST", "/analisis/dictamen", json={"nombre_negocio": datos_sucursal["nombre"], "unidades_vendidas": units,
                        "punto_equilibrio_uds": indicators.get("punto_equilibrio_uds"), "vpn": indicators.get("vpn"), "tir": indicators.get("tir"),
                        "spread": indicators.get("spread_cetes"), "estado_inversion": indicators.get("estado", "")})
                    if result:
                        st.session_state.dictamen = result.get("dictamen_ia", result.get("dictamen", ""))
                        st.session_state.dictamen_escenario = (sucursal_activa_id, units, discount, benchmark, investment, fixed, cost, price)
                if st.session_state.get("dictamen") and st.session_state.get("dictamen_escenario") == (sucursal_activa_id, units, discount, benchmark, investment, fixed, cost, price):
                    with st.container(border=True):
                        st.markdown(st.session_state.dictamen)
                        st.caption("Interpretación automática basada en los números de este escenario.")
        with tendencia_tab:
            st.subheader("Estacionalidad de ejemplo")
            st.info("Esta gráfica contiene datos inventados para demostrar una tendencia. No representa las ventas registradas, un estudio de mercado ni una predicción.")
            trends = report.get("tendencias_simuladas", [])
            if trends:
                trend_frame = pd.DataFrame(trends).rename(columns={"mes": "Mes", "indice_demanda": "Índice de demanda"})
                fig = px.line(trend_frame, x="Mes", y="Índice de demanda", markers=True, title="Demanda simulada a lo largo del año", color_discrete_sequence=["#2563EB"])
                fig.add_hline(y=100, line_dash="dot", annotation_text="Referencia: 100")
                st.plotly_chart(fig, width="stretch")
                st.caption("El índice es una escala comparativa: valores mayores a 100 representan más demanda en este ejemplo; no son pesos ni unidades vendidas.")

if pagina == "Personal y usuarios":
    st.caption("Personal lleva el registro de empleados y sueldos. Cuentas de acceso define quién puede entrar y qué módulos puede usar.")
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
            st.caption("La nómina suma sueldos de empleados activos. No se añade automáticamente al costo fijo de la sede, para evitar contar el mismo gasto dos veces.")
            if staff:
                table([{"Nombre": p["nombre"], "Puesto": p["puesto"], "Área": p["area"], "Turno": p["turno"],
                        "Salario mensual (MXN)": p["salario_mensual"], "Estado": "Activo" if p.get("activo", True) else "Inactivo"} for p in staff])
            else:
                st.info("Todavía no hay empleados registrados. Abre Agregar empleado para crear el primero.")
            with st.expander("Agregar empleado", expanded=not staff):
                st.caption("Registrar un empleado no crea una cuenta para iniciar sesión; eso se hace en Cuentas de acceso.")
                with st.form("nuevo_empleado"):
                    a, b, c = st.columns(3)
                    name = a.text_input("Nombre del empleado")
                    position = b.text_input("Puesto", "Operador")
                    area = c.selectbox("Área del empleado", staff_data.get("areas") or ["Administración", "Ventas", "Inventario", "Producción", "Ingeniería", "Finanzas"])
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
            if staff:
                with st.expander("Actualizar empleado"):
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
    if "usuarios" in permisos_usuario:
        with personnel_tabs["Cuentas de acceso"]:
            users_data = api("GET", "/usuarios", default={})
            users = users_data.get("usuarios", [])
            roles_data = users_data.get("roles", {})
            roles = list(roles_data) or ["gerente", "cajero", "ingeniero"]
            areas = users_data.get("areas", []) or ["Administración", "Ventas", "Ingeniería"]
            st.caption("Gerente: todos los módulos. Cajero: ventas y comprobantes. Ingeniero: inventario, finanzas e ingeniería.")
            table([{"Usuario": u["username"], "Nombre": u.get("nombre", ""), "Rol": u.get("rol", u.get("rol_codigo", "")),
                    "Área": u.get("area", ""), "Estado": "Activa" if u.get("activo", True) else "Inactiva"} for u in users])
            with st.expander("Crear cuenta de acceso", expanded=not users):
                with st.form("nuevo_usuario"):
                    a, b = st.columns(2)
                    username = a.text_input("Nuevo usuario", help="Nombre que se escribirá al iniciar sesión; usa letras, números, punto, guion o guion bajo.")
                    fullname = b.text_input("Nombre de la persona")
                    password = a.text_input("Contraseña nueva (mínimo 8 caracteres)", type="password")
                    role = b.selectbox("Rol de acceso", roles)
                    area = b.selectbox("Área de la cuenta", areas)
                    if st.form_submit_button("Crear usuario", type="primary"):
                        if not username.strip() or not fullname.strip() or len(password) < 8:
                            st.error("Completa el usuario, el nombre y una contraseña de al menos 8 caracteres.")
                        else:
                            result = api("POST", "/usuarios", json={"username": username.strip(), "nombre": fullname.strip(), "password": password, "rol": role, "area": area})
                            if result:
                                finish("Usuario creado. Ya puede iniciar sesión con sus credenciales.")
            if users:
                with st.expander("Modificar acceso de una cuenta"):
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

if pagina == "Configuración":
    config = api("GET", "/configuracion", default={})
    saved_rate = float(config.get("tipo_cambio_usd_mxn", 20.0))
    saved_tax = float(config.get("iva_tasa", 0.16)) * 100
    st.caption("Ajustes compartidos por todas las sedes. El tipo de cambio y el IVA son supuestos de la demostración.")
    a, b = st.columns(2)
    a.metric("Tipo de cambio guardado", f"${saved_rate:,.2f} MXN / USD")
    b.metric("IVA guardado", f"{saved_tax:g} %")
    parameters_tab, calculator_tab, backup_tab = st.tabs(["Parámetros", "Calculadora de importación", "Respaldo de datos"])
    with parameters_tab:
        st.info("Al guardar, el tipo de cambio recalcula el costo actual de los productos en USD. El IVA se aplica a ventas nuevas; los comprobantes anteriores conservan sus importes.")
        with st.form("configuracion"):
            a, b = st.columns(2)
            rate = a.number_input("Tipo de cambio simulado: MXN por USD", min_value=0.01, max_value=1000.0, value=saved_rate, help="Ejemplo: 20 significa que un dólar equivale a 20 pesos. No se consulta una cotización en vivo.")
            tax = b.number_input("IVA (%)", min_value=0.0, max_value=100.0, value=saved_tax, help="Tasa del supuesto académico. Los precios del catálogo no incluyen este impuesto.")
            if st.form_submit_button("Guardar parámetros", type="primary"):
                result = api("PUT", "/configuracion", json={"tipo_cambio_usd_mxn": rate, "iva_tasa": tax / 100})
                if result:
                    finish("Parámetros guardados. Los comprobantes anteriores mantienen sus importes originales.")
    with calculator_tab:
        st.subheader("¿Cuánto cuesta importar una unidad?")
        st.caption(f"Usa el tipo de cambio guardado: ${saved_rate:,.2f} MXN por USD. Esta calculadora no modifica productos.")
        a, b, c = st.columns(3)
        foreign = a.number_input("Precio de compra (USD)", min_value=0.0, value=50.0)
        freight = b.number_input("Flete por unidad (MXN)", min_value=0.0, value=100.0)
        extra = c.number_input("Otros costos por unidad (MXN)", min_value=0.0, value=0.0)
        converted = foreign * saved_rate
        a, b, c = st.columns(3)
        a.metric("Compra convertida a pesos", money(converted))
        b.metric("Flete y otros gastos", money(freight + extra))
        c.metric("Costo unitario estimado sin IVA", money(converted + freight + extra))
        st.caption("Cálculo: compra en dólares × tipo de cambio + flete + otros gastos en pesos.")
        st.info("Para aplicar estos datos a un producto: ve a Inventario y productos → Editar producto → Origen y costo de importación. Selecciona USD, escribe el precio original en dólares y suma el flete y los otros gastos en pesos.")
    with backup_tab:
        st.subheader("Conserva una copia de tus registros")
        st.caption("Incluye sedes, ventas, inventario, movimientos, personal y parámetros. No incluye cuentas, contraseñas ni sesiones.")
        st.info("Descarga el respaldo y el reporte Excel al terminar tu demostración: el alojamiento puede perder los datos locales al reconstruir la aplicación.")
        if st.button("Preparar respaldo JSON"):
            backup = api("GET", "/respaldo")
            if backup:
                st.session_state.respaldo_data = json.dumps(backup, ensure_ascii=False, indent=2)
        if st.session_state.get("respaldo_data"):
            st.download_button("Descargar respaldo", st.session_state.respaldo_data, "respaldo_agtech.json", "application/json", type="primary")
            st.caption("Vuelve a preparar el archivo si registraste cambios después. Guárdalo en un lugar privado porque contiene datos de personal.")
        st.caption("Este archivo sirve como copia de los datos; la aplicación todavía no tiene una opción para restaurarlo automáticamente. Para una revisión legible, usa Preparar reporte Excel en la barra lateral.")


if pagina == "Ingeniería y presupuestos":
    if "ingenieria" not in permisos_usuario:
        st.error("No tienes acceso a este módulo con tu cuenta actual.")
    else:
        st.caption("Compara tres propuestas de planta y explora cómo se fabricarían los kits. Son presupuestos y procesos de demostración, no cotizaciones actuales ni mediciones de maquinaria.")
        comparacion_tab, detalle_tab, proceso_tab, operacion_tab = st.tabs(["Comparar presupuestos", "Detalle del presupuesto", "Proceso de producción", "Costos de operación"])
        budgets = datos_presupuestos.get("detalle_presupuestos", [])
        with comparacion_tab:
            st.subheader("Tres alternativas de inversión")
            if budgets:
                budget_cards = st.columns(len(budgets))
                for column, budget in zip(budget_cards, budgets):
                    with column.container(border=True):
                        st.markdown(f"**{budget['nombre_corto']}**")
                        st.metric("Inversión inicial (MXN)", f"${budget['capex_total_mxn']:,.0f}")
                        st.caption(budget["arquitectura_base"])
                        st.write(f"**Costo estimado por kit:** {money(budget['costo_produccion_kit_mxn'])}")
                        st.write(f"**Precio sugerido sin IVA:** {money(budget['precio_publico_kit_mxn'])}")
                        st.caption(f"Capacidad estimada: {budget['capacidad_planta']}")
                st.caption("La inversión inicial suma maquinaria, adecuaciones, almacenamiento e inventario de arranque. El inventario inicial no es un activo fijo.")
                comparison = pd.DataFrame([{"Alternativa": p["nombre_corto"], "Maquinaria": p["inversion_maquinaria_mxn"], "Almacén y planta": p["inversion_almacenamiento_planta_mxn"] + p["inversion_produccion_instalacion_mxn"], "Inventario de arranque": p["costo_inventario_inicial_mxn"]} for p in budgets])
                fig = px.bar(comparison, x="Alternativa", y=["Maquinaria", "Almacén y planta", "Inventario de arranque"], barmode="stack",
                    labels={"value": "Inversión (MXN)", "variable": "Concepto"}, title="¿En qué se invierte el dinero?", color_discrete_sequence=["#2563EB", "#10B981", "#F59E0B"])
                fig.update_layout(legend_title_text="", yaxis_tickprefix="$")
                st.plotly_chart(fig, width="stretch")
            with st.expander("Ver comparación completa y criterios de evaluación"):
                comparison_rows = [{("Inversión inicial total (MXN)" if k == "CAPEX Total (MXN)" else k): v for k, v in row.items()} for row in datos_presupuestos.get("resumen_disparidad", [])]
                table(comparison_rows)
                st.markdown("**Criterios y calificaciones del ejercicio**")
                table(datos_presupuestos.get("tabla_multicriterio", []))
                st.caption("Los puntajes son valoraciones del presupuesto académico. CPH significa componentes colocados por hora; no equivale a kits terminados por hora.")
        with detalle_tab:
            st.subheader("Explora un presupuesto")
            if budgets:
                selected_budget = st.selectbox("Presupuesto a consultar", range(len(budgets)), format_func=lambda i: budgets[i]["nombre_corto"])
                p_obj = budgets[selected_budget]
                a, b, c = st.columns(3)
                a.metric("Inversión inicial total", money(p_obj["capex_total_mxn"]))
                b.metric("Costo estimado por kit", money(p_obj["costo_produccion_kit_mxn"]))
                c.metric("Precio sugerido sin IVA", money(p_obj["precio_publico_kit_mxn"]))
                st.caption("Estos costos describen los componentes del presupuesto. Las ventas usan los componentes y costos actuales de Inventario, por lo que sus márgenes pueden ser distintos.")
                st.markdown("**Maquinaria, adecuaciones e inventario de arranque**")
                table(p_obj["tabla_maquinaria_y_produccion"])
                with st.expander("Ver componentes y cantidades del lote inicial"):
                    table(p_obj["tabla_inventario_kit"])
                    st.caption("Las cantidades del presupuesto no se agregan automáticamente al inventario disponible para venta.")
            with st.expander("Comparar materiales de los tres kits"):
                st.caption("Lista de materiales, también llamada BOM. Los importes corresponden al presupuesto de referencia.")
                table(datos_presupuestos.get("tabla_bom_kits", []))
        with proceso_tab:
            st.subheader("Del componente al kit terminado")
            st.caption("SMT es el montaje de componentes electrónicos sobre una placa. Cambia de línea para ver su proceso y los tiempos estimados.")
            linea_sel_flujo = st.selectbox("Línea de producción", options=["P1_ECONOMICO", "P2_OBJETIVO", "P3_PREMIUM"],
                format_func=lambda x: {"P1_ECONOMICO": "Económica · ESP32", "P2_OBJETIVO": "Objetivo · Radxa", "P3_PREMIUM": "Premium · Raspberry Pi 5"}[x])
            flujo_data = api("GET", f"/ingenieria/flujo-produccion?presupuesto_id={linea_sel_flujo}", default={})
            if flujo_data:
                a, b = st.columns(2)
                a.metric("Tiempo estimado del ciclo", f"{flujo_data['tiempo_total_optimo_min']} min")
                b.metric("Velocidad de colocación", flujo_data["velocidad_smt"])
                st.caption("CPH = componentes por hora. El ciclo incluye otros pasos; esta velocidad no es la producción final de kits.")
                with st.expander("Equipo y almacenamiento de esta línea"):
                    st.write(f"**Horno de soldadura:** {flujo_data['horno_reflujo']}")
                    st.write(f"**Almacenamiento y proceso:** {flujo_data['almacenamiento_proceso']}")
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
                with st.expander("Ver pasos, tiempos y responsables"):
                    table(flujo_data.get("tabla_pasos", []))
        with operacion_tab:
            st.subheader("Gastos mensuales de referencia")
            monthly_rows = datos_presupuestos.get("tabla_nomina_opex", [])
            st.metric("Presupuesto mensual de operación", money(sum(row.get("Costo Total Mensual (MXN)", 0) for row in monthly_rows)))
            st.caption("OPEX significa gastos de operación. Esta tabla es una referencia académica: no se actualiza al registrar empleados ni sustituye los costos fijos configurados para cada sede.")
            table(monthly_rows)
            st.subheader("Potencia y consumo eléctrico estimados")
            st.caption("kW mide potencia; kWh mide energía consumida durante un periodo. Son estimaciones del presupuesto, sin sensores conectados.")
            consumption = api("GET", "/ingenieria/consumo-electrico", default=[])
            table([{"Equipo": row["equipo"], "Económica (kWh/mes)": row["kwh_p1"], "Objetivo (kWh/mes)": row["kwh_p2"], "Premium (kWh/mes)": row["kwh_p3"]} for row in consumption])
            with st.expander("Ver potencia y horas utilizadas en la línea Objetivo"):
                table([{"Equipo": row["equipo"], "Potencia (kW)": row["potencia_kw"], "Horas por día": row["horas_dia"], "Energía (kWh/mes)": row["consumo_mensual_kwh"]} for row in consumption])
                st.caption("La estimación de esta línea usa 24 días de operación por mes: potencia × horas diarias × 24.")
