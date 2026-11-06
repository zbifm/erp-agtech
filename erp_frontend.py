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


def table(rows):
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.caption("Todavía no hay registros.")


def finish(message):
    st.session_state.flash = message
    st.rerun()


if not st.session_state.autenticado:
    st.title("🌱 ERP AgTech")
    st.subheader("Ventas, inventario e inversión en un mismo sistema")
    st.info("Demostración académica. Se simulan GPS, lector de códigos, impresora y facturación fiscal; las ventas e inventarios sí se registran en el sistema.")
    left, right = st.columns([1, 1])
    with left:
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
        st.markdown("**Accesos de demostración**")
        st.table(pd.DataFrame([
            {"Usuario": "gerente", "Contraseña": "123", "Área": "Administración · acceso completo"},
            {"Usuario": "cajero", "Contraseña": "123", "Área": "Ventas · caja y comprobantes"},
            {"Usuario": "ingeniero", "Contraseña": "123", "Área": "Ingeniería · inventario y análisis"},
        ]))
        st.caption("Estos accesos son exclusivamente de la demostración; utiliza datos ficticios. El gerente puede registrar usuarios individuales.")
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
        sucursal_activa_id = st.selectbox("Sede activa", list(negocios_db), format_func=lambda k: negocios_db[k]["nombre"])
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
    pagina = st.radio("Módulos", menu)
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

st.title(pagina)
if st.session_state.get("flash"):
    st.success(st.session_state.pop("flash"))

if pagina == "Inicio":
    st.markdown("Control operativo y evaluación financiera de un negocio de tecnología agrícola.")
    if datos_sucursal:
        a, b, c = st.columns(3)
        a.metric("Inversión inicial", money(datos_sucursal["inversion_inicial"]))
        b.metric("Costos fijos mensuales", money(datos_sucursal["costos_fijos_mensuales"]))
        c.metric("Productos en catálogo", len(catalogo_comp))
        st.markdown(f"**Sede:** {datos_sucursal['nombre']} · **Sector:** {datos_sucursal.get('sector', 'Agroindustrial')} · **Giro:** {datos_sucursal.get('giro', 'Tecnología agrícola')}")
        st.caption(datos_sucursal.get("actividades", "Producción y comercialización de kits y sensores"))
    st.markdown("**Ruta para la demostración:** registra una sede → revisa inventario → realiza una venta → descarga su ticket → consulta las finanzas.")
    st.info("GPS: coordenadas simuladas. Códigos: captura manual equivalente a un lector USB. Impresora: comprobante descargable para imprimir desde el navegador. Factura: documento académico sin timbrado ni validez fiscal. Sensores y maquinaria: presupuestos y modelos de simulación.")
    if sucursal_activa_id and ("reportes" in permisos_usuario or "inventario" in permisos_usuario):
        recommendations = api("GET", f"/analisis/recomendaciones/{sucursal_activa_id}", default={})
        st.subheader("Sugerencias de adquisición por ubicación")
        st.caption(recommendations.get("fuente", "Reglas de demostración con geolocalización simulada; no son datos de mercado en vivo."))
        table(recommendations.get("recomendaciones", []))

if pagina == "Sedes y ubicación":
    st.caption("La ubicación seleccionada alimenta la geocerca y las sugerencias de productos. No se obtiene GPS real del dispositivo.")
    with st.expander("Buscar dirección o seleccionar en mapa"):
        location_text = st.text_input("Dirección o lugar", placeholder="Texcoco, Estado de México")
        if st.button("Buscar dirección") and location_text.strip():
            try:
                location = Nominatim(user_agent="erp-agtech-academico", timeout=10).geocode(location_text)
                if location:
                    st.session_state.nueva_sede_lat = float(location.latitude)
                    st.session_state.nueva_sede_lon = float(location.longitude)
                    st.success(location.address)
                else:
                    st.warning("No se encontró la dirección. Puedes capturar coordenadas manualmente.")
            except Exception:
                st.warning("El geocodificador no está disponible. Usa las coordenadas manuales.")
        if st.checkbox("Mostrar mapa (requiere conexión)"):
            m = folium.Map(location=[st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon], zoom_start=12)
            folium.Marker([st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon]).add_to(m)
            clicked = st_folium(m, height=300, use_container_width=True, key="mapa_sede")
            if clicked and clicked.get("last_clicked"):
                pair = (clicked["last_clicked"]["lat"], clicked["last_clicked"]["lng"])
                if pair != (st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon):
                    st.session_state.nueva_sede_lat, st.session_state.nueva_sede_lon = pair
                    st.rerun()
    budgets = {p["id_presupuesto"]: p for p in datos_presupuestos.get("detalle_presupuestos", [])}
    pres = st.selectbox("Presupuesto base", list(budgets) or ["P2_OBJETIVO"], format_func=lambda k: budgets.get(k, {}).get("nombre_nivel", k))
    budget = budgets.get(pres, {})
    with st.form("nueva_sede"):
        a, b = st.columns(2)
        nombre = a.text_input("Nombre de la sede", "AgTech Planta Texcoco")
        ciudad = b.text_input("Ciudad / zona", "Texcoco, Estado de México")
        c1, c2, c3 = st.columns(3)
        sector = c1.selectbox("Sector", ["Agroindustrial", "Comercial", "Servicios", "Industrial"])
        giro = c2.text_input("Giro comercial", "Tecnología agrícola")
        actividades = c3.text_input("Actividades", "Ensamble y venta de sensores y kits agrícolas")
        a, b, c = st.columns(3)
        lat = a.number_input("Latitud", -90.0, 90.0, float(st.session_state.nueva_sede_lat), format="%.5f")
        lon = b.number_input("Longitud", -180.0, 180.0, float(st.session_state.nueva_sede_lon), format="%.5f")
        radius = c.number_input("Radio de geocerca (km)", 0.01, 1000.0, 5.0)
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
                fijar_posicion_cajero(lat, lon)
                finish("Sede registrada correctamente.")
    st.subheader("Sedes registradas")
    table(list(negocios_db.values()))

if pagina == "Punto de venta":
    if not datos_sucursal:
        st.info("El gerente debe registrar una sede antes de operar caja.")
    else:
        st.caption(f"Sede: {datos_sucursal['nombre']}. Los precios y el stock se verifican en el servidor al cobrar; el IVA se agrega al precio de catálogo.")
        st.session_state.operador_lat, st.session_state.operador_lon = st.session_state.posicion_cajero
        if st.session_state.get("mapa_cajero_sede") != sucursal_activa_id:
            st.session_state.mapa_cajero_sede = sucursal_activa_id
            reiniciar_mapa_cajero()
        with st.expander("Ubicación del cajero · GPS simulado", expanded=True):
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
            (st.success if allowed else st.error)(geo.get("mensaje", "No se pudo validar la ubicación."))
        mode = st.radio("Tipo de venta", ["Kit estándar de la sede", "Refacción / código de barras", "Combo personalizado"], horizontal=True)
        ids, quote = [], None
        sale_type = "Estándar"
        if mode == "Refacción / código de barras":
            sale_type = "Componentes"
            barcode = st.text_input("Simular lector: escribe o pega el código de barras y presiona Enter")
            found = next((key for key, item in catalogo_comp.items() if barcode and barcode in (key, item.get("codigo_barras"))), None)
            if barcode and not found:
                st.warning("Código no encontrado. También puedes seleccionar el producto.")
            keys = list(catalogo_comp)
            if keys:
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
            st.info(f"Kit según presupuesto {datos_sucursal['presupuesto_seleccionado']}. Precio sin IVA: {money(datos_sucursal['precio_venta_unitario'])}. Se descuentan sus componentes del inventario.")
        a, b = st.columns(2)
        quantity = a.number_input("Cantidad", min_value=1, max_value=10000, value=1, step=1)
        payment = b.selectbox("Método de pago", ["efectivo", "transferencia", "tarjeta"])
        if mode == "Combo personalizado" and ids:
            quote = api("POST", "/tpv/cotizar-combo", json={"placa_id": placa, "almacenamiento_id": almacenamiento, "sensores_ids": sens, "incluir_chasis_fuente": include, "cantidad_combos": quantity})
            if quote:
                table(quote.get("tabla_desglose_combo", []))
                a, b, c = st.columns(3)
                a.metric("Subtotal sin IVA", money(quote.get("precio_total_cliente")))
                b.metric("Costo del lote", money(quote.get("costo_total_lote")))
                c.metric("Descuento", f"{quote.get('descuento_combo_pct', 0)} %")
        if st.button("Cobrar y registrar venta", type="primary", disabled=not allowed or (mode != "Kit estándar de la sede" and not ids)):
            sale_payload = {"negocio_id": sucursal_activa_id, "latitud_operador": lat_operador,
                "longitud_operador": lon_operador, "tipo_venta": sale_type, "componentes_ids": ids, "cantidad": quantity, "metodo_pago": payment}
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
                finish("Venta registrada. El inventario y el IVA se actualizaron; consulta el comprobante abajo.")
        st.divider()
        history = api("GET", f"/ventas/historial/{sucursal_activa_id}", default={})
        sales = history.get("historial_detallado", [])
        st.subheader("Historial y comprobantes")
        if sales:
            a, b, c = st.columns(3)
            a.metric("Unidades registradas (acumulado)", sum(v["cantidad"] for v in sales))
            b.metric("Total cobrado con IVA", money(sum(v.get("total", v.get("ingreso_bruto", 0)) for v in sales)))
            c.metric("Utilidad bruta sin IVA", money(sum(v.get("utilidad_bruta", 0) for v in sales)))
            table(sales)
            folio = st.selectbox("Venta para ticket / factura", [v["folio"] for v in reversed(sales)])
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
    st.caption("Existencias centrales compartidas. Las salidas por venta se registran automáticamente; las compras y ajustes requieren un motivo.")
    table(datos_inventario.get("tabla_inventario", []))
    low = [{"Producto": p["nombre"], "Stock": p["stock"], "Punto de reorden": p.get("punto_reorden", 0)} for p in catalogo_comp.values() if p["stock"] <= p.get("punto_reorden", 0)]
    if low:
        st.warning(f"{len(low)} producto(s) alcanzaron su punto de reorden.")
        table(low)
    if catalogo_comp:
        pid = st.selectbox("Producto a administrar", list(catalogo_comp), format_func=lambda k: catalogo_comp[k]["nombre"])
        product = catalogo_comp[pid]
        a, b, c = st.columns(3)
        a.metric("Stock actual", product["stock"])
        b.metric("Precio sin IVA", money(product["precio_publico"]))
        margin = (product["precio_publico"] - product["costo_unitario"]) / product["precio_publico"] * 100 if product["precio_publico"] else None
        c.metric("Margen bruto", number(margin, " %"))
        if product.get("foto_url"):
            st.image(product["foto_url"], caption=product["nombre"], width=240)
        from barcode import Code128
        from barcode.writer import SVGWriter
        barcode_image = io.BytesIO()
        Code128(product.get("codigo_barras", pid), writer=SVGWriter()).write(barcode_image, options={"module_width": 0.25, "module_height": 12.0, "quiet_zone": 3.0, "font_size": 9, "text_distance": 3.0})
        barcode_svg = barcode_image.getvalue()
        st.image(barcode_svg.decode("utf-8"), caption="Etiqueta Code 128 generada para este producto", width=360)
        st.download_button("Descargar etiqueta de código de barras", barcode_svg, f"codigo_{pid}.svg", "image/svg+xml")
        with st.form("producto_detalle"):
            a, b, c = st.columns(3)
            cost = a.number_input("Costo unitario en MXN", min_value=0.0, value=float(product["costo_unitario"]), disabled=product.get("moneda_origen") == "USD")
            price = b.number_input("Precio sin IVA en MXN", min_value=0.01, value=float(product["precio_publico"]))
            reorder = c.number_input("Punto de reorden", min_value=0, value=int(product.get("punto_reorden", 20)))
            barcode = st.text_input("Código de barras / identificador", product.get("codigo_barras", pid))
            photo = st.text_input("URL de foto (https) o imagen ya guardada", value=product.get("foto_url", ""))
            if product.get("moneda_origen") == "USD":
                st.caption("El costo MXN es calculado: modifica el costo de compra en la sección Origen y costo de importación.")
            upload = st.file_uploader("Cargar foto propia del producto (PNG/JPG, máximo 1 MB)", type=["png", "jpg", "jpeg"])
            if st.form_submit_button("Guardar producto", type="primary"):
                if upload and upload.size > 1024 * 1024:
                    st.error("La imagen supera 1 MB. Reduce su tamaño.")
                else:
                    if upload:
                        photo = f"data:{upload.type};base64," + base64.b64encode(upload.getvalue()).decode("ascii")
                    result = api("PUT", f"/inventario/componentes/{pid}", json={"costo_unitario": cost, "precio_publico": price, "punto_reorden": reorder, "codigo_barras": barcode, "foto_url": photo})
                    if result:
                        finish("Producto actualizado.")
        with st.form("importacion_producto"):
            st.subheader("Origen y costo de importación")
            a, b, c = st.columns(3)
            currency = a.selectbox("Moneda de compra", ["MXN", "USD"], index=1 if product.get("moneda_origen") == "USD" else 0)
            origin_cost = b.number_input("Costo en moneda de compra", min_value=0.0, value=float(product.get("costo_origen", product["costo_unitario"])))
            import_cost = c.number_input("Flete y otros gastos por unidad (MXN)", min_value=0.0, value=float(product.get("gastos_importacion_unitarios", 0)))
            st.caption("En USD, el costo se recalcula con el tipo de cambio simulado guardado por el gerente. Las ventas anteriores mantienen su costo histórico.")
            if st.form_submit_button("Aplicar origen y recalcular costo"):
                result = api("PUT", f"/inventario/componentes/{pid}", json={"moneda_origen": currency, "costo_origen": origin_cost, "gastos_importacion_unitarios": import_cost})
                if result:
                    finish("Origen actualizado y costo del producto recalculado.")
        with st.form("movimiento_stock"):
            st.subheader("Entrada o ajuste de inventario")
            amount = st.number_input("Cantidad: positiva para entrada, negativa para salida", min_value=-100000, max_value=100000, value=1, step=1)
            reason = st.text_input("Motivo", placeholder="Compra a proveedor / devolución / merma")
            if st.form_submit_button("Registrar movimiento"):
                result = api("POST", "/inventario/movimiento", json={"componente_id": pid, "cantidad": amount, "motivo": reason})
                if result:
                    finish("Movimiento de inventario registrado.")
    st.subheader("Bitácora de movimientos")
    moves = api("GET", "/inventario/movimientos", default={})
    table(moves.get("movimientos", []) if isinstance(moves, dict) else moves)

if pagina == "Finanzas y tendencias":
    if not datos_sucursal:
        st.info("Registra o selecciona una sede para analizar sus finanzas.")
    else:
        st.subheader("Escenario de inversión")
        st.caption("Proyección hipotética a tres años; importes sin IVA. Las tasas anuales son supuestos editables, no cotizaciones actuales de CETES.")
        a, b, c = st.columns(3)
        units = a.number_input("Unidades proyectadas por mes", min_value=0, max_value=1000000, value=85, step=1)
        discount = b.number_input("Tasa de descuento anual (%)", min_value=0.0, max_value=100.0, value=15.0)
        benchmark = c.number_input("Tasa de referencia anual supuesta (%)", min_value=0.0, max_value=100.0, value=11.0)
        with st.expander("Modificar supuestos del escenario (no cambia la sede)"):
            a, b, c, d = st.columns(4)
            investment = a.number_input("Inversión inicial", min_value=0.0, value=float(datos_sucursal["inversion_inicial"]))
            fixed = b.number_input("Costos fijos mensuales", min_value=0.0, value=float(datos_sucursal["costos_fijos_mensuales"]))
            cost = c.number_input("Costo variable por unidad", min_value=0.0, value=float(datos_sucursal["costo_variable_unitario"]))
            price = d.number_input("Precio por unidad sin IVA", min_value=0.01, value=float(datos_sucursal["precio_venta_unitario"]))
        simulated = api("POST", "/analisis/simulador", json={"unidades_vendidas_mes": units, "inversion_inicial": investment,
            "costos_fijos_mensuales": fixed, "costo_variable_unitario": cost, "precio_venta_unitario": price,
            "tasa_descuento": discount, "tasa_cetes": benchmark})
        if simulated:
            indicators = simulated["indicadores_duros"]
            a, b, c, d = st.columns(4)
            a.metric("Punto de equilibrio mensual", number(indicators.get("punto_equilibrio_uds"), " uds"))
            b.metric("Flujo operativo mensual", money(indicators.get("flujo_caja_mensual")))
            c.metric("VAN / VPN a 3 años", money(indicators.get("vpn")))
            d.metric("TIR anual", number(indicators.get("tir"), " %"))
            a, b = st.columns(2)
            a.metric("Diferencia frente a referencia", number(indicators.get("spread_cetes"), " puntos porcentuales"))
            b.metric("Margen de contribución unitario", money(price - cost))
            a, b = st.columns(2)
            a.metric("ROI anual simple", number(indicators.get("roi_anual_pct"), " %"))
            b.metric("Recuperación simple", number(indicators.get("recuperacion_meses"), " meses"))
            st.caption(indicators.get("estado", ""))
            for warning in simulated.get("advertencias", []):
                st.warning(warning)
            st.caption(simulated.get("supuestos", {}).get("modelo", ""))
            if indicators.get("tir") is None:
                st.info("La TIR no está definida para este flujo. No se sustituye por 0 %.")
            bars = simulated.get("datos_graficas", {}).get("barras", {})
            if bars:
                frame = pd.DataFrame({"Concepto": bars["categorias"], "MXN por mes": bars["valores"]})
                st.plotly_chart(px.bar(frame, x="Concepto", y="MXN por mes", color="Concepto", title="Ingresos y costos del escenario"), width="stretch")
            if st.button("Generar dictamen financiero del escenario"):
                result = api("POST", "/analisis/dictamen", json={"nombre_negocio": datos_sucursal["nombre"], "unidades_vendidas": units,
                    "punto_equilibrio_uds": indicators.get("punto_equilibrio_uds"), "vpn": indicators.get("vpn"), "tir": indicators.get("tir"),
                    "spread": indicators.get("spread_cetes"), "estado_inversion": indicators.get("estado", "")})
                if result:
                    st.session_state.dictamen = result.get("dictamen_ia", result.get("dictamen", ""))
                    st.session_state.dictamen_escenario = (sucursal_activa_id, units, discount, benchmark, investment, fixed, cost, price)
            if st.session_state.get("dictamen") and st.session_state.get("dictamen_escenario") == (sucursal_activa_id, units, discount, benchmark, investment, fixed, cost, price):
                st.markdown(st.session_state.dictamen)
                st.caption("Dictamen por reglas financieras locales; no requiere una API de IA externa.")
        st.divider()
        st.subheader("Resultados de las ventas registradas")
        report = api("GET", f"/analisis/reportes/{sucursal_activa_id}", default={})
        metrics = report.get("indicadores", {})
        if metrics:
            a, b, c, d = st.columns(4)
            a.metric("Ventas netas sin IVA", money(metrics.get("ventas_netas")))
            b.metric("IVA cobrado", money(metrics.get("iva_cobrado")))
            c.metric("Utilidad bruta", money(metrics.get("utilidad_bruta")))
            d.metric("Margen bruto", number(metrics.get("margen_bruto_pct"), " %"))
            a, b, c = st.columns(3)
            a.metric("Costo de ventas", money(metrics.get("costo_ventas")))
            b.metric("Inventario central a costo", money(metrics.get("valor_inventario_costo")))
            c.metric("Productos en reorden", metrics.get("productos_reorden", 0))
            st.caption("Los acumulados corresponden a las ventas registradas de esta sede. La utilidad bruta todavía no descuenta costos fijos, impuestos sobre la renta ni financiamiento.")
            by_cashier = metrics.get("ventas_por_cajero", {})
            if by_cashier:
                st.markdown("**Ventas por cajero**")
                table([{"Cajero": k, **(v if isinstance(v, dict) else {"Ventas": v})} for k, v in by_cashier.items()] if isinstance(by_cashier, dict) else by_cashier)
        series = report.get("series_mensuales", [])
        if series:
            frame = pd.DataFrame(series)
            st.plotly_chart(px.line(frame, x="mes", y=["ventas_netas", "costo_ventas", "utilidad_bruta"], markers=True, title="Ventas registradas por mes"), width="stretch")
            table(series)
        else:
            st.info("Registra ventas para construir la serie mensual.")
        st.subheader("Tendencia de mercado · simulación")
        st.caption(report.get("fuente_tendencias", "Serie sintética de demostración. No representa un estudio de mercado ni una predicción."))
        trends = report.get("tendencias_simuladas", [])
        if trends:
            st.plotly_chart(px.line(pd.DataFrame(trends), x="mes", y="indice_demanda", markers=True, title="Índice de demanda simulado"), width="stretch")
        for limitation in report.get("limitaciones", []):
            st.caption(limitation)

if pagina == "Personal y usuarios":
    st.caption("Las cuentas controlan acceso al sistema; el personal registra puestos, áreas, turnos y salarios del ejercicio académico.")
    if "personal" in permisos_usuario:
        staff_data = api("GET", "/personal", default={})
        staff = staff_data.get("personal", [])
        st.subheader("Control de personal")
        st.metric("Nómina mensual registrada", money(staff_data.get("nomina_mensual", 0)))
        st.caption(staff_data.get("nota", ""))
        table(staff)
        with st.form("nuevo_empleado"):
            a, b, c = st.columns(3)
            name = a.text_input("Nombre del empleado")
            position = b.text_input("Puesto", "Operador")
            area = c.selectbox("Área del empleado", ["Administración", "Ventas", "Inventario", "Producción", "Ingeniería", "Finanzas"])
            a, b = st.columns(2)
            salary = a.number_input("Salario mensual (MXN)", min_value=0.0, value=10000.0)
            shift = b.selectbox("Turno", ["Matutino", "Vespertino", "Nocturno", "Mixto"])
            if st.form_submit_button("Registrar empleado", type="primary"):
                result = api("POST", "/personal", json={"nombre": name, "puesto": position, "area": area, "salario_mensual": salary, "turno": shift})
                if result:
                    finish("Empleado registrado.")
        if staff:
            with st.expander("Actualizar empleado"):
                people = {str(p["id"]): p for p in staff}
                person_id = st.selectbox("Empleado", list(people), format_func=lambda k: people[k]["nombre"])
                person = people[person_id]
                with st.form("editar_empleado"):
                    a, b = st.columns(2)
                    name = a.text_input("Nombre", person["nombre"])
                    position = b.text_input("Puesto actual", person["puesto"])
                    area = a.text_input("Área actual", person["area"])
                    shift = b.text_input("Turno actual", person["turno"])
                    salary = a.number_input("Salario actualizado (MXN)", min_value=0.0, value=float(person["salario_mensual"]))
                    active = b.checkbox("Empleado activo", bool(person.get("activo", True)))
                    if st.form_submit_button("Actualizar empleado"):
                        result = api("PUT", f"/personal/{person_id}", json={"nombre": name, "puesto": position, "area": area, "turno": shift, "salario_mensual": salary, "activo": active})
                        if result:
                            finish("Empleado actualizado.")
    if "usuarios" in permisos_usuario:
        st.divider()
        st.subheader("Usuarios y niveles de control")
        users_data = api("GET", "/usuarios", default={})
        users = users_data.get("usuarios", [])
        roles_data = users_data.get("roles", {})
        roles = list(roles_data) or ["gerente", "cajero", "ingeniero"]
        areas = users_data.get("areas", []) or ["Administración", "Ventas", "Ingeniería"]
        table(users)
        with st.form("nuevo_usuario"):
            a, b = st.columns(2)
            username = a.text_input("Nuevo usuario")
            fullname = b.text_input("Nombre de la persona")
            password = a.text_input("Contraseña nueva (mínimo 8 caracteres)", type="password")
            role = b.selectbox("Rol de acceso", roles)
            area = b.selectbox("Área de la cuenta", areas)
            if st.form_submit_button("Crear usuario", type="primary"):
                result = api("POST", "/usuarios", json={"username": username, "nombre": fullname, "password": password, "rol": role, "area": area})
                if result:
                    finish("Usuario creado. Ya puede iniciar sesión con sus credenciales.")
        if users:
            with st.expander("Modificar acceso de una cuenta"):
                usernames = {u["username"]: u for u in users}
                selected = st.selectbox("Cuenta", list(usernames))
                user = usernames[selected]
                with st.form("editar_usuario"):
                    active = st.checkbox("Cuenta activa", bool(user.get("activo", True)))
                    role = st.selectbox("Nuevo rol", roles, index=roles.index(user.get("rol_codigo")) if user.get("rol_codigo") in roles else 0)
                    area = st.text_input("Área asignada", user.get("area", "Administración"))
                    if st.form_submit_button("Guardar acceso"):
                        result = api("PUT", f"/usuarios/{selected}", json={"activo": active, "rol": role, "area": area})
                        if result:
                            finish("Acceso actualizado.")

if pagina == "Configuración":
    config = api("GET", "/configuracion", default={})
    st.info("Parámetros manuales para el ejercicio. El tipo de cambio no se consulta en tiempo real y la tasa de IVA debe corresponder al supuesto académico elegido.")
    with st.form("configuracion"):
        a, b = st.columns(2)
        rate = a.number_input("Tipo de cambio simulado: MXN por USD", min_value=0.01, max_value=1000.0, value=float(config.get("tipo_cambio_usd_mxn", 20.0)))
        tax = b.number_input("IVA (%)", min_value=0.0, max_value=100.0, value=float(config.get("iva_tasa", 0.16)) * 100)
        if st.form_submit_button("Guardar parámetros", type="primary"):
            result = api("PUT", "/configuracion", json={"tipo_cambio_usd_mxn": rate, "iva_tasa": tax / 100})
            if result:
                finish("Parámetros guardados. Los comprobantes anteriores mantienen sus importes originales.")
    st.subheader("Respaldo operativo")
    st.caption("Descarga una copia antes de reconstruir o reiniciar un alojamiento con disco efímero. Contiene datos operativos y de personal, sin contraseñas ni sesiones.")
    if st.button("Preparar respaldo JSON"):
        backup = api("GET", "/respaldo")
        if backup:
            st.session_state.respaldo_data = json.dumps(backup, ensure_ascii=False, indent=2)
    if st.session_state.get("respaldo_data"):
        st.download_button("Descargar respaldo", st.session_state.respaldo_data, "respaldo_agtech.json", "application/json")
    st.subheader("Costo de importación simulado")
    a, b, c = st.columns(3)
    foreign = a.number_input("Precio de compra (USD)", min_value=0.0, value=50.0)
    freight = b.number_input("Flete por unidad (MXN)", min_value=0.0, value=100.0)
    extra = c.number_input("Otros costos por unidad (MXN)", min_value=0.0, value=0.0)
    st.metric("Costo unitario estimado sin IVA", money(foreign * rate + freight + extra))
    st.caption("Fórmula: compra en USD × MXN por USD + flete + otros costos. Para usarlo en ventas, registra el costo resultante en el producto; no se modifica el catálogo automáticamente desde esta calculadora.")


if pagina == "Ingeniería y presupuestos":
    if "ingenieria" not in permisos_usuario:
        st.error("⛔ Acceso Restringido.")
    else:
        st.header("⚙️ Análisis de Ingeniería, Presupuestos y Manufactura SMT")
        
        # 1. Tabla Comparativa de Disparidad y Multicriterio
        st.subheader("1. Tabla Comparativa: Disparidad de Precios, Almacenamiento y CAPEX")
        if datos_presupuestos.get("resumen_disparidad"):
            st.dataframe(pd.DataFrame(datos_presupuestos["resumen_disparidad"]), width="stretch", hide_index=True)
            
        st.divider()
        
        # 2. Desglose detallado por Presupuesto (Tabs)
        st.subheader("2. Desglose Tabular por Presupuesto (Maquinaria SMT, Almacenamiento e Inventario Inicial)")
        if datos_presupuestos.get("detalle_presupuestos"):
            tabs_p = st.tabs([p["nombre_corto"] for p in datos_presupuestos["detalle_presupuestos"]])
            for idx, p_obj in enumerate(datos_presupuestos["detalle_presupuestos"]):
                with tabs_p[idx]:
                    m1, m2, m3, m4 = st.columns(4)
                    m1.metric("CAPEX Total", f"${p_obj['capex_total_mxn']:,.2f}")
                    m2.metric("Almacén + Planta", f"${(p_obj['inversion_almacenamiento_planta_mxn'] + p_obj['inversion_produccion_instalacion_mxn']):,.2f}")
                    m3.metric("Costo Unitario Kit", f"${p_obj['costo_produccion_kit_mxn']:,.2f}")
                    m4.metric("Precio Público", f"${p_obj['precio_publico_kit_mxn']:,.2f}", f"Margen: {p_obj['margen_unitario_pct']}%")
                    
                    st.markdown("##### 🛠️ Maquinaria e Infraestructura")
                    st.dataframe(pd.DataFrame(p_obj["tabla_maquinaria_y_produccion"]), width="stretch", hide_index=True)
                    st.markdown("##### 📦 Inventario Inicial del Kit de Arranque")
                    st.dataframe(pd.DataFrame(p_obj["tabla_inventario_kit"]), width="stretch", hide_index=True)

        st.divider()
        
        # 3. BOM Comparativo de Materia Prima y Nómina OPEX
        c_bom1, c_bom2 = st.columns(2)
        with c_bom1:
            st.subheader("3. Tabla de Materia Prima por Kit (BOM)")
            if datos_presupuestos.get("tabla_bom_kits"):
                st.dataframe(pd.DataFrame(datos_presupuestos["tabla_bom_kits"]), width="stretch", hide_index=True)
        with c_bom2:
            st.subheader("4. Nómina y OPEX Mensual ($580,000 MXN)")
            if datos_presupuestos.get("tabla_nomina_opex"):
                st.dataframe(pd.DataFrame(datos_presupuestos["tabla_nomina_opex"]), width="stretch", hide_index=True)

        st.divider()
        
        # 5. DIAGRAMA DE FLUJO DINÁMICO SELECCIONABLE POR LÍNEA DE PRESUPUESTO
        st.subheader("5. Diagrama de Flujo de Producción Dinámico por Línea SMT")
        
        # Selector de presupuesto para actualizar el diagrama en tiempo real
        linea_sel_flujo = st.selectbox(
            "Selecciona la línea de presupuesto para visualizar su diagrama de proceso y tiempos:",
            options=["P1_ECONOMICO", "P2_OBJETIVO", "P3_PREMIUM"],
            format_func=lambda x: "🟢 Línea 1: Económica (ESP32)" if x=="P1_ECONOMICO" else ("🔵 Línea 2: Objetivo (Radxa)" if x=="P2_OBJETIVO" else "🟣 Línea 3: Premium (Raspberry Pi 5)")
        )
        
        try:
            res_flujo = request("GET", f"/ingenieria/flujo-produccion?presupuesto_id={linea_sel_flujo}")
            if res_flujo is not None:
                flujo_data = res_flujo.json()
                
                f_c1, f_c2, f_c3 = st.columns(3)
                f_c1.metric("⏱️ Tiempo Ciclo Total", f"{flujo_data['tiempo_total_optimo_min']} minutos")
                f_c2.metric("⚡ Velocidad SMT", flujo_data['velocidad_smt'])
                f_c3.metric("🔥 Sistema de Reflujo", flujo_data['horno_reflujo'])
                
                st.caption(f"💾 **Almacenamiento y Proceso:** {flujo_data['almacenamiento_proceso']}")
                
                # Renderizar Graphviz
                dot = graphviz.Digraph(comment='Flujo Dinámico')
                dot.attr(bgcolor='transparent', rankdir='TB') 
                dot.attr('node', fontname='sans-serif', fontcolor='white', style='filled, rounded')
                dot.attr('edge', color='#888888', fontcolor='white', fontname='sans-serif', fontsize='10')

                colores_tema = {"oval": "#2196F3", "box": "#262730", "diamond": "#F44336", "parallelogram": "#4CAF50"}
                for nodo in flujo_data.get('nodos', []):
                    dot.node(nodo['id'], nodo['label'], shape=nodo['shape'], fillcolor=colores_tema.get(nodo['shape'], '#262730'), color='#555555') 
                for arista in flujo_data.get('aristas', []):
                    dot.edge(arista['origen'], arista['destino'], label=arista['label'])
                
                st.graphviz_chart(dot, width="stretch")
                
                st.markdown("##### 📋 Tabla de Pasos y Responsables")
                st.dataframe(pd.DataFrame(flujo_data["tabla_pasos"]), width="stretch", hide_index=True)
        except Exception as e:
            st.error(f"Error cargando diagrama dinámico: {e}")

        st.divider()
        
        # 6. Consumo eléctrico
        st.subheader("6. Potencia y consumo eléctrico de planta (kW / kWh)")
        try:
            res_kw = request("GET", "/ingenieria/consumo-electrico")
            if res_kw is not None:
                consumo = res_kw.json()
                st.dataframe(pd.DataFrame(consumo), width="stretch", hide_index=True)
        except Exception:
            st.error("No se pudo mostrar el consumo eléctrico.")
