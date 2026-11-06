"""Datos públicos reales, con caché y respaldo fechado; no consulta la red al importar.

Frankfurter transmite la referencia del BCE USD/MXN. El Banco Mundial publica
precios mensuales de materias primas. Estos precios internacionales no son
precios locales, demanda de sensores ni un pronóstico del negocio.
"""
from __future__ import annotations

import copy
import io
import json
import math
import os
import re
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

import requests
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

FX_URL = "https://api.frankfurter.dev/v2/providers/ecb/rate/usd/mxn"
FX_SOURCE_URL = "https://frankfurter.dev/"
MARKET_SOURCE_URL = "https://www.worldbank.org/en/research/commodity-markets"
MARKET_DATA_URL = "https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx"
FX_REFRESH_SECONDS = 6 * 60 * 60
MARKET_REFRESH_SECONDS = 24 * 60 * 60
RETRY_SECONDS = 15 * 60
MAX_DOWNLOAD_BYTES = 8 * 1024 * 1024
_STORE_LOCK = threading.RLock()
_STORES: dict[str, dict] = {}
_RESOURCE_LOCKS: dict[tuple[str, str], threading.RLock] = {}

COMMODITIES = (
    ("maize", "Maíz", "Maize", "Maíz amarillo n.º 2 de EE. UU.; referencia de exportación FOB del Golfo de EE. UU."),
    ("wheat", "Trigo", "Wheat, US HRW", "Trigo duro rojo de invierno n.º 2 de EE. UU.; referencia de exportación del Golfo."),
    ("soybeans", "Soya", "Soybeans", "La referencia de soya cambia de CIF Rotterdam a FOB Golfo de EE. UU. desde enero de 2025; considera ese cambio al comparar periodos."),
)

# Respaldo real descargado del Banco Mundial y Frankfurter el 6 de noviembre de
# 2026. Solo se usa como último dato conocido, identificado como respaldo hasta
# conseguir una consulta en línea. Nunca se generan observaciones artificiales.
_SEED = {'exchange_rate': {'payload': {'rate': 18.7038,
                               'date': '2026-11-06',
                               'base': 'USD',
                               'quote': 'MXN',
                               'source': 'Banco Central Europeo, vía Frankfurter',
                               'source_url': 'https://frankfurter.dev/',
                               'data_url': 'https://api.frankfurter.dev/v2/providers/ecb/rate/usd/mxn',
                               'unit': 'MXN por USD',
                               'note': 'Referencia diaria publicada; puede conservar la fecha del último día hábil. No '
                                       'es una cotización bancaria de compra o venta.'},
                   'last_checked': None,
                   'last_success': '2026-11-06T23:46:29+00:00',
                   'next_check': None,
                   'error': 'bundled_snapshot',
                   'snapshot': True},
 'market_trends': {'payload': {'series': [{'id': 'maize',
                                           'name': 'Maíz',
                                           'source_name': 'Maize',
                                           'unit': 'USD por tonelada métrica',
                                           'note': 'Maíz amarillo n.º 2 de EE. UU.; referencia de exportación FOB del '
                                                   'Golfo de EE. UU.',
                                           'points': [{'date': '2023-11-01', 'value': 211.3},
                                                      {'date': '2023-12-01', 'value': 206.5},
                                                      {'date': '2024-01-01', 'value': 198.6},
                                                      {'date': '2024-02-01', 'value': 189.1},
                                                      {'date': '2024-03-01', 'value': 190.6},
                                                      {'date': '2024-04-01', 'value': 191.7},
                                                      {'date': '2024-05-01', 'value': 197.8},
                                                      {'date': '2024-06-01', 'value': 192.5},
                                                      {'date': '2024-07-01', 'value': 177.4},
                                                      {'date': '2024-08-01', 'value': 170.3},
                                                      {'date': '2024-09-01', 'value': 185.0},
                                                      {'date': '2024-10-01', 'value': 190.3},
                                                      {'date': '2024-11-01', 'value': 201.3},
                                                      {'date': '2024-12-01', 'value': 202.6},
                                                      {'date': '2025-01-01', 'value': 214.4},
                                                      {'date': '2025-02-01', 'value': 220.9},
                                                      {'date': '2025-03-01', 'value': 207.4},
                                                      {'date': '2025-04-01', 'value': 215.0},
                                                      {'date': '2025-05-01', 'value': 203.9},
                                                      {'date': '2025-06-01', 'value': 196.1},
                                                      {'date': '2025-07-01', 'value': 192.0},
                                                      {'date': '2025-08-01', 'value': 185.5},
                                                      {'date': '2025-09-01', 'value': 197.4},
                                                      {'date': '2025-10-01', 'value': 198.1},
                                                      {'date': '2025-11-01', 'value': 202.0},
                                                      {'date': '2025-12-01', 'value': 205.7},
                                                      {'date': '2026-01-01', 'value': 204.5},
                                                      {'date': '2026-02-01', 'value': 209.6},
                                                      {'date': '2026-03-01', 'value': 212.7},
                                                      {'date': '2026-04-01', 'value': 214.0},
                                                      {'date': '2026-05-01', 'value': 216.2},
                                                      {'date': '2026-06-01', 'value': 197.1},
                                                      {'date': '2026-07-01', 'value': 213.4},
                                                      {'date': '2026-08-01', 'value': 224.0},
                                                      {'date': '2026-09-01', 'value': 239.6},
                                                      {'date': '2026-10-01', 'value': 226.5}]},
                                          {'id': 'wheat',
                                           'name': 'Trigo',
                                           'source_name': 'Wheat, US HRW',
                                           'unit': 'USD por tonelada métrica',
                                           'note': 'Trigo duro rojo de invierno n.º 2 de EE. UU.; referencia de '
                                                   'exportación del Golfo.',
                                           'points': [{'date': '2023-11-01', 'value': 283.6},
                                                      {'date': '2023-12-01', 'value': 291.1},
                                                      {'date': '2024-01-01', 'value': 283.9},
                                                      {'date': '2024-02-01', 'value': 278.5},
                                                      {'date': '2024-03-01', 'value': 274.8},
                                                      {'date': '2024-04-01', 'value': 272.3},
                                                      {'date': '2024-05-01', 'value': 289.4},
                                                      {'date': '2024-06-01', 'value': 265.6},
                                                      {'date': '2024-07-01', 'value': 260.3},
                                                      {'date': '2024-08-01', 'value': 250.9},
                                                      {'date': '2024-09-01', 'value': 269.7},
                                                      {'date': '2024-10-01', 'value': 272.9},
                                                      {'date': '2024-11-01', 'value': 253.8},
                                                      {'date': '2024-12-01', 'value': 252.2},
                                                      {'date': '2025-01-01', 'value': 254.1},
                                                      {'date': '2025-02-01', 'value': 264.6},
                                                      {'date': '2025-03-01', 'value': 255.4},
                                                      {'date': '2025-04-01', 'value': 249.6},
                                                      {'date': '2025-05-01', 'value': 237.0},
                                                      {'date': '2025-06-01', 'value': 240.1},
                                                      {'date': '2025-07-01', 'value': 235.0},
                                                      {'date': '2025-08-01', 'value': 231.1},
                                                      {'date': '2025-09-01', 'value': 233.8},
                                                      {'date': '2025-10-01', 'value': 230.8},
                                                      {'date': '2025-11-01', 'value': 245.9},
                                                      {'date': '2025-12-01', 'value': 242.8},
                                                      {'date': '2026-01-01', 'value': 249.9},
                                                      {'date': '2026-02-01', 'value': 257.6},
                                                      {'date': '2026-03-01', 'value': 276.0},
                                                      {'date': '2026-04-01', 'value': 282.0},
                                                      {'date': '2026-05-01', 'value': 303.0},
                                                      {'date': '2026-06-01', 'value': 286.0},
                                                      {'date': '2026-07-01', 'value': 310.0},
                                                      {'date': '2026-08-01', 'value': 330.0},
                                                      {'date': '2026-09-01', 'value': 347.0},
                                                      {'date': '2026-10-01', 'value': 317.0}]},
                                          {'id': 'soybeans',
                                           'name': 'Soya',
                                           'source_name': 'Soybeans',
                                           'unit': 'USD por tonelada métrica',
                                           'note': 'La referencia de soya cambia de CIF Rotterdam a FOB Golfo de EE. '
                                                   'UU. desde enero de 2025; considera ese cambio al comparar '
                                                   'periodos.',
                                           'points': [{'date': '2023-11-01', 'value': 553.0},
                                                      {'date': '2023-12-01', 'value': 547.0},
                                                      {'date': '2024-01-01', 'value': 547.0},
                                                      {'date': '2024-02-01', 'value': 520.0},
                                                      {'date': '2024-03-01', 'value': 487.0},
                                                      {'date': '2024-04-01', 'value': 477.0},
                                                      {'date': '2024-05-01', 'value': 490.0},
                                                      {'date': '2024-06-01', 'value': 480.0},
                                                      {'date': '2024-07-01', 'value': 470.0},
                                                      {'date': '2024-08-01', 'value': 400.0},
                                                      {'date': '2024-09-01', 'value': 391.0},
                                                      {'date': '2024-10-01', 'value': 442.0},
                                                      {'date': '2024-11-01', 'value': 436.0},
                                                      {'date': '2024-12-01', 'value': 409.0},
                                                      {'date': '2025-01-01', 'value': 411.0},
                                                      {'date': '2025-02-01', 'value': 412.0},
                                                      {'date': '2025-03-01', 'value': 401.0},
                                                      {'date': '2025-04-01', 'value': 408.0},
                                                      {'date': '2025-05-01', 'value': 414.0},
                                                      {'date': '2025-06-01', 'value': 416.0},
                                                      {'date': '2025-07-01', 'value': 410.0},
                                                      {'date': '2025-08-01', 'value': 407.0},
                                                      {'date': '2025-09-01', 'value': 404.0},
                                                      {'date': '2025-10-01', 'value': 404.0},
                                                      {'date': '2025-11-01', 'value': 446.0},
                                                      {'date': '2025-12-01', 'value': 440.0},
                                                      {'date': '2026-01-01', 'value': 425.0},
                                                      {'date': '2026-02-01', 'value': 459.0},
                                                      {'date': '2026-03-01', 'value': 473.0},
                                                      {'date': '2026-04-01', 'value': 463.0},
                                                      {'date': '2026-05-01', 'value': 473.0},
                                                      {'date': '2026-06-01', 'value': 464.0},
                                                      {'date': '2026-07-01', 'value': 478.0},
                                                      {'date': '2026-08-01', 'value': 482.0},
                                                      {'date': '2026-09-01', 'value': 524.0},
                                                      {'date': '2026-10-01', 'value': 515.0}]}],
                               'unit': 'USD por tonelada métrica',
                               'frequency': 'monthly',
                               'period_start': '2023-11-01',
                               'period_end': '2026-10-01',
                               'source': 'Banco Mundial — Commodity Price Data (Pink Sheet)',
                               'source_url': 'https://www.worldbank.org/en/research/commodity-markets',
                               'note': 'Precios internacionales mensuales observados. Sirven como contexto agrícola; '
                                       'no son precios locales, demanda de sensores ni un pronóstico de ventas.',
                               'data_url': 'https://thedocs.worldbank.org/en/doc/74e8be41ceb20fa0da750cda2f6b9e4e-0050012026/related/CMO-Historical-Data-Monthly.xlsx'},
                   'last_checked': None,
                   'last_success': '2026-11-06T23:46:29+00:00',
                   'next_check': None,
                   'error': 'bundled_snapshot',
                   'snapshot': True}}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat(timespec="seconds")


def _parse_timestamp(value: str | None) -> datetime | None:
    try:
        result = datetime.fromisoformat(value or "")
        return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result.astimezone(timezone.utc)
    except (TypeError, ValueError):
        return None


def _cache_path() -> Path:
    configured = os.getenv("ERP_EXTERNAL_CACHE_PATH")
    if configured:
        return Path(configured).expanduser().resolve()
    database = os.getenv("ERP_DB_PATH")
    parent = Path(database).expanduser().resolve().parent if database and database != ":memory:" else Path(__file__).resolve().parent / "data"
    return parent / "external_data_cache.json"


def _store(path: Path) -> dict:
    key = str(path)
    with _STORE_LOCK:
        if key not in _STORES:
            value = copy.deepcopy(_SEED)
            try:
                saved = json.loads(path.read_text(encoding="utf-8"))
                if saved.get("version") == 1 and isinstance(saved.get("records"), dict):
                    for name, record in saved["records"].items():
                        if isinstance(record, dict) and isinstance(record.get("payload"), dict):
                            value[name] = record
            except (OSError, ValueError, TypeError, AttributeError):
                pass
            _STORES[key] = value
        return _STORES[key]


def _save(path: Path) -> None:
    with _STORE_LOCK:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(json.dumps({"version": 1, "records": _STORES[str(path)]}, ensure_ascii=False, allow_nan=False), encoding="utf-8")
            temporary.replace(path)
        except (OSError, ValueError):
            # La operación de caja sigue disponible si el disco es de solo lectura.
            pass


def _download(url: str, deadline: float, limit: int = MAX_DOWNLOAD_BYTES) -> bytes:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError("Tiempo de consulta agotado")
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in {"api.frankfurter.dev", "www.worldbank.org", "thedocs.worldbank.org"}:
        raise ValueError("Origen no permitido")
    timeout = (min(2, remaining), min(6, remaining))
    with requests.get(url, timeout=timeout, stream=True, allow_redirects=False,
                      headers={"User-Agent": "ERP-AgTech-academic/1.0", "Accept": "*/*"}) as response:
        response.raise_for_status()
        if response.status_code != 200:
            raise ValueError("Respuesta incompleta del proveedor")
        if int(response.headers.get("Content-Length", 0)) > limit:
            raise ValueError("Descarga demasiado grande")
        chunks, total = [], 0
        for chunk in response.iter_content(chunk_size=65536):
            total += len(chunk)
            if total > limit:
                raise ValueError("Descarga demasiado grande")
            if time.monotonic() > deadline:
                raise TimeoutError("Tiempo de consulta agotado")
            chunks.append(chunk)
        return b"".join(chunks)


def _fetch_exchange_rate() -> dict:
    data = json.loads(_download(FX_URL, time.monotonic() + 9, limit=65536))
    if not isinstance(data, dict) or data.get("base") != "USD" or data.get("quote") != "MXN":
        raise ValueError("Monedas inesperadas")
    rate = float(data["rate"])
    observed = date.fromisoformat(data["date"])
    if not math.isfinite(rate) or rate <= 0 or rate > 1000 or observed > _now().date():
        raise ValueError("Tipo de cambio o fecha inválidos")
    return {"rate": rate, "date": observed.isoformat(), "base": "USD", "quote": "MXN",
            "source": "Banco Central Europeo, vía Frankfurter", "source_url": FX_SOURCE_URL,
            "data_url": FX_URL, "unit": "MXN por USD",
            "note": "Referencia diaria publicada; puede conservar la fecha del último día hábil. No es una cotización bancaria de compra o venta."}


def _parse_market_workbook(content: bytes) -> dict:
    workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    try:
        rows = list(workbook["Monthly Prices"].iter_rows(values_only=True))
        header_index = next(i for i, row in enumerate(rows[:25]) if all(col in [str(v).strip() for v in row] for _, _, col, _ in COMMODITIES))
        headers = [str(value).strip() for value in rows[header_index]]
        indexes = {series_id: headers.index(column) for series_id, _, column, _ in COMMODITIES}
        units = rows[header_index + 1]
        if any("$/mt" not in str(units[i]) for i in indexes.values()):
            raise ValueError("La unidad del proveedor cambió")
        values = {key: {} for key in indexes}
        for row in rows[header_index + 2:]:
            match = re.fullmatch(r"(\d{4})M(\d{2})", str(row[0] or ""))
            if not match:
                continue
            observed = date(int(match[1]), int(match[2]), 1)
            if observed > _now().date():
                continue
            for series_id, index in indexes.items():
                try:
                    number = float(row[index])
                except (TypeError, ValueError, IndexError):
                    continue
                if math.isfinite(number) and number > 0:
                    values[series_id][observed.isoformat()] = number
        series = []
        for series_id, name, column, note in COMMODITIES:
            points = [{"date": when, "value": value} for when, value in sorted(values[series_id].items())[-36:]]
            if len(points) < 2:
                raise ValueError("Serie mensual insuficiente")
            series.append({"id": series_id, "name": name, "source_name": column,
                           "unit": "USD por tonelada métrica", "note": note, "points": points})
        return {"series": series, "unit": "USD por tonelada métrica", "frequency": "monthly",
                "period_start": min(item["points"][0]["date"] for item in series),
                "period_end": max(item["points"][-1]["date"] for item in series),
                "source": "Banco Mundial — Commodity Price Data (Pink Sheet)", "source_url": MARKET_SOURCE_URL,
                "note": "Precios internacionales mensuales observados. Sirven como contexto agrícola; no son precios locales, demanda de sensores ni un pronóstico de ventas."}
    finally:
        workbook.close()


def _fetch_market_trends() -> dict:
    deadline = time.monotonic() + 9
    data_url = MARKET_DATA_URL
    try:
        page = _download(MARKET_SOURCE_URL, deadline, limit=3 * 1024 * 1024).decode("utf-8", errors="replace")
        candidates = re.findall(r'https://thedocs\.worldbank\.org/[^\s<>"\']*CMO-Historical-Data-Monthly\.xlsx', page, flags=re.IGNORECASE)
        if candidates:
            data_url = candidates[0].replace("&amp;", "&")
    except (requests.RequestException, ValueError, TimeoutError, OSError):
        # El enlace estable verificado permite actualizar aunque falle la portada.
        pass
    result = _parse_market_workbook(_download(data_url, deadline))
    result["data_url"] = data_url
    return result


def _result(record: dict, *, offline: bool = False) -> dict:
    payload = copy.deepcopy(record.get("payload") or {})
    available = bool(payload)
    failed = bool(record.get("error")) or offline
    status = "unavailable" if not available else ("stale" if failed else "fresh")
    if offline:
        message = "Sin conexión automática: se muestra el último dato real disponible con su fecha." if available else "Sin conexión y sin datos reales guardados."
    elif status == "stale":
        message = "No se pudo actualizar la fuente. Se conserva el último dato real disponible con su fecha."
    elif status == "unavailable":
        message = "La fuente no está disponible y no hay datos reales guardados."
    else:
        message = "Última publicación disponible consultada correctamente."
    payload.update({"available": available, "status": status, "message": message,
                    "last_checked": record.get("last_checked"), "last_success": record.get("last_success"),
                    "next_check": record.get("next_check"), "snapshot": bool(record.get("snapshot"))})
    return payload


def _get(name: str, fetcher, interval: int, force: bool) -> dict:
    path = _cache_path()
    with _STORE_LOCK:
        lock = _RESOURCE_LOCKS.setdefault((str(path), name), threading.RLock())
    with lock:
        storage = _store(path)
        record = storage.get(name, {})
        if os.getenv("ERP_EXTERNAL_DATA_OFFLINE", "").lower() in {"1", "true", "yes"}:
            return _result(record, offline=True)
        now = _now()
        next_check = _parse_timestamp(record.get("next_check"))
        if not force and next_check and now < next_check:
            return _result(record)
        updated = copy.deepcopy(record)
        updated["last_checked"] = _iso(now)
        try:
            updated["payload"] = fetcher()
            updated.update({"last_success": _iso(_now()), "error": None, "snapshot": False,
                            "next_check": _iso(now + timedelta(seconds=interval))})
        except (requests.RequestException, ValueError, KeyError, StopIteration, OSError, TimeoutError, TypeError, IndexError,
                BadZipFile, ParseError, InvalidFileException) as exc:
            updated.update({"error": type(exc).__name__, "next_check": _iso(now + timedelta(seconds=RETRY_SECONDS))})
        storage[name] = updated
        _save(path)
        return _result(updated)


def get_exchange_rate(force: bool = False) -> dict:
    """Referencia USD/MXN; reconsulta tras 6 horas y conserva el último éxito."""
    return _get("exchange_rate", _fetch_exchange_rate, FX_REFRESH_SECONDS, force)


def get_market_trends(force: bool = False) -> dict:
    """Últimos 36 meses reales por producto; reconsulta tras 24 horas."""
    return _get("market_trends", _fetch_market_trends, MARKET_REFRESH_SECONDS, force)
