import os
import io
import uuid
import math
import pandas as pd
import numpy as np
import numpy_financial as npf
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

import json
import sqlite3
import threading
import secrets
import hashlib
import hmac
import functools
import copy
from contextlib import closing
import time
import re
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter, defaultdict
from decimal import Decimal, ROUND_HALF_UP
from fastapi import Request
from fastapi.responses import JSONResponse
from pydantic import ConfigDict

# El modo demostración funciona sin claves ni servicios externos.
app = FastAPI(title="ERP AgTech - Backend Visual Multi-Presupuesto ⚙️")

# ==============================================================================
# 1. BASE DE DATOS EN MEMORIA
# ==============================================================================

# 1.1 Usuarios y Roles (RBAC)
db_usuarios = {
    "gerente": {
        "password": "123",
        "rol": "Gerente General",
        "icono": "👔",
        "descripcion_acceso": "Control total: Apertura de sedes GPS, TPV, Simulador IA, Ingeniería y Exportación Excel.",
        "permisos": ["registrar_sede", "tpv", "simulador", "ingenieria", "exportar"]
    },
    "cajero": {
        "password": "123",
        "rol": "Cajero / Operador TPV",
        "icono": "🛒",
        "descripcion_acceso": "Operación exclusiva en Punto de Venta, Armador de Combos e Historial (Sujeto a Geocerca GPS).",
        "permisos": ["tpv"]
    },
    "ingeniero": {
        "password": "123",
        "rol": "Ingeniero de Planta",
        "icono": "⚙️",
        "descripcion_acceso": "Acceso a Simulador Financiero, Presupuestos SMT, Diagramas de Flujo Dinámicos y Excel.",
        "permisos": ["simulador", "ingenieria", "exportar"]
    }
}

# 1.2 Sedes y Ventas
db_negocios: Dict[str, dict] = {}
db_ventas: List[dict] = []

# 1.3 Catálogo Detallado de Componentes e Inventario Inicial (Para Combos y Refacciones)
db_componentes = {
    "PLACA_ESP32": {
        "categoria": "Placa Base", "icono": "🟢", "nombre": "Microcontrolador ESP32-WROOM",
        "especificaciones": "Dual-Core 240MHz, 520KB SRAM, Wi-Fi/BT integrado (Bajo consumo)",
        "presupuesto_ligado": "P1_ECONOMICO", "nivel_tag": "Económico",
        "stock": 150, "costo_unitario": 150.0, "precio_publico": 450.0
    },
    "PLACA_RADXA": {
        "categoria": "Placa Base", "icono": "🔵", "nombre": "Placa SBC Radxa ROCK 4C+",
        "especificaciones": "Rockchip RK3399-T 6-Core, 4GB LPDDR4, GPU Mali-T860",
        "presupuesto_ligado": "P2_OBJETIVO", "nivel_tag": "Objetivo",
        "stock": 100, "costo_unitario": 1300.0, "precio_publico": 3200.0
    },
    "PLACA_RPI5": {
        "categoria": "Placa Base", "icono": "🟣", "nombre": "Raspberry Pi 5 Industrial",
        "especificaciones": "Broadcom BCM2712 Quad-Core 2.4GHz, 8GB RAM, Bus PCIe 2.0",
        "presupuesto_ligado": "P3_PREMIUM", "nivel_tag": "Premium",
        "stock": 80, "costo_unitario": 1600.0, "precio_publico": 4200.0
    },
    "ALM_MICROSD": {
        "categoria": "Almacenamiento", "icono": "💾", "nombre": "Memoria MicroSD Industrial 32GB",
        "especificaciones": "Clase 10 UHS-I (Incluida en arquitectura base / Flasheo directo)",
        "presupuesto_ligado": "P1_ECONOMICO", "nivel_tag": "Económico",
        "stock": 150, "costo_unitario": 100.0, "precio_publico": 300.0
    },
    "ALM_EMMC": {
        "categoria": "Almacenamiento", "icono": "💿", "nombre": "Módulo eMMC Alta Velocidad 64GB",
        "especificaciones": "Soldadura BGA SMT, 400 MB/s lectura, Grado Industrial",
        "presupuesto_ligado": "P2_OBJETIVO", "nivel_tag": "Objetivo",
        "stock": 100, "costo_unitario": 500.0, "precio_publico": 1250.0
    },
    "ALM_NVME": {
        "categoria": "Almacenamiento", "icono": "⚡", "nombre": "Disco SSD NVMe M.2 1TB + HAT",
        "especificaciones": "PCIe Gen3, 2500 MB/s, disipador térmico pasivo de aluminio",
        "presupuesto_ligado": "P3_PREMIUM", "nivel_tag": "Premium",
        "stock": 80, "costo_unitario": 1300.0, "precio_publico": 2900.0
    },
    "SEN_CONDUCT": {
        "categoria": "Sensor", "icono": "🧪", "nombre": "Sensor de Conductividad Eléctrica y pH",
        "especificaciones": "RS485 Modbus, IP68 sumergible, medición NPK y salinidad",
        "presupuesto_ligado": "TODOS", "nivel_tag": "Estándar",
        "stock": 220, "costo_unitario": 500.0, "precio_publico": 1500.0
    },
    "SEN_DHT22": {
        "categoria": "Sensor", "icono": "🌡️", "nombre": "Sensor de Clima (DHT22 / BME280)",
        "especificaciones": "Temp: -40 a 80°C (±0.5°C), Humedad relativa: 0-100% RH",
        "presupuesto_ligado": "TODOS", "nivel_tag": "Estándar",
        "stock": 300, "costo_unitario": 250.0, "precio_publico": 650.0
    },
    "SEN_SUELO": {
        "categoria": "Sensor", "icono": "🌱", "nombre": "Sensor Capacitivo de Humedad de Suelo",
        "especificaciones": "Anticorrosivo v2.0, salida analógica/digital I2C",
        "presupuesto_ligado": "TODOS", "nivel_tag": "Estándar",
        "stock": 300, "costo_unitario": 50.0, "precio_publico": 200.0
    },
    "FUENTE_CHASIS": {
        "categoria": "Producción/Chasis", "icono": "🛡️", "nombre": "Carcasa Plástica 3D IP65 + Fuente",
        "especificaciones": "Impresión 3D PETG UV + Fuente conmutada regulada 12V/5V",
        "presupuesto_ligado": "TODOS", "nivel_tag": "Estándar",
        "stock": 250, "costo_unitario": 150.0, "precio_publico": 950.0
    }
}

# 1.4 Tabla Comparativa de Materia Prima (BOM) por Kit (Alineada al Reporte PDF)
db_bom_comparativa_kits = [
    {
        "Concepto / Componente": "1. Placa Base o Microcontrolador",
        "Kit 1: Económico (ESP32)": "ESP32 ($150 MXN)",
        "Kit 2: Objetivo (Radxa)": "Radxa ROCK 4C+ ($1,300 MXN)",
        "Kit 3: Premium (Raspberry Pi 5)": "Raspberry Pi 5 ($1,600 MXN)",
        "Costo_P1": 150.0, "Costo_P2": 1300.0, "Costo_P3": 1600.0
    },
    {
        "Concepto / Componente": "2. Almacenamiento (SSD / eMMC)",
        "Kit 1: Económico (ESP32)": "Flash Integrada ($0 MXN)",
        "Kit 2: Objetivo (Radxa)": "Módulo eMMC 64GB ($500 MXN)",
        "Kit 3: Premium (Raspberry Pi 5)": "SSD NVMe 1TB M.2 ($1,300 MXN)",
        "Costo_P1": 0.0, "Costo_P2": 500.0, "Costo_P3": 1300.0
    },
    {
        "Concepto / Componente": "3. Sensor de Conductividad Eléctrica",
        "Kit 1: Económico (ESP32)": "Sonda Analógica ($500 MXN)",
        "Kit 2: Objetivo (Radxa)": "Sonda Industrial RS485 ($500 MXN)",
        "Kit 3: Premium (Raspberry Pi 5)": "Sonda Industrial RS485 ($500 MXN)",
        "Costo_P1": 500.0, "Costo_P2": 500.0, "Costo_P3": 500.0
    },
    {
        "Concepto / Componente": "4. Sensor de Clima (DHT22 / BME280)",
        "Kit 1: Económico (ESP32)": "DHT22 Básico ($100 MXN)",
        "Kit 2: Objetivo (Radxa)": "BME280 Alta Precisión ($250 MXN)",
        "Kit 3: Premium (Raspberry Pi 5)": "DHT22 Estándar ($100 MXN)",
        "Costo_P1": 100.0, "Costo_P2": 250.0, "Costo_P3": 100.0
    },
    {
        "Concepto / Componente": "5. Sensor de Humedad de Suelo",
        "Kit 1: Económico (ESP32)": "Capacitivo ($50 MXN)",
        "Kit 2: Objetivo (Radxa)": "Capacitivo ($50 MXN)",
        "Kit 3: Premium (Raspberry Pi 5)": "Capacitivo ($50 MXN)",
        "Costo_P1": 50.0, "Costo_P2": 50.0, "Costo_P3": 50.0
    },
    {
        "Concepto / Componente": "6. Fuente de Alimentación / MicroSD",
        "Kit 1: Económico (ESP32)": "Regulador 5V ($50 MXN)",
        "Kit 2: Objetivo (Radxa)": "Incluido en Placa ($0 MXN)",
        "Kit 3: Premium (Raspberry Pi 5)": "Fuente Dedicada PD 27W ($400 MXN)",
        "Costo_P1": 50.0, "Costo_P2": 0.0, "Costo_P3": 400.0
    },
    {
        "Concepto / Componente": "7. Carcasa Plástica Protectora",
        "Kit 1: Económico (ESP32)": "Caja ABS Básica ($100 MXN)",
        "Kit 2: Objetivo (Radxa)": "Impresión 3D PETG IP65 ($150 MXN)",
        "Kit 3: Premium (Raspberry Pi 5)": "Incluida en Chasis ($0 MXN)",
        "Costo_P1": 100.0, "Costo_P2": 150.0, "Costo_P3": 0.0
    },
    {
        "Concepto / Componente": "💰 COSTO TOTAL UNITARIO (MATERIA PRIMA)",
        "Kit 1: Económico (ESP32)": "$950.00 MXN",
        "Kit 2: Objetivo (Radxa)": "$2,750.00 MXN",
        "Kit 3: Premium (Raspberry Pi 5)": "$3,950.00 MXN",
        "Costo_P1": 950.0, "Costo_P2": 2750.0, "Costo_P3": 3950.0
    },
    {
        "Concepto / Componente": "🏷️ PRECIO DE VENTA AL PÚBLICO SUGERIDO",
        "Kit 1: Económico (ESP32)": "$3,800.00 MXN",
        "Kit 2: Objetivo (Radxa)": "$10,500.00 MXN",
        "Kit 3: Premium (Raspberry Pi 5)": "$15,900.00 MXN",
        "Costo_P1": 3800.0, "Costo_P2": 10500.0, "Costo_P3": 15900.0
    }
]

# 1.5 Tablas Estructuradas de los 3 Presupuestos (Maquinaria, Almacenamiento, Producción e Inv. Inicial)
db_presupuestos_tablas = [
    {
        "id_presupuesto": "P1_ECONOMICO",
        "icono": "🟢",
        "nombre_corto": "Presupuesto 1: Económico (ESP32)",
        "nombre_nivel": "Presupuesto 1: Línea Económica (Arquitectura ESP32)",
        "arquitectura_base": "ESP32-WROOM + Sensores Básicos",
        "capacidad_planta": "1,500 CPH (60 Kits/mes máx)",
        "lote_inventario_inicial_uds": 60,
        "inversion_maquinaria_mxn": 250000.0,
        "inversion_almacenamiento_planta_mxn": 45000.0,
        "inversion_produccion_instalacion_mxn": 35000.0,
        "costo_inventario_inicial_mxn": 57000.0,
        "capex_total_mxn": 387000.0,
        "costo_produccion_kit_mxn": 950.0,
        "precio_publico_kit_mxn": 3800.0,
        "utilidad_unitaria_mxn": 2850.0,
        "margen_unitario_pct": 75.0,
        "calificacion_multicriterio": 3.45,
        "tabla_maquinaria_y_produccion": [
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Pick & Place Escritorio NeoDen YY1", "Especificación / Capacidad": "2 cabezales, visión simple, 1,500 CPH", "Costo Total (MXN)": 145000.0},
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Horno de Reflujo de Cajón T-962A", "Especificación / Capacidad": "Infrarrojo 1500W, ventana 300x320mm", "Costo Total (MXN)": 65000.0},
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Estaciones Manuales Weller WE1010 (x4)", "Especificación / Capacidad": "70W digital para conectores y sensores", "Costo Total (MXN)": 40000.0},
            {"Categoría": "2. Almacenamiento", "Concepto": "Racks Metálicos y Contenedores ESD", "Especificación / Capacidad": "Estantería ligera + 100 gavetas conductivas", "Costo Total (MXN)": 45000.0},
            {"Categoría": "3. Producción y Planta", "Concepto": "Adecuación de Taller, Mesas y Extractores", "Especificación / Capacidad": "4 mesas antiestáticas, pasta soldar, ventilación", "Costo Total (MXN)": 35000.0},
            {"Categoría": "4. Inventario Inicial", "Concepto": "Lote de Arranque: 60 Kits ESP32 Completos", "Especificación / Capacidad": "Costo prod: $950 c/u (Valor público: $228,000)", "Costo Total (MXN)": 57000.0}
        ],
        "tabla_inventario_kit": [
            {"Componente del Kit": "Microcontrolador ESP32-WROOM", "Capacidad / Especificación": "Dual-Core 240MHz, Wi-Fi/BT", "Stock Inicial (Uds)": 60, "Costo Unit. (MXN)": 150.0, "Precio Público Unit. (MXN)": 450.0, "Costo Lote Inicial (MXN)": 9000.0},
            {"Componente del Kit": "Sensor Conductividad Eléctrica", "Capacidad / Especificación": "Sonda NPK y salinidad", "Stock Inicial (Uds)": 60, "Costo Unit. (MXN)": 500.0, "Precio Público Unit. (MXN)": 1500.0, "Costo Lote Inicial (MXN)": 30000.0},
            {"Componente del Kit": "Sensor Clima DHT22", "Capacidad / Especificación": "Temp -40 a 80°C, Humedad RH", "Stock Inicial (Uds)": 60, "Costo Unit. (MXN)": 100.0, "Precio Público Unit. (MXN)": 400.0, "Costo Lote Inicial (MXN)": 6000.0},
            {"Componente del Kit": "Sensor Humedad de Suelo", "Capacidad / Especificación": "Capacitivo anticorrosivo", "Stock Inicial (Uds)": 60, "Costo Unit. (MXN)": 50.0, "Precio Público Unit. (MXN)": 250.0, "Costo Lote Inicial (MXN)": 3000.0},
            {"Componente del Kit": "Fuente 5V + Carcasa ABS", "Capacidad / Especificación": "Regulador 5V y caja sellada", "Stock Inicial (Uds)": 60, "Costo Unit. (MXN)": 150.0, "Precio Público Unit. (MXN)": 1200.0, "Costo Lote Inicial (MXN)": 9000.0}
        ]
    },
    {
        "id_presupuesto": "P2_OBJETIVO",
        "icono": "🔵",
        "nombre_corto": "Presupuesto 2: Objetivo (Radxa)",
        "nombre_nivel": "Presupuesto 2: Línea Objetivo Reporte (Arquitectura Radxa)",
        "arquitectura_base": "Radxa ROCK 4C+ + eMMC 64GB + Carcasa 3D",
        "capacidad_planta": "8,000 CPH (250 Kits/mes óptimos)",
        "lote_inventario_inicial_uds": 100,
        "inversion_maquinaria_mxn": 1200000.0,
        "inversion_almacenamiento_planta_mxn": 180000.0,
        "inversion_produccion_instalacion_mxn": 120000.0,
        "costo_inventario_inicial_mxn": 275000.0,
        "capex_total_mxn": 1775000.0,
        "costo_produccion_kit_mxn": 2750.0,
        "precio_publico_kit_mxn": 10500.0,
        "utilidad_unitaria_mxn": 7750.0,
        "margen_unitario_pct": 73.8,
        "calificacion_multicriterio": 4.40,
        "tabla_maquinaria_y_produccion": [
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Pick & Place Industrial NeoDen 8", "Especificación / Capacidad": "8 cabezales, Flying Vision, 8,000 CPH (Chips BGA)", "Costo Total (MXN)": 780000.0},
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Horno de Reflujo Túnel Continuo IN6", "Especificación / Capacidad": "6 zonas térmicas por convección de aire caliente", "Costo Total (MXN)": 290000.0},
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Inspección Óptica (AOI) + Impresora Esténcil", "Especificación / Capacidad": "Cámara detectora de cortos en soldadura eMMC", "Costo Total (MXN)": 130000.0},
            {"Categoría": "2. Almacenamiento", "Concepto": "Gabinetes Secos (Dry-Cabinets) y Almacén ESD", "Especificación / Capacidad": "Control humedad <5% RH para chips BGA y racks", "Costo Total (MXN)": 180000.0},
            {"Categoría": "3. Producción y Planta", "Concepto": "Mobiliario ESD, Redes y Granja Impresión 3D", "Especificación / Capacidad": "Bancos de flasheo Linux, red local y permisos", "Costo Total (MXN)": 120000.0},
            {"Categoría": "4. Inventario Inicial", "Concepto": "Lote de Arranque: 100 Kits Radxa Completos", "Especificación / Capacidad": "Costo prod: $2,750 c/u (Valor público: $1,050,000)", "Costo Total (MXN)": 275000.0}
        ],
        "tabla_inventario_kit": [
            {"Componente del Kit": "Placa SBC Radxa ROCK 4C+", "Capacidad / Especificación": "6-Core RK3399-T, 4GB RAM LPDDR4", "Stock Inicial (Uds)": 100, "Costo Unit. (MXN)": 1300.0, "Precio Público Unit. (MXN)": 3800.0, "Costo Lote Inicial (MXN)": 130000.0},
            {"Componente del Kit": "Almacenamiento eMMC 64GB", "Capacidad / Especificación": "Soldadura BGA SMT, 400 MB/s", "Stock Inicial (Uds)": 100, "Costo Unit. (MXN)": 500.0, "Precio Público Unit. (MXN)": 1900.0, "Costo Lote Inicial (MXN)": 50000.0},
            {"Componente del Kit": "Sensor Conductividad Eléctrica", "Capacidad / Especificación": "RS485 Modbus IP68 sumergible", "Stock Inicial (Uds)": 100, "Costo Unit. (MXN)": 500.0, "Precio Público Unit. (MXN)": 2200.0, "Costo Lote Inicial (MXN)": 50000.0},
            {"Componente del Kit": "Sensor Clima BME280 / DHT22", "Capacidad / Especificación": "Alta precisión Temp/Humedad/Presión", "Stock Inicial (Uds)": 100, "Costo Unit. (MXN)": 250.0, "Precio Público Unit. (MXN)": 1100.0, "Costo Lote Inicial (MXN)": 25000.0},
            {"Componente del Kit": "Sensor Humedad Suelo + Carcasa 3D", "Capacidad / Especificación": "Sonda capacitiva ($50) + Carcasa 3D ($150)", "Stock Inicial (Uds)": 100, "Costo Unit. (MXN)": 200.0, "Precio Público Unit. (MXN)": 1500.0, "Costo Lote Inicial (MXN)": 20000.0}
        ]
    },
    {
        "id_presupuesto": "P3_PREMIUM",
        "icono": "🟣",
        "nombre_corto": "Presupuesto 3: Premium (Raspberry Pi 5)",
        "nombre_nivel": "Presupuesto 3: Línea Escala Industrial (Arquitectura Raspberry Pi 5)",
        "arquitectura_base": "Raspberry Pi 5 8GB + SSD NVMe 1TB M.2",
        "capacidad_planta": "20,000 CPH (1,000+ Kits/mes)",
        "lote_inventario_inicial_uds": 150,
        "inversion_maquinaria_mxn": 2850000.0,
        "inversion_almacenamiento_planta_mxn": 420000.0,
        "inversion_produccion_instalacion_mxn": 310000.0,
        "costo_inventario_inicial_mxn": 592500.0,
        "capex_total_mxn": 4172500.0,
        "costo_produccion_kit_mxn": 3950.0,
        "precio_publico_kit_mxn": 15900.0,
        "utilidad_unitaria_mxn": 11950.0,
        "margen_unitario_pct": 75.1,
        "calificacion_multicriterio": 3.55,
        "tabla_maquinaria_y_produccion": [
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Centro SMT Alta Velocidad Yamaha YRM20", "Especificación / Capacidad": "20,000 CPH, alimentadores inteligentes non-stop", "Costo Total (MXN)": 1950000.0},
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Horno Industrial 8 Zonas con Nitrógeno", "Especificación / Capacidad": "Atmósfera inerte para alta masa térmica (NVMe)", "Costo Total (MXN)": 620000.0},
            {"Categoría": "1. Maquinaria SMT", "Concepto": "Inspección 3D Rayos-X y AOI en Línea", "Especificación / Capacidad": "Banda automatizada cero defectos", "Costo Total (MXN)": 280000.0},
            {"Categoría": "2. Almacenamiento", "Concepto": "Bodega Automatizada y Carrusel Vertical", "Especificación / Capacidad": "Carrusel SMD climatizado, cuarto limpio y patines", "Costo Total (MXN)": 420000.0},
            {"Categoría": "3. Producción y Planta", "Concepto": "Subestación Trifásica y Servidores de Flasheo", "Especificación / Capacidad": "Generador N2, red industrial y clonadoras MicroSD/NVMe", "Costo Total (MXN)": 310000.0},
            {"Categoría": "4. Inventario Inicial", "Concepto": "Lote de Arranque: 150 Kits Raspberry Pi 5", "Especificación / Capacidad": "Costo prod: $3,950 c/u (Valor público: $2,385,000)", "Costo Total (MXN)": 592500.0}
        ],
        "tabla_inventario_kit": [
            {"Componente del Kit": "Placa Raspberry Pi 5 Industrial", "Capacidad / Especificación": "Quad-Core 2.4GHz, 8GB RAM, PCIe", "Stock Inicial (Uds)": 150, "Costo Unit. (MXN)": 1600.0, "Precio Público Unit. (MXN)": 6200.0, "Costo Lote Inicial (MXN)": 240000.0},
            {"Componente del Kit": "Disco SSD NVMe M.2 1TB", "Capacidad / Especificación": "2500 MB/s + Adaptador PCIe M.2", "Stock Inicial (Uds)": 150, "Costo Unit. (MXN)": 1300.0, "Precio Público Unit. (MXN)": 4800.0, "Costo Lote Inicial (MXN)": 195000.0},
            {"Componente del Kit": "Sensor Conductividad Eléctrica", "Capacidad / Especificación": "RS485 Modbus IP68 sumergible", "Stock Inicial (Uds)": 150, "Costo Unit. (MXN)": 500.0, "Precio Público Unit. (MXN)": 2400.0, "Costo Lote Inicial (MXN)": 75000.0},
            {"Componente del Kit": "Sensores Clima ($100) y Suelo ($50)", "Capacidad / Especificación": "Kit ambiental digital calibrado", "Stock Inicial (Uds)": 150, "Costo Unit. (MXN)": 150.0, "Precio Público Unit. (MXN)": 900.0, "Costo Lote Inicial (MXN)": 22500.0},
            {"Componente del Kit": "Fuente Dedicada PD 27W + Tarjeta SD", "Capacidad / Especificación": "Alimentación industrial 5V/5A aislada", "Stock Inicial (Uds)": 150, "Costo Unit. (MXN)": 400.0, "Precio Público Unit. (MXN)": 1600.0, "Costo Lote Inicial (MXN)": 60000.0}
        ]
    }
]

# 1.6 Tabla de Nómina Mensual y Gastos Operativos (OPEX $580,000 MXN - Tabla 2 del Reporte)
db_nomina_opex = [
    {"Categoría": "Nómina", "Concepto / Puesto": "Operadores de línea e inventario", "Cantidad": 20, "Sueldo / Costo Unitario (MXN)": 8000.0, "Costo Total Mensual (MXN)": 160000.0, "Periodicidad": "Mensual"},
    {"Categoría": "Nómina", "Concepto / Puesto": "Ingenieros de software (Linux / Automatización)", "Cantidad": 5, "Sueldo / Costo Unitario (MXN)": 20000.0, "Costo Total Mensual (MXN)": 100000.0, "Periodicidad": "Mensual"},
    {"Categoría": "Nómina", "Concepto / Puesto": "Técnicos instaladores y electrónicos SMT", "Cantidad": 15, "Sueldo / Costo Unitario (MXN)": 12000.0, "Costo Total Mensual (MXN)": 180000.0, "Periodicidad": "Mensual"},
    {"Categoría": "Nómina", "Concepto / Puesto": "Analistas de control de calidad", "Cantidad": 5, "Sueldo / Costo Unitario (MXN)": 12000.0, "Costo Total Mensual (MXN)": 60000.0, "Periodicidad": "Mensual"},
    {"Categoría": "Operativos", "Concepto / Puesto": "Renta de nave industrial (Texcoco / Sede)", "Cantidad": 1, "Sueldo / Costo Unitario (MXN)": 50000.0, "Costo Total Mensual (MXN)": 50000.0, "Periodicidad": "Mensual"},
    {"Categoría": "Operativos", "Concepto / Puesto": "Servicios básicos (Luz CFE GDMTO, agua, internet)", "Cantidad": 1, "Sueldo / Costo Unitario (MXN)": 30000.0, "Costo Total Mensual (MXN)": 30000.0, "Periodicidad": "Mensual"}
]

# 1.7 Tabla de Matriz de Decisión Multicriterio (Tabla 3 del Reporte)
db_matriz_multicriterio = [
    {"Criterio de Evaluación": "1. Costo de Producción", "Peso (%)": "35%", "Opción 1: Económica (ESP32)": 5, "Opción 2: Objetivo (Radxa)": 4, "Opción 3: Premium (Raspberry Pi)": 2},
    {"Criterio de Evaluación": "2. Capacidad de Procesamiento", "Peso (%)": "25%", "Opción 1: Económica (ESP32)": 2, "Opción 2: Objetivo (Radxa)": 4, "Opción 3: Premium (Raspberry Pi)": 5},
    {"Criterio de Evaluación": "3. Precisión de Sensores", "Peso (%)": "20%", "Opción 1: Económica (ESP32)": 3, "Opción 2: Objetivo (Radxa)": 5, "Opción 3: Premium (Raspberry Pi)": 4},
    {"Criterio de Evaluación": "4. Durabilidad de Materiales", "Peso (%)": "20%", "Opción 1: Económica (ESP32)": 3, "Opción 2: Objetivo (Radxa)": 5, "Opción 3: Premium (Raspberry Pi)": 4},
    {"Criterio de Evaluación": "🏆 CALIFICACIÓN FINAL PONDERADA", "Peso (%)": "100%", "Opción 1: Económica (ESP32)": 3.45, "Opción 2: Objetivo (Radxa)": 4.40, "Opción 3: Premium (Raspberry Pi)": 3.55}
]

# 1.8 Diagramas de Flujo Dinámicos por Línea de Presupuesto
db_flujos_por_presupuesto = {
    "P1_ECONOMICO": {
        "id_presupuesto": "P1_ECONOMICO",
        "titulo": "Flujo Línea 1: Ensamblaje Económico de Escritorio (Arquitectura ESP32)",
        "tiempo_total_optimo_min": 19.0,
        "velocidad_smt": "1,500 CPH (NeoDen YY1)",
        "horno_reflujo": "Horno Infrarrojo de Cajón T-962A",
        "almacenamiento_proceso": "Gavetas ESD estándar (Sin control de humedad activo)",
        "nodos": [
            {"id": "A", "label": "INICIO: Lote Económico ESP32", "shape": "oval"},
            {"id": "B", "label": "1. Recepción en Gavetas ESD\nDesempacar ESP32 y PCB 2 capas\n(3.0 min)", "shape": "box"},
            {"id": "C", "label": "2. Flasheo Firmware C++/Arduino\nvía USB-UART (Sin SO Linux)\n(3.0 min)", "shape": "box"},
            {"id": "D", "label": "3. Montaje SMT Escritorio (NeoDen YY1)\n+ Horno de Cajón T-962A (1,500 CPH)\n(6.0 min)", "shape": "box"},
            {"id": "E", "label": "4. Soldadura Manual Weller WE1010\nde Sensores Básicos y Regulador 5V\n(4.0 min)", "shape": "box"},
            {"id": "F", "label": "¿Lectura Serial y\nWi-Fi correcta?\n(1.5 min)", "shape": "diamond"},
            {"id": "G", "label": "NO: Retrabajo con Cautín\nCorregir pines frios\n(8.0 min)", "shape": "box"},
            {"id": "H", "label": "SÍ: Empacar en Caja ABS\ne Ingresar a Stock ($3,800)\n(1.5 min)", "shape": "parallelogram"},
            {"id": "I", "label": "FIN: Lote ESP32 Listo", "shape": "oval"}
        ],
        "aristas": [
            {"origen": "A", "destino": "B", "label": ""},
            {"origen": "B", "destino": "C", "label": ""},
            {"origen": "C", "destino": "D", "label": ""},
            {"origen": "D", "destino": "E", "label": ""},
            {"origen": "E", "destino": "F", "label": ""},
            {"origen": "F", "destino": "G", "label": "No (Error)"},
            {"origen": "G", "destino": "E", "label": "Re-soldar"},
            {"origen": "F", "destino": "H", "label": "Sí (OK)"},
            {"origen": "H", "destino": "I", "label": ""}
        ],
        "tabla_pasos": [
            {"Paso": 1, "Etapa": "Almacén y Recepción", "Actividad": "Contabilizar microcontroladores ESP32 en gavetas ESD", "Equipo / Responsable": "2 Operadores + Mesas ESD", "Tiempo (min)": 3.0},
            {"Paso": 2, "Etapa": "Flasheo Firmware", "Actividad": "Cargar binario ligero por puerto serie USB (Sin Linux)", "Equipo / Responsable": "1 Ingeniero Software", "Tiempo (min)": 3.0},
            {"Paso": 3, "Etapa": "Ensamblaje SMT Básico", "Actividad": "Colocación a 1,500 CPH y fundido en horno de cajón", "Equipo / Responsable": "NeoDen YY1 + Horno T-962A", "Tiempo (min)": 6.0},
            {"Paso": 4, "Etapa": "Integración Sensores", "Actividad": "Soldadura manual de sonda, DHT22 y regulador 5V", "Equipo / Responsable": "Técnico + Weller WE1010", "Tiempo (min)": 4.0},
            {"Paso": 5, "Etapa": "Control de Calidad", "Actividad": "Inspección visual con lupa y prueba de ping Wi-Fi", "Equipo / Responsable": "1 Analista Calidad", "Tiempo (min)": 1.5},
            {"Paso": 6, "Etapa": "Empaque e Inventario", "Actividad": "Cerrar en caja plástica ABS e ingresar a TPV", "Equipo / Responsable": "Operadores Almacén", "Tiempo (min)": 1.5}
        ]
    },
    "P2_OBJETIVO": {
        "id_presupuesto": "P2_OBJETIVO",
        "titulo": "Flujo Línea 2 (Objetivo Reporte): Automatización SMT Estándar (Arquitectura Radxa)",
        "tiempo_total_optimo_min": 27.0,
        "velocidad_smt": "8,000 CPH (NeoDen 8 con Flying Vision)",
        "horno_reflujo": "Horno de Túnel Continuo IN6 (6 zonas de convección)",
        "almacenamiento_proceso": "Gabinetes Secos (Dry-Cabinets <5% RH) + Impresión 3D PETG",
        "nodos": [
            {"id": "A", "label": "INICIO: Producción Lotes Radxa", "shape": "oval"},
            {"id": "B", "label": "1. Extracción de Gabinete Seco ESD\nPreparar Placas Radxa y chips eMMC\n(5.0 min)", "shape": "box"},
            {"id": "C", "label": "2. Configurar Entorno Linux Server\nHabilitar puertos y demonios en eMMC\n(8.0 min)", "shape": "box"},
            {"id": "D", "label": "3. Línea SMT Industrial (NeoDen 8 - 8,000 CPH)\nSoldar eMMC BGA y Sensores en Horno IN6\n(4.0 min)", "shape": "box"},
            {"id": "E", "label": "4. Transferir Scripts Python/AgTech\ny algoritmos de automatización\n(4.0 min)", "shape": "box"},
            {"id": "F", "label": "¿Inspección AOI y\nlectura RS485 exitosa?\n(2.0 min)", "shape": "diamond"},
            {"id": "G", "label": "NO: Estación de Retrabajo BGA\nCorregir soldadura eMMC/Sensores\n(10.0 min)", "shape": "box"},
            {"id": "H", "label": "SÍ: Montar en Carcasa Impresa 3D\ne Ingresar a Stock ($10,500)\n(4.0 min)", "shape": "parallelogram"},
            {"id": "I", "label": "FIN: Lote Radxa Terminado", "shape": "oval"}
        ],
        "aristas": [
            {"origen": "A", "destino": "B", "label": ""},
            {"origen": "B", "destino": "C", "label": ""},
            {"origen": "C", "destino": "D", "label": ""},
            {"origen": "D", "destino": "E", "label": ""},
            {"origen": "E", "destino": "F", "label": ""},
            {"origen": "F", "destino": "G", "label": "No (Fallo AOI)"},
            {"origen": "G", "destino": "D", "label": "Regresa a SMT"},
            {"origen": "F", "destino": "H", "label": "Sí (Aprobado)"},
            {"origen": "H", "destino": "I", "label": ""}
        ],
        "tabla_pasos": [
            {"Paso": 1, "Etapa": "Almacén Climatizado ESD", "Actividad": "Desempacar placas Radxa y chips eMMC de Dry-Cabinet", "Equipo / Responsable": "2 Operadores + Gabinete Seco", "Tiempo (min)": 5.0},
            {"Paso": 2, "Etapa": "Preparación S.O. Linux", "Actividad": "Instalar Linux, habilitar puertos para servidor local", "Equipo / Responsable": "2 Ingenieros Software", "Tiempo (min)": 8.0},
            {"Paso": 3, "Etapa": "Línea SMT y Reflujo IN6", "Actividad": "Montaje a 8,000 CPH y soldadura en túnel de 6 zonas", "Equipo / Responsable": "NeoDen 8 + Horno IN6", "Tiempo (min)": 4.0},
            {"Paso": 4, "Etapa": "Carga Lógica AgTech", "Actividad": "Transferir código y algoritmos de automatización", "Equipo / Responsable": "1-2 Programadores", "Tiempo (min)": 4.0},
            {"Paso": 5, "Etapa": "Inspección Óptica AOI", "Actividad": "Verificar soldadura BGA y lectura de sensores BME280/RS485", "Equipo / Responsable": "Analista + Cámara AOI", "Tiempo (min)": 2.0},
            {"Paso": 6, "Etapa": "Ensamble 3D e Inventario", "Actividad": "Empaquetar en carcasa impresa 3D y registrar kit terminado", "Equipo / Responsable": "Operadores + Granja 3D", "Tiempo (min)": 4.0}
        ]
    },
    "P3_PREMIUM": {
        "id_presupuesto": "P3_PREMIUM",
        "titulo": "Flujo Línea 3: Alta Velocidad Automatizada (Arquitectura Raspberry Pi 5 + NVMe)",
        "tiempo_total_optimo_min": 14.5,
        "velocidad_smt": "20,000 CPH (Centro Industrial Yamaha YRM20)",
        "horno_reflujo": "Horno de 8 Zonas con Inyección de Nitrógeno (N2)",
        "almacenamiento_proceso": "Carrusel Vertical Automatizado + Cuarto Limpio ISO",
        "nodos": [
            {"id": "A", "label": "INICIO: Línea Masiva Raspberry Pi 5", "shape": "oval"},
            {"id": "B", "label": "1. Suministro por Carrusel Vertical\nLote Raspberry Pi 5 (8GB) + SSD 1TB M.2\n(2.0 min)", "shape": "box"},
            {"id": "C", "label": "2. Clonación Masiva de Imagen Linux\nen Discos NVMe 1TB y MicroSD\n(3.5 min)", "shape": "box"},
            {"id": "D", "label": "3. Centro SMT Yamaha YRM20 (20,000 CPH)\n+ Horno 8 Zonas Nitrógeno (Cero Oxidación)\n(2.0 min)", "shape": "box"},
            {"id": "E", "label": "4. Acoplamiento HAT PCIe NVMe 1TB,\nFuente 27W y Despliegue por Red Gigabit\n(3.0 min)", "shape": "box"},
            {"id": "F", "label": "¿Escaneo 3D Rayos-X y\nTelemetría en Línea OK?\n(1.5 min)", "shape": "diamond"},
            {"id": "G", "label": "NO: Desvío Automático de Banda\nReemplazo de módulo en caliente\n(5.0 min)", "shape": "box"},
            {"id": "H", "label": "SÍ: Empaque Automatizado en Almacén\ne Ingreso a Stock ($15,900)\n(2.5 min)", "shape": "parallelogram"},
            {"id": "I", "label": "FIN: Lote Industrial RPi 5", "shape": "oval"}
        ],
        "aristas": [
            {"origen": "A", "destino": "B", "label": ""},
            {"origen": "B", "destino": "C", "label": ""},
            {"origen": "C", "destino": "D", "label": ""},
            {"origen": "D", "destino": "E", "label": ""},
            {"origen": "E", "destino": "F", "label": ""},
            {"origen": "F", "destino": "G", "label": "No (Descarte)"},
            {"origen": "G", "destino": "D", "label": "Re-ingreso"},
            {"origen": "F", "destino": "H", "label": "Sí (100% OK)"},
            {"origen": "H", "destino": "I", "label": ""}
        ],
        "tabla_pasos": [
            {"Paso": 1, "Etapa": "Carrusel Automatizado", "Actividad": "Entrega automática de placas RPi 5 8GB y SSD 1TB M.2", "Equipo / Responsable": "Carrusel Vertical + 2 Operadores", "Tiempo (min)": 2.0},
            {"Paso": 2, "Etapa": "Clonación NVMe/MicroSD", "Actividad": "Flasheo simultáneo de sistema Linux y servidor local", "Equipo / Responsable": "2 Ingenieros + Clonadora 16 puertos", "Tiempo (min)": 3.5},
            {"Paso": 3, "Etapa": "SMT Yamaha + Nitrógeno", "Actividad": "Ensamble a 20,000 CPH y reflujo en atmósfera de N2", "Equipo / Responsable": "Yamaha YRM20 + Horno 8 Zonas N2", "Tiempo (min)": 2.0},
            {"Paso": 4, "Etapa": "Integración PCIe y Scripts", "Actividad": "Montar SSD 1TB M.2, fuente dedicada y scripts por red", "Equipo / Responsable": "Técnicos + Red Automatizada", "Tiempo (min)": 3.0},
            {"Paso": 5, "Etapa": "Inspección 3D Rayos-X", "Actividad": "Escaneo automático en banda transportadora sin detener línea", "Equipo / Responsable": "Sistema Rayos-X / AOI 3D", "Tiempo (min)": 1.5},
            {"Paso": 6, "Etapa": "Bodega Automatizada", "Actividad": "Estibado y registro directo en ERP como lote terminado", "Equipo / Responsable": "Banda + Almacén Inteligente", "Tiempo (min)": 2.5}
        ]
    }
}

# 1.9 Matriz de Consumo Eléctrico Diferenciada por Línea de Presupuesto
db_consumo_electrico = [
    {"equipo": "Maquinaria SMT Pick & Place", "linea": "General / Planta", "potencia_kw": 1.50, "horas_dia": 8.0, "consumo_mensual_kwh": 288.0, "kwh_p1": 115.0, "kwh_p2": 288.0, "kwh_p3": 672.0},
    {"equipo": "Horno de Reflujo Industrial", "linea": "General / Planta", "potencia_kw": 4.50, "horas_dia": 8.0, "consumo_mensual_kwh": 864.0, "kwh_p1": 288.0, "kwh_p2": 864.0, "kwh_p3": 1728.0},
    {"equipo": "Almacenamiento Seco ESD / Carrusel", "linea": "Almacén", "potencia_kw": 0.40, "horas_dia": 24.0, "consumo_mensual_kwh": 230.4, "kwh_p1": 48.0, "kwh_p2": 230.4, "kwh_p3": 576.0},
    {"equipo": "Impresoras 3D (Carcasas IP65)", "linea": "Manufactura", "potencia_kw": 0.75, "horas_dia": 24.0, "consumo_mensual_kwh": 432.0, "kwh_p1": 144.0, "kwh_p2": 432.0, "kwh_p3": 864.0},
    {"equipo": "Equipos de Cómputo y Bancos Linux", "linea": "Ingeniería (50 emp)", "potencia_kw": 3.50, "horas_dia": 8.0, "consumo_mensual_kwh": 672.0, "kwh_p1": 336.0, "kwh_p2": 672.0, "kwh_p3": 960.0},
    {"equipo": "Iluminación, Ventilación y Servicios", "linea": "Nave Industrial", "potencia_kw": 2.20, "horas_dia": 10.0, "consumo_mensual_kwh": 528.0, "kwh_p1": 310.0, "kwh_p2": 528.0, "kwh_p3": 880.0}
]

# ==============================================================================
# 2. FUNCIONES AUXILIARES (GEOCERCA HAVERSINE Y ESTILO EXCEL)
# ==============================================================================
def calcular_distancia_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    a = min(1.0, max(0.0, a))
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def estilizar_hoja_excel(ws, titulo_hoja: str):
    """Aplica diseño ejecutivo (colores, bordes y auto-ajuste de columnas) a una hoja de openpyxl."""
    header_fill = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid")
    header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    zebra_fill = PatternFill(start_color="F2F6FA", end_color="F2F6FA", fill_type="solid")
    thin_border = Border(
        left=Side(style="thin", color="D9D9D9"),
        right=Side(style="thin", color="D9D9D9"),
        top=Side(style="thin", color="D9D9D9"),
        bottom=Side(style="thin", color="D9D9D9")
    )

    for col_idx, cell in enumerate(ws[1], start=1):
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, max_row=ws.max_row), start=2):
        for cell in row:
            cell.border = thin_border
            if row_idx % 2 == 0:
                cell.fill = zebra_fill
            if isinstance(cell.value, (int, float)):
                header_text = str(ws.cell(row=1, column=cell.column).value or "").lower()
                if any(k in header_text for k in ["costo", "precio", "capex", "inv", "ingreso", "utilidad", "sueldo", "vpn", "flujo", "mxn"]):
                    cell.number_format = '$#,##0.00'
                elif "pct" in header_text or "%" in header_text:
                    cell.number_format = '0.0"%"'

    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            val_str = str(cell.value or "")
            if len(val_str) > max_len:
                max_len = len(val_str)
        ws.column_dimensions[col_letter].width = min(max(max_len + 4, 14), 48)
    ws.row_dimensions[1].height = 26

# ==============================================================================
# 3. MODELOS PYDANTIC
# ==============================================================================
class ValidatedModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False, str_strip_whitespace=True)

class LoginRequest(ValidatedModel):
    username: str = Field(min_length=1, max_length=60)
    password: str = Field(min_length=1, max_length=200)

class NegocioCreate(ValidatedModel):
    nombre: str = Field(default="AgTech Planta Texcoco Centro", min_length=1, max_length=160)
    ciudad_referencia: str = Field(default="Texcoco, Edo. Méx.", max_length=200)
    latitud: float = Field(default=19.5119, ge=-90, le=90)
    longitud: float = Field(default=-98.8829, ge=-180, le=180)
    radio_operacion_km: float = Field(default=5.0, gt=0, le=1000)
    presupuesto_seleccionado: str = "P2_OBJETIVO"
    inversion_inicial: float = Field(default=1775000.0, ge=0, le=1e12)
    costos_fijos_mensuales: float = Field(default=580000.0, ge=0, le=1e12)
    costo_variable_unitario: float = Field(default=2750.0, ge=0, le=1e9)
    precio_venta_unitario: float = Field(default=10500.0, gt=0, le=1e9)
    sector: str = Field(default="Secundario", min_length=1, max_length=100)
    giro: str = Field(default="Tecnología agrícola", min_length=1, max_length=100)
    actividades: str = Field(default="Ensamble, venta y mantenimiento de sensores para agricultura", max_length=500)

class ValidacionGeoRequest(ValidatedModel):
    negocio_id: str
    latitud_operador: float = Field(ge=-90, le=90)
    longitud_operador: float = Field(ge=-180, le=180)

class CotizacionComboRequest(ValidatedModel):
    placa_id: str
    almacenamiento_id: str
    sensores_ids: List[str] = Field(default_factory=list, max_length=10)
    incluir_chasis_fuente: bool = True
    cantidad_combos: int = Field(default=1, gt=0, le=10000, strict=True)

class VentaComboCreate(ValidatedModel):
    negocio_id: str
    latitud_operador: float = Field(ge=-90, le=90)
    longitud_operador: float = Field(ge=-180, le=180)
    # Campos heredados sólo para compatibilidad: nunca determinan importes o identidad.
    usuario_vendedor: str = ""
    tipo_venta: str = "Componentes"
    descripcion_items: str = ""
    cantidad: int = Field(gt=0, le=10000, strict=True)
    costo_total: float = 0
    precio_venta_total: float = 0
    metodo_pago: str = "Efectivo"
    componentes_ids: List[str] = Field(default_factory=list, max_length=50)
    idempotency_key: Optional[str] = Field(default=None, max_length=100)

class SimulacionInteractiva(ValidatedModel):
    unidades_vendidas_mes: int = Field(ge=0, le=1000000, strict=True)
    inversion_inicial: float = Field(ge=0, le=1e12)
    costos_fijos_mensuales: float = Field(ge=0, le=1e12)
    costo_variable_unitario: float = Field(ge=0, le=1e9)
    precio_venta_unitario: float = Field(gt=0, le=1e9)
    tasa_cetes: float = Field(default=11.0, ge=0, le=100)
    tasa_descuento: float = Field(default=15.0, ge=0, le=100)

class SolicitudDictamen(ValidatedModel):
    nombre_negocio: str
    unidades_vendidas: int = Field(ge=0)
    punto_equilibrio_uds: Optional[float] = None
    vpn: float
    tir: Optional[float] = None
    spread: Optional[float] = None
    estado_inversion: str

# ==============================================================================
# 4. ENDPOINTS: AUTENTICACIÓN Y ROLES (RBAC)
# ==============================================================================
@app.post("/auth/login", tags=["Seguridad y Roles"])
def iniciar_sesion(credenciales: LoginRequest):
    username = credenciales.username.lower()
    user = db_usuarios.get(username)
    if not user or not user.get("activo", True) or not verificar_password(credenciales.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos.")
    for key in list(db_sesiones):
        if db_sesiones[key]["expira"] <= time.time():
            del db_sesiones[key]
    token = secrets.token_urlsafe(36)
    db_sesiones[hashlib.sha256(token.encode()).hexdigest()] = {"username": username, "expira": time.time() + 8 * 3600}
    return {"autenticado": True, **usuario_publico(username, user), "access_token": token, "token_type": "bearer"}

# ==============================================================================
# 5. ENDPOINTS: SEDES Y GEOLOCALIZACIÓN
# ==============================================================================
@app.post("/negocios", tags=["Sedes y Geolocalización"])
def registrar_negocio(negocio: NegocioCreate):
    if negocio.presupuesto_seleccionado not in KIT_BOM:
        raise HTTPException(400, "Presupuesto desconocido")
    uid = uuid.uuid4().hex[:12]
    datos = negocio.model_dump()
    datos["id"] = uid
    db_negocios[uid] = datos
    return {"id_negocio": uid, "datos": db_negocios[uid]}

@app.get("/negocios", tags=["Sedes y Geolocalización"])
def listar_negocios():
    return db_negocios

@app.post("/negocios/validar-geocerca", tags=["Sedes y Geolocalización"])
def validar_operacion_geografica(req: ValidacionGeoRequest):
    if req.negocio_id not in db_negocios:
        raise HTTPException(status_code=404, detail="Sede no encontrada")
    
    sede = db_negocios[req.negocio_id]
    distancia = calcular_distancia_km(
        sede["latitud"], sede["longitud"],
        req.latitud_operador, req.longitud_operador
    )
    permitido = distancia <= sede["radio_operacion_km"]
    return {
        "operacion_permitida": permitido,
        "distancia_km": round(distancia, 2),
        "radio_maximo_km": sede["radio_operacion_km"],
        "mensaje": f"Ubicación declarada dentro de geocerca ({distancia:.2f} km). GPS simulado/manual." if permitido else f"⛔ BLOQUEO GEOGRÁFICO: Estás a {distancia:.2f} km de {sede['nombre']} (Máx: {sede['radio_operacion_km']} km)."
    }

# ==============================================================================
# 6. ENDPOINTS: PRESUPUESTOS TABULARES, INVENTARIO Y COMBOS
# ==============================================================================
@app.get("/ingenieria/presupuestos-tabulares", tags=["Ingeniería y Presupuestos"])
def obtener_presupuestos_tabulares():
    """Devuelve todas las tablas comparativas: Disparidad, BOM de Kits, Nómina OPEX, Multicriterio y Desglose por Presupuesto."""
    tabla_comparativa_disparidad = [
        {
            "ID": p["id_presupuesto"],
            "Nivel de Presupuesto": f"{p['icono']} {p['nombre_corto']}",
            "Arquitectura Base": p["arquitectura_base"],
            "Velocidad SMT": p["capacidad_planta"],
            "Inv. Maquinaria (MXN)": p["inversion_maquinaria_mxn"],
            "Inv. Almacenamiento (MXN)": p["inversion_almacenamiento_planta_mxn"],
            "Inv. Producción/Planta (MXN)": p["inversion_produccion_instalacion_mxn"],
            "Inv. Inventario Inicial (MXN)": p["costo_inventario_inicial_mxn"],
            "CAPEX Total (MXN)": p["capex_total_mxn"],
            "Costo Unitario Kit (MXN)": p["costo_produccion_kit_mxn"],
            "Precio Público Kit (MXN)": p["precio_publico_kit_mxn"],
            "Utilidad por Kit (MXN)": p["utilidad_unitaria_mxn"],
            "Margen Bruto (%)": p["margen_unitario_pct"],
            "Puntaje Multicriterio": p["calificacion_multicriterio"]
        }
        for p in db_presupuestos_tablas
    ]
    return {
        "resumen_disparidad": tabla_comparativa_disparidad,
        "tabla_bom_kits": db_bom_comparativa_kits,
        "tabla_nomina_opex": db_nomina_opex,
        "tabla_multicriterio": db_matriz_multicriterio,
        "detalle_presupuestos": db_presupuestos_tablas
    }

@app.get("/inventario/componentes", tags=["Inventario y Combos"])
def obtener_inventario_detallado():
    lista_tabular = []
    for cid, d in db_componentes.items():
        margen_comp = round(((d["precio_publico"] - d["costo_unitario"]) / d["precio_publico"]) * 100, 1)
        fila = {
            "Código": cid,
            "Categoría": f"{d['icono']} {d['categoria']}",
            "Componente": d["nombre"],
            "Especificaciones y Capacidades": d["especificaciones"],
            "Nivel Ligado": d["nivel_tag"],
            "Stock Actual": d["stock"],
            "Punto de Reorden": d["punto_reorden"],
            "Reorden": d["stock"] <= d["punto_reorden"],
            "Código de Barras": d["codigo_barras"],
            "Costo Unitario (MXN)": d["costo_unitario"],
            "Precio Público (MXN)": d["precio_publico"],
            "Margen (%)": margen_comp,
            "Valor Stock a Costo (MXN)": d["stock"] * d["costo_unitario"],
            "Valor Stock a Público (MXN)": d["stock"] * d["precio_publico"]
        }
        lista_tabular.append(fila)
    return {
        "catalogo_diccionario": db_componentes,
        "tabla_inventario": lista_tabular
    }

@app.post("/tpv/cotizar-combo", tags=["Inventario y Combos"])
def cotizar_combo_personalizado(combo: CotizacionComboRequest):
    ids = [combo.placa_id, combo.almacenamiento_id] + combo.sensores_ids
    if combo.incluir_chasis_fuente:
        ids.append("FUENTE_CHASIS")
    validar_combo(ids)
    items = [db_componentes[cid] for cid in ids]
    costo = dinero(sum(i["costo_unitario"] for i in items))
    regular = dinero(sum(i["precio_publico"] for i in items))
    descuento = 0.08 if len(ids) >= 4 else 0
    precio = dinero(regular * (1 - descuento))
    subtotal = dinero(precio * combo.cantidad_combos)
    iva = dinero(subtotal * db_config["iva_tasa"])
    return {
        "descripcion_combo": " + ".join(i["nombre"] for i in items),
        "componentes_ids": ids, "componentes_incluidos": items,
        "tabla_desglose_combo": [{"Categoría":i["categoria"],"Componente Elegido":i["nombre"],"Especificaciones":i["especificaciones"],"Costo Prod. (MXN)":i["costo_unitario"],"Precio Público (MXN)":i["precio_publico"]} for i in items],
        "cantidad_combos": combo.cantidad_combos, "costo_produccion_unitario": costo,
        "precio_publico_regular_unitario": regular, "descuento_combo_pct": descuento * 100,
        "ahorro_cliente_total": dinero((regular-precio)*combo.cantidad_combos),
        "precio_publico_final_unitario": precio, "costo_total_lote": dinero(costo*combo.cantidad_combos),
        "precio_total_cliente": subtotal, "utilidad_bruta_total": dinero((precio-costo)*combo.cantidad_combos),
        "subtotal":subtotal,"iva":iva,"total":dinero(subtotal+iva),"iva_tasa":db_config["iva_tasa"],
        "stock_disponible_combos": min(i["stock"] for i in items),
        "nota_precios":"Precios netos; IVA simulado agregado al subtotal."
    }

def calcular_cotizacion_venta(venta: VentaComboCreate):
    """Calcula importes y disponibilidad sin reservar ni modificar existencias."""
    sede = db_negocios.get(venta.negocio_id)
    if not sede:
        raise HTTPException(404,"Sede no encontrada")
    tipo = venta.tipo_venta.lower()
    descuento = 0.0
    if tipo in ("estándar","estandar","kit estándar","kit estandar"):
        ids = KIT_BOM[sede["presupuesto_seleccionado"]]
        precio = sede["precio_venta_unitario"]
    elif tipo in ("combo","combo personalizado"):
        ids = venta.componentes_ids
        validar_combo(ids)
        descuento = 0.08 if len(ids)>=4 else 0.0
        precio = dinero(sum(db_componentes[i]["precio_publico"] for i in ids) * (1-descuento))
    elif tipo in ("componentes","refacción","refaccion"):
        ids = venta.componentes_ids
        if not ids or any(i not in db_componentes for i in ids):
            raise HTTPException(400,"Seleccione componentes válidos por código.")
        precio = dinero(sum(db_componentes[i]["precio_publico"] for i in ids))
    else:
        raise HTTPException(400,"Tipo de venta desconocido")
    if venta.metodo_pago.lower() not in ("efectivo","tarjeta","transferencia"):
        raise HTTPException(400,"Método de pago inválido")
    cantidades = Counter(ids)
    disponibles = min(db_componentes[cid]["stock"] // veces for cid, veces in cantidades.items())
    faltantes = [{"componente_id": cid, "nombre": db_componentes[cid]["nombre"],
                  "requerido": veces * venta.cantidad, "disponible": db_componentes[cid]["stock"]}
                 for cid, veces in cantidades.items() if db_componentes[cid]["stock"] < veces * venta.cantidad]
    costo = dinero(sum(db_componentes[cid]["costo_unitario"] for cid in ids) * venta.cantidad)
    subtotal = dinero(precio * venta.cantidad)
    iva = dinero(subtotal*db_config["iva_tasa"])
    detalle = [{"componente_id":cid,"nombre":db_componentes[cid]["nombre"],"cantidad":n*venta.cantidad,
                "costo_unitario":db_componentes[cid]["costo_unitario"],"precio_catalogo":db_componentes[cid]["precio_publico"]} for cid,n in cantidades.items()]
    return {"negocio_id":venta.negocio_id,"tipo_venta":venta.tipo_venta,
            "item":" + ".join(db_componentes[i]["nombre"] for i in ids),
            "cantidad":venta.cantidad,"componentes_ids":list(ids),"precio_unitario":dinero(precio),
            "subtotal":subtotal,"iva":iva,"iva_tasa":db_config["iva_tasa"],"total":dinero(subtotal+iva),
            "costo_mercancia":costo,"utilidad_bruta":dinero(subtotal-costo),"descuento_pct":descuento*100,
            "unidades_disponibles":disponibles,"stock_suficiente":not faltantes,"faltantes":faltantes,
            "detalle":detalle,"nota":"Cotización con precios y existencias actuales; se verifican de nuevo al registrar la venta."}


@app.post("/tpv/cotizar-venta", tags=["Inventario y Combos"])
def cotizar_venta(venta: VentaComboCreate):
    return calcular_cotizacion_venta(venta)


@app.post("/tpv/venta", tags=["Inventario y Combos"])
def registrar_venta(venta: VentaComboCreate, request: Request):
    sede = db_negocios.get(venta.negocio_id)
    if not sede:
        raise HTTPException(404,"Sede no encontrada")
    username = request.state.usuario["username"]
    if venta.idempotency_key:
        anterior = next((v for v in db_ventas if v.get("idempotency_key")==venta.idempotency_key and v["vendedor"]==username),None)
        if anterior:
            return {"mensaje":"Venta ya registrada; no se duplicó el cobro.","ticket":anterior}
    distancia = calcular_distancia_km(sede["latitud"],sede["longitud"],venta.latitud_operador,venta.longitud_operador)
    if distancia > sede["radio_operacion_km"]:
        raise HTTPException(403,"Operación fuera de la geocerca. Coordenadas declaradas/simuladas.")
    cotizacion = calcular_cotizacion_venta(venta)
    if not cotizacion["stock_suficiente"]:
        raise HTTPException(409,f"Stock insuficiente: {cotizacion['faltantes'][0]['nombre']}")
    ids = cotizacion["componentes_ids"]
    cantidades = Counter(ids)
    subtotal, iva, costo = cotizacion["subtotal"], cotizacion["iva"], cotizacion["costo_mercancia"]
    folio = uuid.uuid4().hex[:12].upper()
    registro = {"folio":folio,"fecha":ahora(),"negocio_id":venta.negocio_id,"nombre_sede":sede["nombre"],
        "vendedor":username,"tipo_venta":venta.tipo_venta,"item":cotizacion["item"],
        "cantidad":venta.cantidad,"metodo_pago":venta.metodo_pago.capitalize(),"precio_unitario":cotizacion["precio_unitario"],
        "ingreso_bruto":subtotal,"subtotal":subtotal,"iva":iva,"iva_tasa":db_config["iva_tasa"],"total":dinero(subtotal+iva),
        "costo_mercancia":costo,"utilidad_bruta":dinero(subtotal-costo),"distancia_operacion_km":round(distancia,2),
        "detalle":cotizacion["detalle"],"idempotency_key":venta.idempotency_key,"modo_pago":"Simulación: no se procesa ningún cobro bancario"}
    for cid,n in cantidades.items():
        db_componentes[cid]["stock"] -= n*venta.cantidad
        registrar_movimiento(cid,-n*venta.cantidad,"Venta "+folio,username)
    db_ventas.append(registro)
    return {"mensaje":"Venta registrada, inventario descontado y ticket generado.","ticket":registro}

@app.get("/ventas/historial/{negocio_id}", tags=["Inventario y Combos"])
def obtener_ventas_base(negocio_id: str):
    if negocio_id not in db_negocios:
        raise HTTPException(status_code=404, detail="Negocio no encontrado")
    
    ventas_sucursal = [v for v in db_ventas if v["negocio_id"] == negocio_id]
    unidades_kits = sum(v["cantidad"] for v in ventas_sucursal)
    
    return {
        "unidades_vendidas_tpv": unidades_kits,
        "historial_detallado": ventas_sucursal
    }

# ==============================================================================
# 7. ENDPOINTS: SIMULADOR, IA Y FLUJO DINÁMICO DE INGENIERÍA
# ==============================================================================
@app.post("/analisis/simulador", tags=["Análisis Financiero"])
def simular_graficas(sim: SimulacionInteractiva):
    ingresos = sim.unidades_vendidas_mes * sim.precio_venta_unitario
    costos_var = sim.unidades_vendidas_mes * sim.costo_variable_unitario
    margen_bruto = ingresos - costos_var
    flujo_mensual = margen_bruto - sim.costos_fijos_mensuales
    contribucion = sim.precio_venta_unitario - sim.costo_variable_unitario
    pe = sim.costos_fijos_mensuales / contribucion if contribucion > 0 else None
    avance = sim.unidades_vendidas_mes / pe * 100 if pe and pe > 0 else 0
    margen = margen_bruto / ingresos * 100 if ingresos else 0
    flujos = [-sim.inversion_inicial] + [flujo_mensual*12]*3
    vpn = float(npf.npv(sim.tasa_descuento/100,flujos))
    tir_raw = float(npf.irr(flujos)) if sim.inversion_inicial>0 and flujo_mensual>0 else float("nan")
    tir = round(tir_raw*100,2) if math.isfinite(tir_raw) else None
    spread = round(tir-sim.tasa_cetes,2) if tir is not None else None
    estado = "Sin TIR definida" if tir is None else ("Supera referencia simulada" if spread>0 else "Riesgo financiero")
    return {"indicadores_duros":{"unidades_simuladas":sim.unidades_vendidas_mes,"punto_equilibrio_uds":round(pe,2) if pe is not None else None,
        "flujo_caja_mensual":dinero(flujo_mensual),"vpn":dinero(vpn),"van":dinero(vpn),"tir":tir,"spread_cetes":spread,"estado":estado,
        "margen_bruto_pct":round(margen,2),"roi_anual_pct":round(flujo_mensual*12/sim.inversion_inicial*100,2) if sim.inversion_inicial>0 else None,
        "recuperacion_meses":round(sim.inversion_inicial/flujo_mensual,2) if flujo_mensual>0 else None},
        "datos_graficas":{"barras":{"categorias":["Ingresos","C. Variables","C. Fijos"],"valores":[ingresos,costos_var,sim.costos_fijos_mensuales]},
        "radar":{"categorias":["TIR (%)","Referencia (%)","Margen Bruto (%)","Avance Equilibrio (%)"],"valores":[min(max(tir or 0,0),100),sim.tasa_cetes,margen,min(avance,100)]}},
        "supuestos":{"horizonte_anios":3,"flujos_anuales":flujos,"precios":"Netos de IVA","referencia":"Tasa introducida por usuario; no es cotización CETES en tiempo real","modelo":"Escenario constante, sin financiamiento, depreciación, ISR ni valor residual"},
        "advertencias":(["No existe punto de equilibrio finito cuando el precio no supera el costo variable."] if pe is None else []) + (["La TIR no está definida para estos flujos."] if tir is None else [])}

@app.post("/analisis/dictamen", tags=["Análisis Financiero"])
def generar_dictamen(datos: SolicitudDictamen):
    equilibrio = "No existe punto de equilibrio finito." if datos.punto_equilibrio_uds is None else f"Meta: {datos.unidades_vendidas} unidades; equilibrio: {datos.punto_equilibrio_uds:,.2f} unidades."
    tir_text = "No definida" if datos.tir is None else f"{datos.tir:,.2f}% anual"
    viable = datos.vpn > 0 and datos.tir is not None and (datos.spread or 0)>0
    return {"dictamen_ia":f"### Dictamen automático local — escenario simulado\n{equilibrio}\n\nVAN a 3 años: MXN {datos.vpn:,.2f}. TIR: {tir_text}.\n\n**Resultado: {'viable bajo los supuestos introducidos' if viable else 'revisar precio, costos y volumen antes de invertir'}.**\n\n- Comparar el volumen requerido con la capacidad de producción.\n- Validar costos y demanda con datos reales antes de una decisión.\n\nGenerado por reglas transparentes, sin IA externa ni datos de mercado actuales.","fuente":"Motor de reglas local","simulado":True}

@app.get("/ingenieria/flujo-produccion", tags=["Ingeniería y Presupuestos"])
def obtener_diagrama_flujo(presupuesto_id: str = Query(default="P2_OBJETIVO", description="ID del presupuesto: P1_ECONOMICO, P2_OBJETIVO o P3_PREMIUM")):
    """Devuelve el diagrama de flujo específico según la línea de presupuesto seleccionada, además del diccionario con los 3 flujos."""
    flujo_elegido = db_flujos_por_presupuesto.get(presupuesto_id, db_flujos_por_presupuesto["P2_OBJETIVO"])
    return {
        **flujo_elegido,
        "todos_los_flujos": db_flujos_por_presupuesto
    }

@app.get("/ingenieria/consumo-electrico", tags=["Ingeniería y Presupuestos"])
def obtener_consumo_electrico():
    return db_consumo_electrico

# ==============================================================================
# 8. ENDPOINT: EXPORTACIÓN INTEGRAL A EXCEL (10 PESTAÑAS CON TODAS LAS TABLAS)
# ==============================================================================
@app.get("/exportar/excel", tags=["Exportación Excel"])
def exportar_todo_a_excel():
    """Genera un libro de Excel profesional con 10 hojas que contienen todas las tablas del ERP."""
    output = io.BytesIO()
    
    res_pres = obtener_presupuestos_tabulares()
    
    # 1. Hoja Disparidad de Presupuestos
    df_1_disparidad = pd.DataFrame(res_pres["resumen_disparidad"])
    
    # 2. Hoja Comparativa BOM de Kits (Tabla 1 del Reporte)
    df_2_bom = pd.DataFrame(res_pres["tabla_bom_kits"])
    
    # 3, 4 y 5. Hojas individuales para cada Presupuesto (Maquinaria + Almacén + Inventario del Kit)
    p1_data = db_presupuestos_tablas[0]
    df_3_p1 = pd.concat([
        pd.DataFrame(p1_data["tabla_maquinaria_y_produccion"]),
        pd.DataFrame([{"Categoría": "---", "Concepto": "DESGLOSE DE INVENTARIO INICIAL DEL KIT P1 (ESP32)", "Especificación / Capacidad": f"Lote de {p1_data['lote_inventario_inicial_uds']} Kits", "Costo Total (MXN)": p1_data["costo_inventario_inicial_mxn"]}]),
        pd.DataFrame(p1_data["tabla_inventario_kit"]).rename(columns={"Componente del Kit": "Concepto", "Capacidad / Especificación": "Especificación / Capacidad", "Costo Lote Inicial (MXN)": "Costo Total (MXN)"})
    ], ignore_index=True)

    p2_data = db_presupuestos_tablas[1]
    df_4_p2 = pd.concat([
        pd.DataFrame(p2_data["tabla_maquinaria_y_produccion"]),
        pd.DataFrame([{"Categoría": "---", "Concepto": "DESGLOSE DE INVENTARIO INICIAL DEL KIT P2 (RADXA)", "Especificación / Capacidad": f"Lote de {p2_data['lote_inventario_inicial_uds']} Kits", "Costo Total (MXN)": p2_data["costo_inventario_inicial_mxn"]}]),
        pd.DataFrame(p2_data["tabla_inventario_kit"]).rename(columns={"Componente del Kit": "Concepto", "Capacidad / Especificación": "Especificación / Capacidad", "Costo Lote Inicial (MXN)": "Costo Total (MXN)"})
    ], ignore_index=True)

    p3_data = db_presupuestos_tablas[2]
    df_5_p3 = pd.concat([
        pd.DataFrame(p3_data["tabla_maquinaria_y_produccion"]),
        pd.DataFrame([{"Categoría": "---", "Concepto": "DESGLOSE DE INVENTARIO INICIAL DEL KIT P3 (RASPBERRY PI 5)", "Especificación / Capacidad": f"Lote de {p3_data['lote_inventario_inicial_uds']} Kits", "Costo Total (MXN)": p3_data["costo_inventario_inicial_mxn"]}]),
        pd.DataFrame(p3_data["tabla_inventario_kit"]).rename(columns={"Componente del Kit": "Concepto", "Capacidad / Especificación": "Especificación / Capacidad", "Costo Lote Inicial (MXN)": "Costo Total (MXN)"})
    ], ignore_index=True)

    # 6. Hoja Catálogo General de Componentes y Precios para Combos
    df_6_inventario = pd.DataFrame(obtener_inventario_detallado()["tabla_inventario"])

    # 7. Hoja de los 3 Diagramas de Flujo de Producción (Pasos y Tiempos por Línea)
    filas_flujos = []
    for k_id, f_obj in db_flujos_por_presupuesto.items():
        for paso in f_obj["tabla_pasos"]:
            filas_flujos.append({
                "Línea de Presupuesto": f_obj["titulo"],
                "Velocidad SMT": f_obj["velocidad_smt"],
                "Tiempo Ciclo Total (min)": f_obj["tiempo_total_optimo_min"],
                **paso
            })
    df_7_flujos = pd.DataFrame(filas_flujos)

    # 8. Hoja Nómina Mensual ($580k), Matriz Multicriterio y Consumo Eléctrico (kW/h)
    df_8_nomina = pd.DataFrame(db_nomina_opex)
    df_8_energia = pd.DataFrame(db_consumo_electrico)
    df_8_multi = pd.DataFrame(db_matriz_multicriterio)

    # 9. Hoja Sedes Registradas + Simulación Financiera Automática por Sede
    if db_negocios:
        filas_sedes_sim = []
        for s_id, s in db_negocios.items():
            uds_vta = sum(v["cantidad"] for v in db_ventas if v["negocio_id"] == s_id)
            mes_actual = ahora()[:7]
            uds_proy = sum(v["cantidad"] for v in db_ventas if v["negocio_id"]==s_id and v["fecha"].startswith(mes_actual))
            sim_res = simular_graficas(SimulacionInteractiva(
                unidades_vendidas_mes=uds_proy,
                inversion_inicial=s["inversion_inicial"],
                costos_fijos_mensuales=s["costos_fijos_mensuales"],
                costo_variable_unitario=s["costo_variable_unitario"],
                precio_venta_unitario=s["precio_venta_unitario"]
            ))["indicadores_duros"]
            filas_sedes_sim.append({
                "ID Sede": s["id"],
                "Nombre Sede": s["nombre"],
                "Ciudad / Referencia": s.get("ciudad_referencia", "Texcoco"),
                "Latitud GPS": s["latitud"],
                "Longitud GPS": s["longitud"],
                "Geocerca (km)": s.get("radio_operacion_km", 5.0),
                "Presupuesto Asignado": s.get("presupuesto_seleccionado", "P2_OBJETIVO"),
                "CAPEX Inicial (MXN)": s["inversion_inicial"],
                "Costos Fijos Mes (MXN)": s["costos_fijos_mensuales"],
                "Costo Unit. Kit (MXN)": s["costo_variable_unitario"],
                "Precio Venta Kit (MXN)": s["precio_venta_unitario"],
                "Ventas acumuladas TPV (Uds)": uds_vta,
                "Unidades mensuales asumidas en proyección": uds_proy,
                "Base de proyección": f"Volumen registrado en {mes_actual}, repetido durante 3 años; supuesto, no pronóstico",
                "Punto Equilibrio (Uds)": sim_res["punto_equilibrio_uds"],
                "Flujo Mensual Simulado (MXN)": sim_res["flujo_caja_mensual"],
                "VPN 3 Años (MXN)": sim_res["vpn"],
                "TIR Anual (%)": sim_res["tir"],
                "Estado Financiero": sim_res["estado"]
            })
        df_9_sedes = pd.DataFrame(filas_sedes_sim)
    else:
        df_9_sedes = pd.DataFrame([{"Mensaje": "Aún no se han registrado sedes en la sesión actual."}])

    # 10. Hoja Historial de Ventas y Combos
    df_10_ventas = pd.DataFrame(db_ventas) if db_ventas else pd.DataFrame([{"Mensaje": "Aún no se han registrado ventas en el TPV."}])

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df_1_disparidad.to_excel(writer, sheet_name="1_Disparidad_Presupuestos", index=False)
        df_2_bom.to_excel(writer, sheet_name="2_Comparativa_BOM_Kits", index=False)
        df_3_p1.to_excel(writer, sheet_name="3_Presupuesto1_ESP32", index=False)
        df_4_p2.to_excel(writer, sheet_name="4_Presupuesto2_Radxa", index=False)
        df_5_p3.to_excel(writer, sheet_name="5_Presupuesto3_RPi5", index=False)
        df_6_inventario.to_excel(writer, sheet_name="6_Catalogo_Stock_Precios", index=False)
        df_7_flujos.to_excel(writer, sheet_name="7_Flujos_Produccion_SMT", index=False)
        df_8_nomina.to_excel(writer, sheet_name="8_Nomina_OPEX_580k", index=False)
        df_8_energia.to_excel(writer, sheet_name="9_Consumo_Electrico_kWh", index=False)
        df_8_multi.to_excel(writer, sheet_name="10_Matriz_Multicriterio", index=False)
        df_9_sedes.to_excel(writer, sheet_name="11_Sedes_y_Finanzas_GPS", index=False)
        df_10_ventas.to_excel(writer, sheet_name="12_Historial_Ventas_TPV", index=False)

        # Estilizar todas las hojas automáticamente
        for sheet_name, ws in writer.sheets.items():
            # Forzar cadenas como texto, incluso si el usuario escribió =,+,-,@.
            for row in ws.iter_rows():
                for cell in row:
                    if isinstance(cell.value, str) and cell.value.startswith(("=", "+", "-", "@")):
                        cell.data_type = "s"
            estilizar_hoja_excel(ws, sheet_name)

    output.seek(0)
    headers = {
        "Content-Disposition": 'attachment; filename="Reporte_Maestro_ERP_AgTech_Completo.xlsx"'
    }
    return StreamingResponse(
        output, 
        headers=headers, 
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )


# ==============================================================================
# Persistencia, permisos y módulos de operación añadidos para la evaluación.
# Los catálogos de ingeniería anteriores son presupuestos estimados; las ventas
# usan los costos actuales del catálogo operativo y guardan una copia histórica.
# ==============================================================================
DB_PATH = Path(os.environ.get("ERP_DB_PATH", str(Path(__file__).parent / "data" / "erp.sqlite3")))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)
_STATE_LOCK = threading.RLock()
AREAS = ["Dirección", "Ventas y caja", "Almacén", "Producción", "Finanzas", "Recursos humanos"]
ROLES = {
    "gerente": {"rol":"Gerente General","icono":"👔","permisos":["registrar_sede","tpv","simulador","ingenieria","exportar","inventario","usuarios","personal","reportes"]},
    "cajero": {"rol":"Cajero / Operador TPV","icono":"🛒","permisos":["tpv"]},
    "ingeniero": {"rol":"Ingeniero de Planta","icono":"⚙️","permisos":["simulador","ingenieria","exportar","inventario","reportes"]},
}
KIT_BOM = {
    "P1_ECONOMICO":["PLACA_ESP32","SEN_CONDUCT","SEN_DHT22","SEN_SUELO","FUENTE_CHASIS"],
    "P2_OBJETIVO":["PLACA_RADXA","ALM_EMMC","SEN_CONDUCT","SEN_DHT22","SEN_SUELO","FUENTE_CHASIS"],
    "P3_PREMIUM":["PLACA_RPI5","ALM_NVME","SEN_CONDUCT","SEN_DHT22","SEN_SUELO","FUENTE_CHASIS"],
}
db_movimientos = []
db_personal = {}
db_sesiones = {}
db_config = {"tipo_cambio_usd_mxn":20.0,"iva_tasa":0.16,"modo_demo":True,"fuente_tipo_cambio":"Supuesto manual de demostración; no cotización actual"}


def ahora():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def dinero(valor):
    return float(Decimal(str(valor)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 260000).hex()
    return f"pbkdf2_sha256$260000${salt}${digest}"


def verificar_password(password, encoded):
    try:
        _, rounds, salt, expected = encoded.split("$")
        actual = hashlib.pbkdf2_hmac("sha256",password.encode(),bytes.fromhex(salt),int(rounds)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError):
        return False


def usuario_publico(username, user):
    codigo = user.get("rol_codigo","cajero")
    return {"username":username,"nombre":user.get("nombre",username),"area":user.get("area","Ventas y caja"),
            "activo":user.get("activo",True),"rol_codigo":codigo,**ROLES[codigo],
            "descripcion_acceso":"Permisos verificados en el servidor para cada solicitud."}


def validar_combo(ids):
    if len(ids)!=len(set(ids)):
        raise HTTPException(400,"Un combo no admite componentes repetidos.")
    if any(cid not in db_componentes for cid in ids):
        raise HTTPException(400,"Componente inexistente.")
    categorias = Counter(db_componentes[cid]["categoria"] for cid in ids)
    if categorias["Placa Base"]!=1 or categorias["Almacenamiento"]!=1:
        raise HTTPException(400,"Un combo debe incluir exactamente una placa y un almacenamiento.")
    if any(c not in ("Placa Base","Almacenamiento","Sensor","Producción/Chasis") for c in categorias):
        raise HTTPException(400,"Categoría no válida para combo.")


def registrar_movimiento(cid, cantidad, motivo, usuario):
    db_movimientos.append({"id":uuid.uuid4().hex[:12],"fecha":ahora(),"componente_id":cid,"cantidad":cantidad,
        "motivo":motivo,"usuario":usuario,"stock_resultante":db_componentes[cid]["stock"]})


def _estado():
    return {"usuarios":db_usuarios,"negocios":db_negocios,"ventas":db_ventas,"componentes":db_componentes,
            "movimientos":db_movimientos,"personal":db_personal,"sesiones":db_sesiones,"configuracion":db_config}


def _cargar(state):
    for nombre,obj in [("usuarios",db_usuarios),("negocios",db_negocios),("ventas",db_ventas),("componentes",db_componentes),
                       ("movimientos",db_movimientos),("personal",db_personal),("sesiones",db_sesiones),("configuracion",db_config)]:
        obj.clear()
        if isinstance(obj,list):
            obj.extend(state[nombre])
        else:
            obj.update(state[nombre])


def _conexion():
    conn=sqlite3.connect(str(DB_PATH),timeout=30)
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _inicializar():
    with _STATE_LOCK, closing(_conexion()) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS erp_state (id INTEGER PRIMARY KEY CHECK(id=1), payload TEXT NOT NULL)")
        conn.execute("BEGIN IMMEDIATE")
        saved=conn.execute("SELECT payload FROM erp_state WHERE id=1").fetchone()
        if saved:
            _cargar(json.loads(saved[0]))
            conn.commit()
            return
        for codigo,user in db_usuarios.items():
            user["password_hash"]=hash_password(user.pop("password"))
            user.update({"rol_codigo":codigo,"activo":True,"nombre":codigo.title(),"area":"Dirección" if codigo=="gerente" else ("Ventas y caja" if codigo=="cajero" else "Producción")})
            user.update(ROLES[codigo])
        for n,(cid,producto) in enumerate(db_componentes.items(),1):
            producto.update({"codigo_barras":f"AGT{n:08d}","foto_url":"","punto_reorden":20,"moneda_origen":"MXN",
                             "costo_origen":producto["costo_unitario"],"gastos_importacion_unitarios":0.0})
        demo=NegocioCreate(nombre="AgTech Texcoco — sede de demostración").model_dump()
        demo["id"]="DEMO_TEXCOCO"
        db_negocios[demo["id"]]=demo
        conn.execute("INSERT INTO erp_state(id,payload) VALUES(1,?)",(json.dumps(_estado(),ensure_ascii=False,allow_nan=False),))
        conn.commit()


def _atomic_handler(fn):
    """Carga y guarda todo el estado en una sola transacción SQLite por operación.

    El bloqueo local impide carreras entre hilos; BEGIN IMMEDIATE serializa además
    procesos que compartan el mismo archivo. Una excepción revierte todos los cambios.
    """
    @functools.wraps(fn)
    def wrapped(*args,**kwargs):
        with _STATE_LOCK:
            conn=_conexion()
            original=None
            try:
                conn.execute("BEGIN IMMEDIATE")
                original=json.loads(conn.execute("SELECT payload FROM erp_state WHERE id=1").fetchone()[0])
                _cargar(original)
                result=fn(*args,**kwargs)
                conn.execute("UPDATE erp_state SET payload=? WHERE id=1",(json.dumps(_estado(),ensure_ascii=False,allow_nan=False),))
                conn.commit()
                return copy.deepcopy(result) if isinstance(result,(dict,list)) else result
            except Exception:
                conn.rollback()
                if original is not None:
                    _cargar(original)
                raise
            finally:
                conn.close()
    return wrapped


def _authenticate(token):
    # Lectura independiente; no retiene un bloqueo mientras se ejecuta la ruta.
    with closing(_conexion()) as conn:
        state=json.loads(conn.execute("SELECT payload FROM erp_state WHERE id=1").fetchone()[0])
    session=state["sesiones"].get(hashlib.sha256(token.encode()).hexdigest())
    if not session or session["expira"]<=time.time():
        return None
    user=state["usuarios"].get(session["username"])
    return usuario_publico(session["username"],user) if user and user.get("activo",True) else None


def permiso_ruta(path, method):
    if path.startswith("/usuarios"):
        return "usuarios"
    if path.startswith("/personal"):
        return "personal"
    if path.startswith("/exportar"):
        return "exportar"
    if path.startswith("/respaldo"):
        return "registrar_sede"
    if path.startswith("/ingenieria"):
        return "ingenieria"
    if path.startswith("/analisis/simulador") or path.startswith("/analisis/dictamen"):
        return "simulador"
    if path.startswith("/analisis"):
        return "reportes"
    if path.startswith("/tpv") or path.startswith("/ventas"):
        return "tpv"
    if path.startswith("/inventario") and method not in ("GET","HEAD"):
        return "inventario"
    if path=="/configuracion" and method!="GET":
        return "registrar_sede"
    if path=="/negocios" and method=="POST":
        return "registrar_sede"
    return None


@app.middleware("http")
async def autorizar(request: Request, call_next):
    if request.url.path in ("/health","/auth/login"):
        return await call_next(request)
    authorization=request.headers.get("authorization","")
    if not authorization.startswith("Bearer "):
        return JSONResponse(status_code=401,content={"detail":"Inicie sesión para acceder al sistema."})
    from anyio import to_thread
    user=await to_thread.run_sync(_authenticate,authorization[7:])
    if not user:
        return JSONResponse(status_code=401,content={"detail":"Sesión inválida o vencida."})
    required=permiso_ruta(request.url.path,request.method)
    acceso_lectura_ventas = request.method=="GET" and request.url.path.startswith("/ventas") and "reportes" in user["permisos"]
    if required and required not in user["permisos"] and not acceso_lectura_ventas:
        return JSONResponse(status_code=403,content={"detail":"Su rol no tiene permiso para esta operación."})
    request.state.usuario=user
    return await call_next(request)


class ProductoUpdate(ValidatedModel):
    costo_unitario: Optional[float] = Field(default=None, ge=0, le=1e9)
    precio_publico: Optional[float] = Field(default=None, gt=0, le=1e9)
    punto_reorden: Optional[int] = Field(default=None, ge=0, le=1000000, strict=True)
    foto_url: Optional[str] = Field(default=None, max_length=1500000)
    codigo_barras: Optional[str] = Field(default=None, min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    moneda_origen: Optional[str] = Field(default=None, pattern=r"^(MXN|USD)$")
    costo_origen: Optional[float] = Field(default=None, ge=0, le=1e9)
    gastos_importacion_unitarios: Optional[float] = Field(default=None, ge=0, le=1e9)


class MovimientoCreate(ValidatedModel):
    componente_id: str
    cantidad: int = Field(ge=-1000000,le=1000000,strict=True)
    motivo: str = Field(min_length=3,max_length=300)


class UsuarioCreate(ValidatedModel):
    username: str = Field(min_length=3,max_length=60,pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=8,max_length=200)
    rol: str = Field(pattern=r"^(gerente|cajero|ingeniero)$")
    nombre: str = Field(min_length=1,max_length=100)
    area: str = Field(min_length=1,max_length=100)


class UsuarioUpdate(ValidatedModel):
    activo: Optional[bool] = None
    rol: Optional[str] = Field(default=None,pattern=r"^(gerente|cajero|ingeniero)$")
    nombre: Optional[str] = Field(default=None,min_length=1,max_length=100)
    area: Optional[str] = Field(default=None,min_length=1,max_length=100)
    password: Optional[str] = Field(default=None,min_length=8,max_length=200)


class PersonalCreate(ValidatedModel):
    nombre: str = Field(min_length=1,max_length=100)
    puesto: str = Field(min_length=1,max_length=100)
    area: str = Field(min_length=1,max_length=100)
    salario_mensual: float = Field(ge=0,le=1e8)
    turno: str = Field(default="Diurno",min_length=1,max_length=60)
    activo: bool = True


class PersonalUpdate(ValidatedModel):
    nombre: Optional[str] = Field(default=None,min_length=1,max_length=100)
    puesto: Optional[str] = Field(default=None,min_length=1,max_length=100)
    area: Optional[str] = Field(default=None,min_length=1,max_length=100)
    salario_mensual: Optional[float] = Field(default=None,ge=0,le=1e8)
    turno: Optional[str] = Field(default=None,min_length=1,max_length=60)
    activo: Optional[bool] = None


class ConfiguracionUpdate(ValidatedModel):
    tipo_cambio_usd_mxn: Optional[float] = Field(default=None,gt=0,le=1000)
    iva_tasa: Optional[float] = Field(default=None,ge=0,le=1)


@app.get("/health")
def health():
    return {"status":"ok","modo":"demostracion","persistencia":"SQLite"}


@app.get("/auth/me")
def auth_me(request:Request):
    return request.state.usuario


@app.post("/auth/logout")
def logout(request:Request):
    token=request.headers["authorization"][7:]
    db_sesiones.pop(hashlib.sha256(token.encode()).hexdigest(),None)
    return {"mensaje":"Sesión cerrada"}


@app.get("/usuarios")
def listar_usuarios():
    return {"usuarios":[usuario_publico(k,v) for k,v in db_usuarios.items()],"roles":ROLES,"areas":AREAS}


@app.post("/usuarios",status_code=201)
def crear_usuario(datos:UsuarioCreate):
    username=datos.username.lower()
    if username in db_usuarios:
        raise HTTPException(409,"El nombre de usuario ya existe.")
    db_usuarios[username]={"nombre":datos.nombre,"area":datos.area,"rol_codigo":datos.rol,"activo":True,
                           "password_hash":hash_password(datos.password),**ROLES[datos.rol]}
    return usuario_publico(username,db_usuarios[username])


@app.put("/usuarios/{username}")
def editar_usuario(username:str,datos:UsuarioUpdate,request:Request):
    user=db_usuarios.get(username)
    if not user:
        raise HTTPException(404,"Usuario no encontrado")
    if username==request.state.usuario["username"] and (datos.activo is False or (datos.rol and datos.rol!="gerente")):
        raise HTTPException(400,"No puede desactivar ni quitar el rol a su propia sesión de administración.")
    updates=datos.model_dump(exclude_none=True)
    if "rol" in updates:
        user["rol_codigo"]=updates.pop("rol")
        user.update(ROLES[user["rol_codigo"]])
    if "password" in updates:
        user["password_hash"]=hash_password(updates.pop("password"))
        for key in list(db_sesiones):
            if db_sesiones[key]["username"]==username:
                del db_sesiones[key]
    user.update(updates)
    return usuario_publico(username,user)


@app.get("/personal")
def listar_personal():
    return {"personal":list(db_personal.values()),"areas":AREAS,"nomina_mensual":dinero(sum(p["salario_mensual"] for p in db_personal.values() if p["activo"])),
            "nota":"La nómina operativa se registra por separado del presupuesto fijo estimado; no se suma automáticamente al OPEX para evitar duplicarlo."}


@app.post("/personal",status_code=201)
def crear_personal(datos:PersonalCreate):
    uid=uuid.uuid4().hex[:12]
    db_personal[uid]={"id":uid,**datos.model_dump(),"fecha_alta":ahora()}
    return db_personal[uid]


@app.put("/personal/{uid}")
def actualizar_personal(uid:str,datos:PersonalUpdate):
    if uid not in db_personal:
        raise HTTPException(404,"Personal no encontrado")
    db_personal[uid].update(datos.model_dump(exclude_none=True))
    return db_personal[uid]


@app.put("/inventario/componentes/{cid}")
def editar_producto(cid:str,datos:ProductoUpdate):
    if cid not in db_componentes:
        raise HTTPException(404,"Producto no encontrado")
    updates=datos.model_dump(exclude_none=True)
    barcode=updates.get("codigo_barras")
    if barcode and any(k!=cid and v["codigo_barras"]==barcode for k,v in db_componentes.items()):
        raise HTTPException(409,"Código de barras duplicado")
    foto=updates.get("foto_url","")
    if foto:
        if foto.startswith(("data:image/png;base64,","data:image/jpeg;base64,")):
            import base64
            from PIL import Image
            try:
                content=base64.b64decode(foto.split(",",1)[1],validate=True)
                if len(content)>1000000:
                    raise ValueError()
                with Image.open(io.BytesIO(content)) as uploaded:
                    expected = "PNG" if foto.startswith("data:image/png;") else "JPEG"
                    if uploaded.format != expected or uploaded.width * uploaded.height > 20000000:
                        raise ValueError()
                    uploaded.verify()
            except (ValueError, OSError, SyntaxError, Image.DecompressionBombError):
                raise HTTPException(400,"Foto inválida; use PNG o JPEG de máximo 1 MB y 20 megapíxeles.")
        elif not foto.startswith("https://"):
            raise HTTPException(400,"La foto debe ser PNG/JPEG o una URL HTTPS.")
    producto=db_componentes[cid]
    producto.update(updates)
    if producto["moneda_origen"]=="USD":
        producto["costo_unitario"]=dinero(producto["costo_origen"]*db_config["tipo_cambio_usd_mxn"]+producto["gastos_importacion_unitarios"])
    elif "costo_origen" in updates or "gastos_importacion_unitarios" in updates or "moneda_origen" in updates:
        producto["costo_unitario"]=dinero(producto["costo_origen"]+producto["gastos_importacion_unitarios"])
    elif "costo_unitario" in updates:
        producto["costo_origen"]=producto["costo_unitario"]
        producto["gastos_importacion_unitarios"]=0.0
    return {"componente_id":cid,**producto}


@app.post("/inventario/movimiento")
def mover_inventario(datos:MovimientoCreate,request:Request):
    producto=db_componentes.get(datos.componente_id)
    if not producto:
        raise HTTPException(404,"Componente no encontrado")
    if datos.cantidad==0:
        raise HTTPException(400,"La cantidad debe ser distinta de cero.")
    if producto["stock"]+datos.cantidad<0:
        raise HTTPException(409,"El movimiento dejaría inventario negativo.")
    producto["stock"]+=datos.cantidad
    registrar_movimiento(datos.componente_id,datos.cantidad,datos.motivo,request.state.usuario["username"])
    return {"mensaje":"Movimiento guardado","stock":producto["stock"],"movimiento":db_movimientos[-1]}


@app.get("/inventario/movimientos")
def movimientos():
    return {"movimientos":db_movimientos}


@app.get("/configuracion")
def configuracion():
    return db_config


@app.put("/configuracion")
def cambiar_configuracion(datos:ConfiguracionUpdate):
    db_config.update(datos.model_dump(exclude_none=True))
    for producto in db_componentes.values():
        if producto["moneda_origen"]=="USD":
            producto["costo_unitario"]=dinero(producto["costo_origen"]*db_config["tipo_cambio_usd_mxn"]+producto["gastos_importacion_unitarios"])
    return db_config


def buscar_venta(folio):
    venta=next((v for v in db_ventas if v["folio"]==folio),None)
    if not venta:
        raise HTTPException(404,"Venta no encontrada")
    return venta


def texto_ticket(v):
    detalle="\n".join(f"{d['cantidad']} x {d['nombre']}" for d in v["detalle"])
    return (f"ERP AGTECH — TICKET DE DEMOSTRACIÓN\n{v['nombre_sede']}\nFolio: {v['folio']}\nFecha UTC: {v['fecha']}\n"
            f"Cajero: {v['vendedor']}\n{detalle}\nSubtotal neto: MXN {v['subtotal']:,.2f}\n"
            f"IVA ({v['iva_tasa']*100:g}%): MXN {v['iva']:,.2f}\nTOTAL: MXN {v['total']:,.2f}\n"
            f"Pago: {v['metodo_pago']} (simulado)\nSIN VALOR FISCAL. No sustituye un CFDI.\n")


@app.get("/ventas/{folio}/ticket")
def ticket(folio:str):
    venta=buscar_venta(folio)
    return {"texto":texto_ticket(venta),"ticket":venta,"simulado":True}


@app.get("/ventas/{folio}/factura")
def factura(folio:str):
    venta=buscar_venta(folio)
    return {"texto":"FACTURA DE DEMOSTRACIÓN — NO TIMBRADA\n"+texto_ticket(venta),
            "factura":{"folio":"SIM-"+folio,"fecha":venta["fecha"],"emisor":"AgTech Demo","receptor":"Público de demostración",
                       "conceptos":venta["detalle"],"subtotal":venta["subtotal"],"iva":venta["iva"],"total":venta["total"],
                       "moneda":"MXN","estado":"Simulada, sin valor fiscal; sin UUID SAT"},"simulado":True}


@app.get("/analisis/recomendaciones/{negocio_id}")
def recomendaciones(negocio_id:str):
    sede=db_negocios.get(negocio_id)
    if not sede:
        raise HTTPException(404,"Sede no encontrada")
    cerca=calcular_distancia_km(sede["latitud"],sede["longitud"],19.5119,-98.8829)<100
    preferidos=["SEN_SUELO","SEN_CONDUCT","SEN_DHT22"] if cerca else ["SEN_DHT22","PLACA_ESP32","SEN_SUELO"]
    recomendaciones=[]
    for cid,p in db_componentes.items():
        if p["stock"]<=p["punto_reorden"] or cid in preferidos:
            motivo="Existencia en o bajo el punto de reorden." if p["stock"]<=p["punto_reorden"] else ("Escenario agrícola de demostración a menos de 100 km de Texcoco: priorizar monitoreo de suelo y riego." if cerca else "Escenario general de demostración: priorizar medición de clima y monitoreo remoto.")
            recomendaciones.append({"producto_id":cid,"producto":p["nombre"],"motivo":motivo,"cantidad_sugerida":max(0,p["punto_reorden"]*2-p["stock"])})
    return {"recomendaciones":recomendaciones,"fuente":"Reglas geográficas simuladas + inventario real registrado. No utiliza clima, proveedores ni mercado en tiempo real.",
            "sector":sede["sector"],"giro":sede["giro"],"actividades":sede["actividades"],"coordenadas":{"latitud":sede["latitud"],"longitud":sede["longitud"]}}


@app.get("/analisis/reportes/{negocio_id}")
def reportes(negocio_id:str):
    if negocio_id not in db_negocios:
        raise HTTPException(404,"Sede no encontrada")
    ventas=[v for v in db_ventas if v["negocio_id"]==negocio_id]
    subtotal=dinero(sum(v["subtotal"] for v in ventas))
    costo=dinero(sum(v["costo_mercancia"] for v in ventas))
    series=defaultdict(lambda:{"ventas_netas":0,"costo_ventas":0,"utilidad_bruta":0,"unidades":0})
    cajeros=defaultdict(float)
    for venta in ventas:
        mes=venta["fecha"][:7]
        series[mes]["ventas_netas"]+=venta["subtotal"]
        series[mes]["costo_ventas"]+=venta["costo_mercancia"]
        series[mes]["utilidad_bruta"]+=venta["utilidad_bruta"]
        series[mes]["unidades"]+=venta["cantidad"]
        cajeros[venta["vendedor"]]+=venta["subtotal"]
    indicadores={"ventas_netas":subtotal,"iva_cobrado":dinero(sum(v["iva"] for v in ventas)),"total_cobrado":dinero(sum(v["total"] for v in ventas)),
        "costo_ventas":costo,"utilidad_bruta":dinero(subtotal-costo),"margen_bruto_pct":round((subtotal-costo)/subtotal*100,2) if subtotal else 0,
        "unidades":sum(v["cantidad"] for v in ventas),"valor_inventario_costo":dinero(sum(p["stock"]*p["costo_unitario"] for p in db_componentes.values())),
        "productos_reorden":sum(p["stock"]<=p["punto_reorden"] for p in db_componentes.values()),
        "ventas_por_cajero":[{"cajero":k,"ventas_netas":dinero(v)} for k,v in cajeros.items()]}
    return {"indicadores":indicadores,"series_mensuales":[{"mes":k,**{n:dinero(v) for n,v in row.items()}} for k,row in sorted(series.items())],
        "tendencias_simuladas":[{"mes":m,"indice_demanda":v} for m,v in zip(["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"],[80,85,102,120,135,130,115,110,104,100,94,90])],
        "fuente_tendencias":"Serie sintética de estacionalidad agrícola para demostrar gráficas; no es observación ni pronóstico real.",
        "limitaciones":["Inventario central compartido entre sedes; ventas y reportes separados por sede.","Importes de ventas netos de IVA; cobros bancarios y facturas son simulados.","El inventario se valora al costo actual; el costo de ventas conserva su valor histórico.","SQLite persiste en el disco del servidor; en alojamiento efímero descargue respaldos antes de reinicios o reconstrucciones."]}


@app.get("/respaldo")
def respaldo():
    return {"version":1,"fecha":ahora(),"negocios":db_negocios,"ventas":db_ventas,"componentes":db_componentes,
            "movimientos":db_movimientos,"personal":db_personal,"configuracion":db_config,
            "nota":"Respaldo operativo JSON sin contraseñas ni sesiones. Incluye datos de personal; guardar en un lugar privado."}


_inicializar()
# FastAPI ejecuta estas funciones síncronas en su pool. El RLock nunca se sostiene
# entre awaits del event loop. La firma original se conserva para la validación.
from fastapi.routing import APIRoute
for _route in app.routes:
    if isinstance(_route,APIRoute):
        _route.dependant.call=_atomic_handler(_route.endpoint)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app,host="127.0.0.1",port=int(os.environ.get("ERP_PORT","8000")))

