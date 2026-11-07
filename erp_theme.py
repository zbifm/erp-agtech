"""Identidad visual compartida por las pantallas de AgTech."""

import streamlit as st


_ESTILOS = """
<style>
/* Streamlit aplica color-scheme al contenedor de la aplicación. */
[data-testid="stApp"] {
    --ag-ink: light-dark(#163a30, #f1f2e6);
    --ag-muted: light-dark(#526457, #c1cebf);
    --ag-paper: light-dark(#f6f5ed, #12251f);
    --ag-surface: light-dark(#fffefa, #1b3029);
    --ag-line: light-dark(#cbd2c3, #41594b);
    --ag-forest: #123c32;
    --ag-lime: #d1e59d;
    --ag-action: light-dark(#245c46, #bfd985);
    --ag-action-hover: light-dark(#1a4a37, #d0e69e);
    --ag-on-action: light-dark(#fffefa, #17382a);
    --ag-shadow: 0 3px 12px rgba(15, 45, 33, .055);
    --ag-display: "Source Serif", Georgia, serif;
}
.stMainBlockContainer {
    max-width: 1420px;
    padding: 4.35rem clamp(1.4rem, 3.8vw, 4.25rem) 4rem;
}
.stMainBlockContainer h2, .stMainBlockContainer h3 {
    color: var(--ag-ink);
    letter-spacing: -.025em;
    line-height: 1.22;
}
.stMainBlockContainer h3 {font-size: clamp(1.25rem, 1.7vw, 1.55rem);}
.stMainBlockContainer [data-testid="stCaptionContainer"] {color: var(--ag-muted); opacity: 1;}

/* El mismo encabezado sitúa al usuario en cada área de trabajo. */
.agtech-hero {
    position: relative;
    isolation: isolate;
    overflow: hidden;
    padding: clamp(1.45rem, 3vw, 2.45rem);
    background: var(--ag-forest);
    color: #fffefa;
    border-radius: 1rem;
}
.agtech-hero h1 {
    margin: 0;
    padding: 0;
    font: 500 clamp(2.4rem, 4.5vw, 4rem)/1.07 var(--ag-display);
    letter-spacing: -.045em;
    color: inherit;
}
.agtech-hero p {
    max-width: 60rem;
    padding: 0;
    margin: .65rem 0 0;
    color: #e3ecde;
    line-height: 1.5;
}
.agtech-eyebrow {
    margin: 0 0 .45rem;
    font-size: .76rem;
    font-weight: 650;
    letter-spacing: .13em;
    text-transform: uppercase;
    color: var(--ag-lime);
}
.agtech-hero--compact {
    padding: .4rem 0 1.45rem;
    background: transparent;
    border-radius: 0;
    border-bottom: 1px solid var(--ag-line);
    color: var(--ag-ink);
}
.agtech-hero--compact .agtech-eyebrow {color: var(--ag-muted);}
.agtech-hero--compact h1 {font-size: clamp(2.4rem, 4.5vw, 3.6rem);}
.agtech-hero--compact p {color: var(--ag-muted);}
@media (min-width: 1100px) {
    .agtech-hero--compact {padding-right: 16%;}
    .agtech-hero--compact::after {
        content: "";
        position: absolute;
        z-index: -1;
        inset: 0 0 0 78%;
        opacity: .55;
        pointer-events: none;
        background: repeating-radial-gradient(ellipse at 100% 175%,
            transparent 0 15px, var(--ag-line) 16px 17px, transparent 18px 26px);
        mask-image: linear-gradient(90deg, transparent, #000);
    }
}

/* Señales de estado: el texto y el borde siguen siendo legibles en ambos temas. */
.agtech-insight, .agtech-empty {
    padding: 1rem 1.2rem;
    color: var(--ag-ink);
    border: 1px solid var(--ag-line);
    border-radius: .65rem;
}
.agtech-insight {
    --ag-signal: light-dark(#477286, #9ccad4);
    border-left: 4px solid var(--ag-signal);
    background: color-mix(in srgb, var(--ag-signal) 8%, var(--ag-surface));
}
.agtech-insight--success {--ag-signal: light-dark(#4d7156, #a3cba8);}
.agtech-insight--warning {--ag-signal: light-dark(#a26824, #e6bf71);}
.agtech-insight strong, .agtech-empty strong {
    display: block;
    font-size: 1.05rem;
    line-height: 1.35;
}
.agtech-insight p, .agtech-empty p {margin: .25rem 0 0; line-height: 1.5;}
.agtech-empty {background: var(--ag-surface); border-style: dashed;}

/* La barra lateral mantiene el orden por grupos y resalta la página activa. */
[data-testid="stSidebar"] {border-right: 1px solid #365a4d;}
[data-testid="stSidebarUserContent"] {padding-top: .35rem;}
.agtech-brand {
    display: flex;
    align-items: center;
    gap: .65rem;
    margin-bottom: .25rem;
    font: 550 2.05rem/1.12 var(--ag-display);
    letter-spacing: -.055em;
    color: #fffdf0;
}
.agtech-brand-mark {position: relative; width: 1.8rem; height: 1.8rem; flex: none;}
.agtech-brand-mark::before, .agtech-brand-mark::after {
    position: absolute;
    content: "";
    width: .89rem;
    height: 1.28rem;
    border-radius: 0 83% 0 83%;
    background: var(--ag-lime);
}
.agtech-brand-mark::before {left: 0; top: .44rem;}
.agtech-brand-mark::after {left: .94rem; top: .04rem; transform: scaleX(-1);}
.st-key-navegacion_principal {gap: .16rem;}
.st-key-navegacion_principal .agtech-nav-group {
    margin: .38rem 0 0;
    padding: .35rem .62rem .12rem;
    color: #c0d2bf;
    font: 650 .72rem/1.25 "Source Sans", sans-serif;
    letter-spacing: .12em;
    text-transform: uppercase;
}
.st-key-navegacion_principal button {
    display: flex;
    justify-content: flex-start;
    text-align: left;
    min-height: 2.5rem;
    padding-inline: .75rem;
    border: 1px solid transparent;
    border-radius: .48rem;
    font-weight: 550;
}
.st-key-navegacion_principal button > div {justify-content: flex-start;}
.st-key-navegacion_principal button p {text-align: left;}
.st-key-navegacion_principal [data-testid="stBaseButton-tertiary"] {color: #f1f4e9;}
.st-key-navegacion_principal [data-testid="stBaseButton-tertiary"]:hover {
    background: #245143;
    color: white;
}
.st-key-navegacion_principal [data-testid="stBaseButton-primary"] {
    background: var(--ag-lime);
    border-color: var(--ag-lime);
    color: #17382a;
}
.st-key-navegacion_principal [data-testid="stBaseButton-primary"]:is(:hover, :active) {
    background: #e0efb5;
    border-color: #e0efb5;
    color: #17382a;
}
.st-key-navegacion_principal [data-testid="stBaseButton-primary"] p {color: inherit;}

/* Valores numéricos, cuadros de captura y pestañas comparten escala y espaciado. */
.stMainBlockContainer [data-testid="stMetric"] {
    height: 100%;
    padding: .92rem 1.05rem;
    border: 1px solid var(--ag-line);
    border-radius: .75rem;
    background: var(--ag-surface);
    box-shadow: var(--ag-shadow);
}
[data-testid="stMetricLabel"] {height: auto; min-height: 1.35rem; color: var(--ag-muted);}
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"], [data-testid="stMetricLabel"] p {
    white-space: normal; overflow: visible; text-overflow: clip;
}
[data-testid="stMetricValue"] {
    font-size: clamp(1.55rem, 2.5vw, 2.15rem);
    font-weight: 600;
    font-variant-numeric: tabular-nums;
    letter-spacing: -.04em;
    color: var(--ag-ink);
}
[data-testid="stMetricValue"] [data-testid="stMarkdownContainer"],
[data-testid="stMetricValue"] p {
    white-space: normal; overflow: visible; text-overflow: clip; overflow-wrap: anywhere;
}
.st-key-cotizacion_actual {background: var(--ag-surface);}
.stMainBlockContainer .st-key-cotizacion_actual [data-testid="stMetric"] {
    border: none; background: transparent; box-shadow: none; padding: 0;
}
.stMainBlockContainer [data-testid="stForm"] {
    background: var(--ag-surface);
    border-color: var(--ag-line);
    border-radius: .8rem;
}
.stMainBlockContainer [data-testid="stExpander"] details {
    background: var(--ag-surface);
    border-color: var(--ag-line);
    border-radius: .65rem;
}
.stMainBlockContainer [data-testid="stExpander"] summary {font-weight: 550;}
.stMainBlockContainer [data-testid="stWidgetLabel"] p {font-weight: 550;}
.stMainBlockContainer [data-testid="stDataFrame"] {border-radius: .58rem;}
.stMainBlockContainer [data-testid="stTable"] th {background: var(--ag-surface);}
.stMainBlockContainer .stTabs [role="tab"] {
    min-height: 2.7rem;
    padding-inline: .55rem;
    font-weight: 600;
}
.stMainBlockContainer .stTabs [role="tab"][aria-selected="true"] {color: var(--ag-ink);}
.stMainBlockContainer :is(.stButton, .stDownloadButton, .stFormSubmitButton, .stLinkButton) :is(button, a) {
    min-height: 2.6rem;
    font-weight: 600;
}
.stMainBlockContainer [data-testid^="stBaseButton-primary"]:not(:disabled) {
    background: var(--ag-action);
    border-color: var(--ag-action);
    color: var(--ag-on-action);
}
.stMainBlockContainer [data-testid^="stBaseButton-primary"]:not(:disabled):is(:hover, :active) {
    background: var(--ag-action-hover);
    border-color: var(--ag-action-hover);
    color: var(--ag-on-action);
}
.stMainBlockContainer [data-testid^="stBaseButton-primary"] p {color: inherit;}
.stMainBlockContainer :is(button, a, summary):focus-visible {
    outline: 3px solid light-dark(#527a3b, #d1e59d);
    outline-offset: 2px;
}
[data-testid="stSidebar"] :is(button, a, summary):focus-visible {
    outline: 3px solid #f4fadf;
    outline-offset: 2px;
}
@media (max-width: 640px) {
    .stMainBlockContainer {padding: 3.8rem 1rem 3rem;}
    .agtech-hero--compact {padding: .15rem 0 1rem;}
    .agtech-hero--compact h1 {font-size: 2.2rem;}
    .stMainBlockContainer [data-testid="stMetric"] {padding: .75rem .9rem;}
    .agtech-insight, .agtech-empty {padding: .8rem .95rem;}
}
</style>
"""


def aplicar_tema():
    """Inyecta solo estilos en el contenedor de eventos, sin ocupar una fila."""
    st.html(_ESTILOS)
