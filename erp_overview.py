"""Portada y encabezado del panel de inicio de AgTech."""

import base64
import html
from functools import lru_cache
from pathlib import Path

import streamlit as st


@lru_cache(maxsize=1)
def _imagen_campo():
    archivo = Path(__file__).with_name("assets") / "campo_agtech.webp"
    return base64.b64encode(archivo.read_bytes()).decode("ascii")


def estilos_inicio():
    st.html("""
    <style>
    .ag-cover {
        isolation: isolate;
        position: relative;
        overflow: hidden;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        box-sizing: border-box;
        background: #10372e;
        color: #fff;
        border: 1px solid #244d41;
        border-radius: 1.45rem;
    }
    .ag-cover::before {
        position: absolute;
        z-index: -1;
        inset: 0;
        content: "";
        background-image: linear-gradient(90deg, #0c322c 0%, #0d332a80 46%, transparent 78%), var(--campo);
        background-position: center, 63% center;
        background-size: cover;
    }
    .ag-cover--login {
        min-height: 29rem;
        padding: clamp(1.5rem, 3.4vw, 3.5rem);
    }
    .ag-cover .ag-wordmark {
        display: flex;
        align-items: center;
        gap: .65rem;
        margin: 0;
        color: #fff;
        font-size: 1.12rem;
        letter-spacing: -.015em;
        font-weight: 650;
    }
    .ag-cover h1 {
        padding: 0;
        margin: 0;
        color: #fbf8e9;
        font-family: var(--ag-display, Georgia, serif);
        font-size: clamp(3.25rem, 5.4vw, 6.25rem);
        font-weight: 400;
        letter-spacing: -.055em;
        line-height: .96;
    }
    .ag-cover--login .ag-cover__description {
        color: #f3f5e9;
        margin: 1rem 0 0;
        max-width: 24rem;
        font-size: clamp(1.01rem, 1.4vw, 1.2rem);
        line-height: 1.45;
        text-wrap: balance;
    }
    .ag-cover .ag-cover__credit {
        color: #e6ebce;
        margin: 0;
        font-size: .83rem;
        line-height: 1.4;
    }
    .ag-cover--home {
        min-height: 11rem;
        justify-content: center;
        gap: .85rem;
        padding: clamp(1.5rem, 2.7vw, 2.7rem);
    }
    .ag-cover--home::before {
        left: 32%;
        background-image: linear-gradient(90deg, #10372e, #10372e48 45%, transparent), var(--campo);
        background-position: center, right 61%;
    }
    .ag-cover--home h1 {font-size: clamp(2.5rem, 3.8vw, 4.4rem);}
    .ag-cover--home .ag-cover__branch {
        margin: 0;
        max-width: 69%;
        color: #fff;
        font-size: .96rem;
        line-height: 1.5;
        overflow-wrap: anywhere;
    }
    .ag-cover__branch b {color: #dcf2ad; font-size: .82rem; font-weight: 650; margin-right: .55rem;}
    .st-key-acceso_erp h2 {
        margin: 0;
        padding: 0;
        color: var(--ag-ink);
        font-family: var(--ag-display, Georgia, serif);
        font-size: clamp(2rem, 3.4vw, 3rem);
        font-weight: 400;
        letter-spacing: -.045em;
        line-height: 1.1;
    }
    .st-key-acceso_erp form {border: 0; padding: 0; background: transparent; box-shadow: none;}
    .st-key-acceso_erp [data-testid="stForm"] {border: 0; padding: 0; background: transparent; box-shadow: none;}
    .st-key-perfiles_demo [data-testid="stHorizontalBlock"] {flex-wrap: nowrap; gap: .45rem;}
    .st-key-perfiles_demo [data-testid="stColumn"] {width: auto; min-width: 0; flex: 1 1 0;}
    .st-key-perfiles_demo button {padding-inline: .35rem; min-height: 2.35rem;}
    .st-key-perfiles_demo button p {font-size: .88rem; white-space: normal;}
    .st-key-tareas_inicio [data-testid="stColumn"] {align-self: stretch;}
    .st-key-tareas_inicio [data-testid="stMarkdownContainer"] strong {font-size: 1.08rem;}
    .st-key-tareas_inicio [data-testid="stMarkdownContainer"] [class*="material-symbols"] {
        padding: .34rem;
        margin-right: .38rem;
        border-radius: .55rem;
        background: #e6eddd;
        color: #284c3e;
        vertical-align: middle;
    }
    @media (max-width: 850px) {
        .ag-cover--login {min-height: 27rem;}
    }
    @media (max-width: 640px) {
        .ag-cover--login {min-height: 15rem; gap: 1.1rem; padding: 1.3rem 1.45rem;}
        .ag-cover--login h1 {font-size: 3.1rem;}
        .ag-cover--login h1 br {display: none;}
        .ag-cover--login .ag-cover__description {max-width: 17rem; font-size: .95rem; margin: .45rem 0 0;}
        .ag-cover--home {min-height: 9rem; padding: 1.4rem;}
        .ag-cover--home .ag-cover__branch {max-width: 93%; text-shadow: 0 1px 4px #0b2b23;}
    }
    </style>
    """)


def portada_acceso():
    st.html(
        f"""<section class="ag-cover ag-cover--login" style="--campo:url('data:image/webp;base64,{_imagen_campo()}')">
        <div class="ag-wordmark"><span class="agtech-brand-mark" aria-hidden="true"></span>ERP AgTech</div>
        <div><h1>Gestión <br>agrícola</h1>
        <p class="ag-cover__description">Ventas, inventario y finanzas en un solo lugar.</p></div>
        <p class="ag-cover__credit">Universidad Autónoma Chapingo · Demostración académica</p>
        </section>"""
    )


def encabezado_inicio(sede):
    ubicacion = (
        f'<p class="ag-cover__branch"><b>Sede activa</b>{html.escape(sede["nombre"])}</p>'
        if sede else ""
    )
    st.html(
        f"""<header class="ag-cover ag-cover--home" style="--campo:url('data:image/webp;base64,{_imagen_campo()}')">
        <h1>Panel de inicio</h1>{ubicacion}</header>"""
    )


def elegir_perfil(usuario):
    st.session_state.acceso_usuario = usuario
    st.session_state.acceso_clave = "123"
