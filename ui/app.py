"""
automacao-juridica-trf1 — Interface Streamlit v4
Week Test Release

Uso:
    streamlit run ui/app.py
"""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import sys
import time
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.config import settings
from core.modelos import (
    ItemRelatorio, NivelConfianca, TipoDocumento, TERMOS_NEGOCIO,
)

# ============================================
# PAGE CONFIG
# ============================================

st.set_page_config(
    page_title="Classificador de Documentação Jurídica",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================
# DESIGN SYSTEM CSS
# ============================================

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Manrope:wght@300;400;500;600;700&family=Inter:wght@300;400;500;600&display=swap');

    :root {
        --surface: #131313;
        --surface-low: #1C1B1B;
        --surface-container: #20201F;
        --surface-high: #2A2A2A;
        --primary: #FFB783;
        --primary-container: #E67E22;
        --primary-muted: #D4700A;
        --on-surface: #E5E2E1;
        --on-surface-variant: #DCC1B1;
        --secondary: #C6C6C6;
        --outline-variant: #564337;
        --error: #F87171;
        --success: #4ADE80;
    }

    .stApp { background-color: var(--surface) !important; }
    #MainMenu, footer, .stDeployButton,
    [data-testid="stToolbar"],
    [data-testid="stDecoration"] { display: none !important; }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: var(--surface-low) !important;
        min-width: 260px !important;
        max-width: 260px !important;
        transform: none !important;
        visibility: visible !important;
        position: relative !important;
    }
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 24px !important;
        padding-left: 16px !important;
        padding-right: 16px !important;
    }
    /* Hide the collapse arrow button inside sidebar */
    [data-testid="stSidebar"] button[kind="header"],
    [data-testid="stSidebar"] [data-testid="stSidebarNavCollapseButton"],
    [data-testid="stSidebar"] .st-emotion-cache-1gwvy71,
    [data-testid="stSidebarCollapseButton"],
    [data-testid="collapsedControl"] {
        display: none !important;
        visibility: hidden !important;
        width: 0 !important;
        height: 0 !important;
        overflow: hidden !important;
    }

    /* Typography */
    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, sans-serif !important;
        color: var(--secondary) !important;
    }
    h1, h2, h3, h4, .stMarkdown h1, .stMarkdown h2, .stMarkdown h3 {
        font-family: 'Manrope', sans-serif !important;
        color: var(--on-surface) !important;
        font-weight: 600 !important;
    }

    /* Brand */
    .brand-title {
        font-family: 'Manrope', sans-serif;
        font-size: 15px;
        font-weight: 700;
        color: var(--on-surface);
        margin: 0;
        line-height: 1.3;
    }
    .brand-sub {
        font-family: 'Inter', sans-serif;
        font-size: 10px;
        font-weight: 500;
        letter-spacing: 0.15em;
        text-transform: uppercase;
        color: var(--primary-muted);
        margin: 0 0 32px 0;
    }

    /* Nav buttons override */
    [data-testid="stSidebar"] .stButton > button {
        background: transparent !important;
        border: none !important;
        color: var(--secondary) !important;
        font-family: 'Inter', sans-serif !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        text-align: left !important;
        padding: 10px 16px !important;
        border-radius: 6px !important;
        width: 100% !important;
        justify-content: flex-start !important;
    }
    [data-testid="stSidebar"] .stButton > button:hover {
        background: rgba(255, 183, 131, 0.06) !important;
        color: var(--on-surface) !important;
    }
    [data-testid="stSidebar"] .stButton > button:focus {
        box-shadow: none !important;
    }

    /* Active nav styling via wrapper div */
    .nav-active > div > button {
        background: rgba(255, 183, 131, 0.08) !important;
        color: var(--primary) !important;
        font-weight: 500 !important;
        border-left: 3px solid var(--primary) !important;
        border-radius: 0 6px 6px 0 !important;
    }

    /* Overline */
    .overline {
        font-family: 'Inter', sans-serif;
        font-size: 11px; font-weight: 500;
        letter-spacing: 0.15em; text-transform: uppercase;
        color: var(--primary-muted); margin: 0 0 6px 0;
    }
    .page-title {
        font-family: 'Manrope', sans-serif;
        font-size: 30px; font-weight: 700;
        color: var(--on-surface); margin: 0 0 4px 0; line-height: 1.1;
    }
    .page-sub {
        font-family: 'Inter', sans-serif;
        font-size: 14px; color: #777; margin: 0 0 32px 0;
    }

    /* Cards */
    .card {
        background: var(--surface-container);
        border-radius: 8px; padding: 24px; margin: 8px 0;
    }
    .card-accent {
        background: var(--surface-container);
        border-left: 3px solid var(--primary-muted);
        border-radius: 8px; padding: 24px; margin: 8px 0;
    }
    .card-empresa {
        background: var(--surface-container);
        border-top: 3px solid var(--primary-muted);
        border-radius: 8px; padding: 24px; margin: 8px 0 16px 0;
    }

    /* Metrics */
    .m-card {
        background: var(--surface-container);
        border-radius: 8px; padding: 20px 24px; text-align: left;
    }
    .m-card-hl {
        background: linear-gradient(135deg, rgba(230,126,34,0.15), rgba(255,183,131,0.08));
        border-radius: 8px; padding: 20px 24px; text-align: left;
    }
    .m-val {
        font-family: 'Manrope', sans-serif;
        font-size: 36px; font-weight: 300;
        color: var(--on-surface); margin: 0; line-height: 1;
    }
    .m-val-a {
        font-family: 'Manrope', sans-serif;
        font-size: 36px; font-weight: 300;
        color: var(--primary); margin: 0; line-height: 1;
    }
    .m-lbl {
        font-family: 'Inter', sans-serif;
        font-size: 11px; font-weight: 500;
        letter-spacing: 0.1em; text-transform: uppercase;
        color: #777; margin: 8px 0 0 0;
    }

    /* Pills */
    .p-ok { background: rgba(74,222,128,0.12); color: #4ADE80;
            padding: 3px 14px; border-radius: 20px; font-size: 12px;
            font-weight: 500; display: inline-block; }
    .p-auto { background: rgba(255,183,131,0.12); color: var(--primary);
              padding: 3px 14px; border-radius: 20px; font-size: 12px;
              font-weight: 500; display: inline-block; }
    .p-rev { background: rgba(248,113,113,0.12); color: #F87171;
             padding: 3px 14px; border-radius: 20px; font-size: 12px;
             font-weight: 500; display: inline-block; }

    /* Text extract */
    .t-ext {
        background: var(--surface-low); border-radius: 6px; padding: 20px;
        font-family: 'SF Mono','Fira Code','Consolas', monospace;
        font-size: 12.5px; color: var(--on-surface-variant);
        white-space: pre-wrap; max-height: 400px;
        overflow-y: auto; line-height: 1.7;
    }
    .sug-box {
        background: rgba(255,183,131,0.05);
        border-left: 2px solid var(--primary-muted);
        border-radius: 0 6px 6px 0; padding: 14px 18px;
        font-size: 13px; color: var(--on-surface-variant);
        line-height: 1.6; margin: 8px 0;
    }
    .rev-card {
        background: var(--surface-container);
        border-left: 3px solid #F87171;
        border-radius: 8px; padding: 20px 24px; margin: 16px 0;
    }
    .blk-warn {
        background: rgba(248,113,113,0.06);
        border-radius: 8px; padding: 20px 24px;
        color: var(--error); font-size: 14px; line-height: 1.5;
    }
    .sb-status {
        font-family: 'Inter', sans-serif; font-size: 12px;
        color: #666; line-height: 1.8;
    }

    /* Streamlit overrides */
    .stTextInput input {
        background: var(--surface-high) !important;
        border: none !important;
        border-bottom: 2px solid var(--outline-variant) !important;
        color: var(--on-surface) !important;
        border-radius: 4px 4px 0 0 !important;
    }
    .stTextInput input:focus {
        border-bottom-color: var(--primary) !important;
        box-shadow: none !important;
    }
    .stTextArea textarea {
        background: var(--surface-low) !important;
        border: none !important;
        color: var(--on-surface-variant) !important;
        font-family: 'SF Mono','Fira Code', monospace !important;
        font-size: 12px !important;
        border-radius: 6px !important;
    }
    .stSelectbox > div > div {
        background: var(--surface-high) !important;
        border: none !important;
        color: var(--on-surface) !important;
    }
    .stButton > button[kind="primary"] {
        background: linear-gradient(135deg, var(--primary), var(--primary-container)) !important;
        color: var(--surface) !important;
        border: none !important; font-weight: 600 !important;
        border-radius: 6px !important; padding: 8px 24px !important;
    }
    .stButton > button[kind="secondary"],
    .stButton > button:not([kind="primary"]) {
        background: transparent !important;
        border: 1px solid rgba(86,67,55,0.2) !important;
        color: var(--secondary) !important;
        border-radius: 6px !important;
    }
    .stProgress > div > div {
        background: linear-gradient(90deg, var(--primary-container), var(--primary)) !important;
    }
    .streamlit-expanderHeader {
        background: var(--surface-container) !important;
        border-radius: 6px !important;
        color: var(--secondary) !important;
    }
    .streamlit-expanderContent {
        background: var(--surface-low) !important;
    }
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        background: rgba(255,183,131,0.1) !important;
        color: var(--primary) !important;
        border-bottom: 2px solid var(--primary) !important;
    }
    .stTabs [data-baseweb="tab-list"] button {
        color: var(--secondary) !important;
    }
</style>
""", unsafe_allow_html=True)


# ============================================
# SESSION STATE
# ============================================

def _init():
    for k, v in {
        "page": "nova_consulta", "pipeline_rodou": False, "cnpj": "",
        "servicos_identificados": [], "triagem_pendente": [],
        "oportunidades": [], "dados_empresa": {}, "stats": {},
        "regras_sugeridas": [], "revisao_concluida": False, "motor": None,
        "download_proc": None, "download_cnpj": "",
        "cnpj_prefill": "",
    }.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()


# ============================================
# SIDEBAR — Label-only, left-aligned
# ============================================

with st.sidebar:
    st.markdown("""
        <p class="brand-title">Classificador de<br>Documentação Jurídica</p>
        <p class="brand-sub">Legal Intelligence</p>
    """, unsafe_allow_html=True)

    nav = [
        ("nova_consulta", "Nova Consulta"),
        ("download", "Download PDFs"),
        ("resultados", "Resultados"),
        ("revisao", "Revisão"),
        ("oportunidades", "Oportunidades"),
    ]

    n_rev = len(st.session_state.triagem_pendente)

    for key, label in nav:
        display = f"{label} ({n_rev})" if key == "revisao" and n_rev > 0 else label
        is_active = st.session_state.page == key

        # Active indicator: orange bar before label
        if is_active:
            display = f"▸ {display}"

        if st.button(display, key=f"nav_{key}", use_container_width=True):
            st.session_state.page = key
            st.rerun()

    st.markdown("<br>" * 6, unsafe_allow_html=True)
    st.markdown("---")
    st.button("Configurações", key="nav_cfg", use_container_width=True)

    if st.session_state.pipeline_rodou:
        d = st.session_state.dados_empresa
        st.markdown(f"""<div class="sb-status" style="margin-top:12px;">
            <strong style="color:#999;">Última consulta</strong><br>
            CNPJ: {d.get('cnpj','')}<br>
            {d.get('n_processos',0)} processos · {d.get('n_documentos',0)} docs<br>
            Custo: {d.get('custo_llm','$0')}
        </div>""", unsafe_allow_html=True)

    # Version footer — read from VERSION file at project root
    try:
        _version = (PROJECT_ROOT / "VERSION").read_text(encoding="utf-8").strip()
        st.markdown(
            f"""<div style="position:absolute;bottom:12px;left:16px;color:#555;font-size:11px;">
                v{_version}
            </div>""",
            unsafe_allow_html=True
        )
    except Exception:
        pass


# ============================================
# HELPERS
# ============================================

def _pill(c):
    c = c.lower()
    if "confirmado" in c or "alta" in c: return '<span class="p-ok">Confirmado</span>'
    if "automático" in c or "autom" in c or "llm" in c: return '<span class="p-auto">Automático</span>'
    if "pendente" in c or "revisão" in c or "revisao" in c: return '<span class="p-rev">Pendente</span>'
    return f"<span>{c}</span>"

def _fmt(d):
    d = d.strip()
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}" if len(d) == 14 else d

def _has_pdfs(cnpj):
    p = settings.DATA_DOCUMENTOS_DIR / cnpj
    return p.exists() and any(p.glob("*.pdf"))


def _listar_cnpjs_baixados(limite=8):
    """Lista CNPJs com documentos baixados, ordenados por modificação mais recente.

    Returns: lista de dicts [{"cnpj": str, "n_docs": int, "empresa": str}, ...]
    limitada aos `limite` mais recentes.
    """
    base = settings.DATA_DOCUMENTOS_DIR
    if not base.exists():
        return []

    entradas = []
    for sub in base.iterdir():
        if not sub.is_dir():
            continue
        cnpj = sub.name
        # CNPJ deve ter 14 dígitos
        if not (cnpj.isdigit() and len(cnpj) == 14):
            continue
        pdfs = list(sub.glob("*.pdf"))
        if not pdfs:
            continue
        # Nome da empresa se disponível
        empresa = ""
        empresa_json = sub / "empresa.json"
        if empresa_json.exists():
            try:
                import json
                emp = json.loads(empresa_json.read_text(encoding="utf-8"))
                empresa = emp.get("empresa", "")
            except Exception:
                pass
        entradas.append({
            "cnpj": cnpj,
            "n_docs": len(pdfs),
            "empresa": empresa,
            "mtime": sub.stat().st_mtime,
        })

    entradas.sort(key=lambda x: x["mtime"], reverse=True)
    return entradas[:limite]


def _disk_usage(cnpj):
    p = settings.DATA_DOCUMENTOS_DIR / cnpj
    if not p.exists(): return 0
    return sum(f.stat().st_size for f in p.rglob("*") if f.is_file())

def _limpar_registro_csv():
    """Remove duplicatas do registro_de_downloads.csv. Returns (antes, depois)."""
    rp = settings.REGISTRO_DOWNLOADS_CSV
    if not rp.exists():
        return 0, 0

    # Read all
    rows = []
    with rp.open("r", newline="", encoding="utf-8-sig") as f:
        fl = f.readline(); f.seek(0)
        dl = ";" if ";" in fl else ","
        reader = csv.DictReader(f, delimiter=dl)
        fieldnames = reader.fieldnames
        rows = list(reader)

    antes = len(rows)

    # Dedup by (processo, tipo_documento, filename)
    seen = set()
    unicos = []
    for row in rows:
        proc = row.get("numero_processo", "").strip()
        tipo = row.get("tipo_documento", "").strip()
        arquivo = Path(row.get("caminho_pdf", "").strip()).name
        chave = (proc, tipo, arquivo)
        if chave in seen:
            continue
        seen.add(chave)
        unicos.append(row)

    depois = len(unicos)

    # Rewrite
    with rp.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
        writer.writeheader()
        for row in unicos:
            writer.writerow(row)

    return antes, depois


# ============================================
# PIPELINE
# ============================================

def _run_pipeline(cnpj_input):
    from core.extrator import extrair_texto
    from core.gap_analysis import calcular_gap
    from classificacao.motor import MotorClassificacao

    bar = st.progress(0, text="Carregando documentos...")
    rp = settings.REGISTRO_DOWNLOADS_CSV
    if not rp.exists():
        st.error(f"Registro não encontrado: {rp}"); return

    regs = []
    seen = set()  # dedup by (processo, tipo_documento, filename)
    with rp.open("r", newline="", encoding="utf-8-sig") as f:
        fl = f.readline(); f.seek(0)
        dl = ";" if ";" in fl else ","
        for row in csv.DictReader(f, delimiter=dl):
            if cnpj_input and row.get("cnpj","").strip() != cnpj_input: continue
            # Dedup: same process + same doc type + same file = same entry
            proc = row.get("numero_processo","").strip()
            tipo = row.get("tipo_documento","").strip()
            arquivo = Path(row.get("caminho_pdf","").strip()).name
            chave = (proc, tipo, arquivo)
            if chave in seen:
                continue
            seen.add(chave)
            regs.append(row)

    if not regs:
        st.error(f"Nenhum documento para {_fmt(cnpj_input)}"); return

    cnpj = regs[0].get("cnpj","").strip()
    procs = OrderedDict()
    for r in regs:
        n = r.get("numero_processo","").strip()
        if n: procs.setdefault(n, []).append(r)
    for n in procs:
        procs[n].sort(key=lambda d: 0 if "PETICAO" in d.get("tipo_documento","") else 1)

    bar.progress(0.15, text="Extraindo textos...")
    docs = []
    for num, ds in procs.items():
        for r in ds:
            cp_raw = r.get("caminho_pdf","").strip()
            ts = r.get("tipo_documento","").strip()

            # Cross-platform path resolution:
            # CSV may contain Mac absolute paths — reconstruct from filename + CNPJ
            cp = Path(cp_raw)
            if not cp.exists():
                # Try relative to project root
                if not cp.is_absolute():
                    cp = settings.PROJECT_ROOT / cp_raw
                if not cp.exists():
                    # Reconstruct: data/documentos/{cnpj}/{filename}
                    filename = Path(cp_raw).name
                    cp = settings.DATA_DOCUMENTOS_DIR / cnpj / filename
                if not cp.exists():
                    continue

            try: td = TipoDocumento(ts)
            except ValueError: continue
            rel = extrair_texto(str(cp), td)
            if rel: docs.append((num, ts, rel, str(cp)))

    if not docs:
        st.error("Nenhum texto extraído."); return

    csv_a = settings.DATA_ENTRADA_DIR / "mapeamento_tipo_servico_ATIVO.csv"
    if not csv_a.exists(): shutil.copy2(settings.MAPEAMENTO_CSV, csv_a)
    motor = MotorClassificacao(mapeamento_csv=csv_a, auto_aprender=True)

    svcs=[]; found=set(); rev_s=set(); tri=[]
    for i,(num,ts,rel,cp) in enumerate(docs):
        bar.progress(0.3+0.5*(i+1)/len(docs), text=f"Classificando {i+1}/{len(docs)}...")
        res = motor.classificar_documento(texto=rel.trecho, numero_processo=num, tipo_documento=ts, caminho_pdf=cp)
        tipo=""; conf=""; met=""; obs=""
        if res:
            tipo=res.tipo_de_servico; met=res.metodo.value
            conf=TERMOS_NEGOCIO.get(res.confianca, res.confianca.value)
            obs=res.razao_llm or ""
            if res.confianca==NivelConfianca.REVISAO: rev_s.add(tipo)
            elif tipo!="REVISAO": found.add(tipo)
        item = ItemRelatorio(cnpj=cnpj, numero_processo=num, tipo_documento=ts,
                             tipo_de_servico=tipo, confianca=conf, metodo=met,
                             trecho_extraido=rel.trecho or "", observacao=obs)
        svcs.append(item)
        if "pendente" in conf.lower() or "revisao" in tipo.lower(): tri.append(item)

    bar.progress(0.9, text="Calculando oportunidades...")
    gap = calcular_gap(servicos_encontrados=found, servicos_revisao=rev_s, dados_empresa={"cnpj":cnpj})
    bar.progress(1.0, text="Concluído!")

    # Read company data from empresa.json (saved by downloader)
    empresa_nome = ""
    empresa_cidade = ""
    empresa_atividade = ""
    empresa_json = settings.DATA_DOCUMENTOS_DIR / cnpj / "empresa.json"
    if empresa_json.exists():
        try:
            import json
            emp = json.loads(empresa_json.read_text(encoding="utf-8"))
            empresa_nome = emp.get("empresa", "")
            empresa_cidade = emp.get("cidade_uf_matriz", "")
            empresa_atividade = emp.get("atividade_principal", "")
        except Exception:
            pass

    st.session_state.update({
        "pipeline_rodou":True, "cnpj":cnpj, "servicos_identificados":svcs,
        "triagem_pendente":tri, "oportunidades":gap.oportunidades, "motor":motor,
        "regras_sugeridas":[{"palavras":s.palavras_chave,"tipo":s.tipo_de_servico,"processo":s.numero_processo} for s in motor.regras_sugeridas],
        "revisao_concluida":len(tri)==0,
        "dados_empresa":{"cnpj":cnpj,"empresa":empresa_nome,"cidade_uf":empresa_cidade,
                         "atividade":empresa_atividade,
                         "n_processos":len(procs),"n_documentos":len(docs),
                         "n_identificados":len(found),"n_oportunidades":gap.n_oportunidades,
                         "n_revisao":len(tri),"custo_llm":f"${motor._llm.custo_estimado:.6f}",
                         "chamadas_llm":motor._llm._calls},
        "stats":{"camada1":motor.stats.camada1_regras,"camada2":motor.stats.camada2_llm,"revisao":motor.stats.revisao},
    })
    time.sleep(0.3); bar.empty()
    st.session_state.page = "resultados"
    st.rerun()


def _start_download(cnpj, ano_min=2016):
    runner = PROJECT_ROOT / "scripts" / "_run_download.py"
    flag = settings.DATA_SAIDA_DIR / f".downloading_{cnpj}"
    log_file = settings.DATA_SAIDA_DIR / f"download_log_{cnpj}.txt"
    runner.parent.mkdir(parents=True, exist_ok=True)
    settings.DATA_SAIDA_DIR.mkdir(parents=True, exist_ok=True)

    # Write runner script with error logging
    # P1: redirect sys.stdout/stderr and logging to file so nothing writes into Popen pipes
    # P2: delete flag file in finally block so UI can detect completion after page refresh
    runner.write_text(
        f'import sys, os, logging, traceback\n'
        f'sys.path.insert(0, r"{PROJECT_ROOT}")\n'
        f'os.environ["MIN_PROCESS_YEAR"] = "{ano_min}"\n'
        f'flag_path = r"{flag}"\n'
        f'log = open(r"{log_file}", "w", encoding="utf-8", buffering=1)\n'
        f'sys.stdout = log\n'
        f'sys.stderr = log\n'
        f'logging.basicConfig(level=logging.INFO, stream=log,\n'
        f'    format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")\n'
        f'try:\n'
        f'    log.write("Iniciando download...\\n")\n'
        f'    log.flush()\n'
        f'    from core.downloader import executar_downloads\n'
        f'    executar_downloads(["{cnpj}"])\n'
        f'    log.write("Download concluido com sucesso.\\n")\n'
        f'except Exception as e:\n'
        f'    log.write(f"ERRO: {{e}}\\n")\n'
        f'    traceback.print_exc(file=log)\n'
        f'finally:\n'
        f'    log.close()\n'
        f'    try:\n'
        f'        if os.path.exists(flag_path): os.remove(flag_path)\n'
        f'    except Exception: pass\n',
        encoding="utf-8"
    )

    # Create flag file
    flag.write_text(cnpj, encoding="utf-8")

    # Set encoding for Windows subprocess
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    proc = subprocess.Popen(
        [sys.executable, str(runner)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        cwd=str(PROJECT_ROOT),
        env=env,
    )
    st.session_state.download_proc = proc
    st.session_state.download_cnpj = cnpj
    return proc


def _check_download():
    """Check download status using flag file + Popen. Survives page refresh."""
    cnpj = st.session_state.get("download_cnpj", "")

    # Check flag files for any CNPJ
    if not cnpj:
        for f in settings.DATA_SAIDA_DIR.glob(".downloading_*"):
            cnpj = f.stem.replace(".downloading_", "")
            st.session_state.download_cnpj = cnpj
            break

    if not cnpj:
        return None

    flag = settings.DATA_SAIDA_DIR / f".downloading_{cnpj}"
    runner = PROJECT_ROOT / "scripts" / "_run_download.py"

    # Check Popen if available
    proc = st.session_state.get("download_proc")
    if proc is not None:
        rc = proc.poll()
        if rc is None:
            return "running"
        # Process finished
        st.session_state.download_proc = None
        flag.unlink(missing_ok=True)
        runner.unlink(missing_ok=True)
        return "done" if rc == 0 else "error"

    # No Popen (page refreshed) — check flag file.
    # P2: new runner deletes flag in its finally block when subprocess completes.
    # Flag present = subprocess alive. Flag absent = subprocess finished.
    if flag.exists():
        return "running"

    # Flag gone — subprocess finished. Inspect log tail to distinguish success/error.
    log_path = settings.DATA_SAIDA_DIR / f"download_log_{cnpj}.txt"
    if log_path.exists():
        try:
            tail = log_path.read_text(encoding="utf-8")
            if "ERRO:" in tail or "Traceback" in tail:
                return "error"
            if "Download concluido com sucesso" in tail:
                return "done"
        except Exception:
            pass

    return None


def _get_downloaded_pdfs(cnpj):
    """List PDFs downloaded for a CNPJ, sorted by modification time (newest first)."""
    pasta = settings.DATA_DOCUMENTOS_DIR / cnpj
    if not pasta.exists():
        return []
    pdfs = list(pasta.glob("*.pdf"))
    pdfs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return pdfs


def _cancel_download():
    """Cancel/reset download state. Cleans up flag files and kills subprocess."""
    cnpj = st.session_state.get("download_cnpj", "")

    # Kill subprocess if still alive
    proc = st.session_state.get("download_proc")
    if proc is not None:
        try:
            proc.kill()
        except Exception:
            pass
    st.session_state.download_proc = None

    # Clean up flag files
    if cnpj:
        flag = settings.DATA_SAIDA_DIR / f".downloading_{cnpj}"
        flag.unlink(missing_ok=True)

    # Clean up all stale flags
    for f in settings.DATA_SAIDA_DIR.glob(".downloading_*"):
        f.unlink(missing_ok=True)

    # Clean up runner script
    runner = PROJECT_ROOT / "scripts" / "_run_download.py"
    runner.unlink(missing_ok=True)

    st.session_state.download_cnpj = ""


def _recalc_gap():
    from core.gap_analysis import calcular_gap
    found = {i.tipo_de_servico for i in st.session_state.servicos_identificados
             if i.confianca.lower() not in ("pendente",) and i.tipo_de_servico != "REVISAO"}
    gap = calcular_gap(servicos_encontrados=found, dados_empresa={"cnpj":st.session_state.cnpj})
    st.session_state.oportunidades = gap.oportunidades
    st.session_state.dados_empresa["n_oportunidades"] = gap.n_oportunidades
    st.session_state.dados_empresa["n_revisao"] = len(st.session_state.triagem_pendente)
    st.session_state.dados_empresa["n_identificados"] = len(found)
    if not st.session_state.triagem_pendente: st.session_state.revisao_concluida = True


# ============================================
# PAGE: NOVA CONSULTA
# ============================================

def pg_nova_consulta():
    st.markdown('<p class="overline">Prospecção</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-title">Nova Consulta</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-sub">Insira o CNPJ para gerar o relatório de oportunidades tributárias.</p>', unsafe_allow_html=True)

    # Se o usuário clicou em "Usar" em um CNPJ da lista abaixo, o handler setou
    # cnpj_prefill. Aqui propagamos o valor para a chave do proprio widget ANTES
    # dele ser instanciado — padrao canonico do Streamlit para preencher widgets
    # programaticamente. Tentar passar value=prefill com key= na mesma chamada
    # NAO funciona: Streamlit prioriza session_state cacheado sobre o value=.
    if st.session_state.get("cnpj_prefill"):
        st.session_state["cnpj_input"] = st.session_state["cnpj_prefill"]
        st.session_state["cnpj_prefill"] = ""

    cnpj = st.text_input("CNPJ", placeholder="00.000.000/0000-00",
                         label_visibility="collapsed", key="cnpj_input")
    cl = "".join(c for c in cnpj if c.isdigit())

    if cl and len(cl) == 14:
        has = _has_pdfs(cl)
        if has:
            st.markdown(f"""<div class="card">
                <span class="p-ok">Documentos disponíveis</span>
                <p style="color:var(--on-surface);font-size:16px;margin:12px 0 4px;font-family:Manrope,sans-serif;font-weight:500;">{_fmt(cl)}</p>
                <p style="color:#777;font-size:13px;margin:0;">Pronto para classificar.</p>
            </div>""", unsafe_allow_html=True)
            c1, c2, _ = st.columns([1, 1, 2])
            with c1:
                if st.button("Gerar Consulta", type="primary", use_container_width=True):
                    _run_pipeline(cl)
            with c2:
                if st.button("Re-baixar Documentos", use_container_width=True):
                    _start_download(cl)
                    st.session_state.page = "download"
                    st.rerun()
        else:
            st.markdown(f"""<div class="card-accent">
                <p style="color:var(--primary);font-size:16px;margin:0 0 4px;font-family:Manrope,sans-serif;font-weight:500;">{_fmt(cl)}</p>
                <p style="color:#777;font-size:13px;margin:0;">Nenhum documento encontrado. Baixe os documentos primeiro.</p>
            </div>""", unsafe_allow_html=True)
            if st.button("Fazer Download", type="primary", use_container_width=True):
                _start_download(cl)
                st.session_state.page = "download"
                st.rerun()
    elif cl:
        st.warning("CNPJ deve ter 14 dígitos.")

    if st.session_state.pipeline_rodou:
        st.markdown("<br>", unsafe_allow_html=True)
        d = st.session_state.dados_empresa
        st.markdown(f"""<div class="card-accent">
            <p class="overline" style="margin-bottom:8px;">Última Consulta</p>
            <p style="color:var(--on-surface);font-size:18px;font-weight:500;font-family:Manrope,sans-serif;margin:0 0 6px;">{_fmt(d.get('cnpj',''))}</p>
            <p style="color:#777;font-size:13px;margin:0;">{d.get('n_identificados',0)} serviços · {d.get('n_oportunidades',0)} oportunidades · {d.get('n_revisao',0)} pendentes</p>
        </div>""", unsafe_allow_html=True)

    # Lista de CNPJs com documentos já baixados — facilita copiar/colar.
    baixados = _listar_cnpjs_baixados(limite=8)
    if baixados:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown('<p class="overline">CNPJs com Documentos Disponíveis</p>', unsafe_allow_html=True)
        st.markdown('<p class="page-sub" style="margin-bottom:12px;">Clique em qualquer item para preencher o campo acima.</p>', unsafe_allow_html=True)
        for entrada in baixados:
            c1, c2 = st.columns([5, 1])
            with c1:
                nome = entrada["empresa"] if entrada["empresa"] else "Empresa não identificada"
                st.markdown(f"""<div class="card" style="margin-bottom:8px;">
                    <p style="color:var(--on-surface);font-size:15px;font-family:Manrope,sans-serif;font-weight:500;margin:0 0 4px;">{nome}</p>
                    <p style="color:var(--primary);font-size:13px;margin:0 0 2px;">{_fmt(entrada['cnpj'])}</p>
                    <p style="color:#777;font-size:12px;margin:0;">{entrada['n_docs']} documentos baixados</p>
                </div>""", unsafe_allow_html=True)
            with c2:
                if st.button("Usar", key=f"usar_{entrada['cnpj']}", use_container_width=True):
                    st.session_state.cnpj_prefill = entrada["cnpj"]
                    st.rerun()


# ============================================
# PAGE: DOWNLOAD PDFs
# ============================================

def pg_download():
    st.markdown('<p class="overline">Módulo de Extração</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-title">Download PDFs</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-sub">Baixe documentos processuais do TRF1 PJe. A automação roda em segundo plano.</p>', unsafe_allow_html=True)

    # Check running download
    status = _check_download()
    dl_cnpj = st.session_state.get("download_cnpj", "")

    # Show log file if exists
    def _show_log(cnpj_for_log):
        log_path = settings.DATA_SAIDA_DIR / f"download_log_{cnpj_for_log}.txt"
        if log_path.exists():
            try:
                content = log_path.read_text(encoding="utf-8").strip()
                if content:
                    with st.expander("Log da automação", expanded=("ERRO" in content)):
                        st.code(content[-3000:], language=None)
            except Exception:
                pass

    if status == "running":
        st.markdown(f"""<div class="card" style="border-left:3px solid var(--primary);">
            <p style="color:var(--primary);font-size:14px;margin:0 0 4px;">Download em andamento</p>
            <p style="color:var(--on-surface);font-size:16px;font-family:Manrope;margin:0 0 4px;">{_fmt(dl_cnpj)}</p>
            <p style="color:#777;font-size:13px;margin:0;">Chrome de automação está rodando. Aguarde a conclusão.</p>
        </div>""", unsafe_allow_html=True)
        _show_log(dl_cnpj)
        if st.button("Cancelar Download", use_container_width=False):
            _cancel_download()
            st.rerun()
        # P2: auto-refresh while running so UI detects completion without manual interaction.
        # Cancel click is preserved — Streamlit queues it and processes on next rerun.
        time.sleep(3)
        st.rerun()
    elif status == "done":
        st.markdown(f"""<div class="card" style="border-left:3px solid var(--success);">
            <p style="color:var(--success);font-size:14px;margin:0 0 4px;">Download concluído</p>
            <p style="color:var(--on-surface);font-size:16px;font-family:Manrope;margin:0 0 4px;">{_fmt(dl_cnpj)}</p>
            <p style="color:#777;font-size:13px;margin:0;">Documentos prontos. Vá para "Nova Consulta" para classificar.</p>
        </div>""", unsafe_allow_html=True)
        _show_log(dl_cnpj)
    elif status == "error":
        st.error("Erro durante o download.")
        _show_log(dl_cnpj)

    # Metrics for active/last CNPJ
    show_cnpj = dl_cnpj if dl_cnpj else ""

    # Input for new download (only show if NOT running)
    if status != "running":
        st.markdown("<br>", unsafe_allow_html=True)

        # Chrome warning
        st.markdown("""<div class="note" style="border-left-color:#D4700A;">
            <strong style="color:#D4700A;">Antes de iniciar:</strong> O sistema abrirá uma janela do Chrome
            com o perfil de automação (certificado digital). Sua sessão do Chrome pessoal não será afetada.
        </div>""", unsafe_allow_html=True)

        cnpj_inp = st.text_input("CNPJ para download", placeholder="00.000.000/0000-00", label_visibility="collapsed")
        cl = "".join(c for c in cnpj_inp if c.isdigit())

        current_year = datetime.now().year
        anos = list(range(current_year, 2015, -1))
        ano_sel = st.selectbox("Processos a partir do ano", anos, index=0,
                               help="Baixar apenas processos autuados a partir deste ano.")

        if cl and len(cl) == 14:
            show_cnpj = cl
            st.markdown(f"""<div class="card">
                <p style="color:var(--on-surface);font-size:16px;font-family:Manrope;margin:0 0 4px;">{_fmt(cl)}</p>
                <p style="color:#777;font-size:13px;margin:0;">Chrome será aberto. Faça login via whom.doc9 quando solicitado.</p>
            </div>""", unsafe_allow_html=True)

            if st.button("Iniciar Download", type="primary", use_container_width=True):
                _start_download(cl, ano_min=ano_sel)
                st.rerun()

    # Always show metrics + document list for active CNPJ
    if show_cnpj:
        st.markdown("<br>", unsafe_allow_html=True)

        # Metrics
        disk = _disk_usage(show_cnpj)
        pdfs = _get_downloaded_pdfs(show_cnpj)
        n_pdfs = len(pdfs)

        c1, c2, c3 = st.columns(3)
        with c1:
            disk_display = f"{disk/1024/1024:.1f}" if disk > 1024*1024 else f"{disk/1024:.0f} KB" if disk > 0 else "0"
            unit = "MB" if disk > 1024*1024 else ""
            st.markdown(f"""<div class="m-card">
                <p class="m-val">{disk_display} <span style="font-size:14px;color:#777;">{unit}</span></p>
                <p class="m-lbl">Espaço em Disco</p>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown(f"""<div class="m-card">
                <p class="m-val">{n_pdfs}</p>
                <p class="m-lbl">Documentos Baixados</p>
            </div>""", unsafe_allow_html=True)
        with c3:
            # Estimated speed based on file timestamps
            if n_pdfs >= 2:
                newest = pdfs[0].stat().st_mtime
                oldest = pdfs[-1].stat().st_mtime
                elapsed_min = max((newest - oldest) / 60, 0.1)
                speed = n_pdfs / elapsed_min
                st.markdown(f"""<div class="m-card">
                    <p class="m-val">{speed:.1f} <span style="font-size:14px;color:#777;">docs/min</span></p>
                    <p class="m-lbl">Velocidade Estimada</p>
                </div>""", unsafe_allow_html=True)
            else:
                st.markdown(f"""<div class="m-card">
                    <p class="m-val">—</p>
                    <p class="m-lbl">Velocidade Estimada</p>
                </div>""", unsafe_allow_html=True)

        # Document list
        if pdfs:
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<p class="overline">Documentos Baixados</p>', unsafe_allow_html=True)

            for pdf in pdfs[:30]:  # Show last 30
                mod_time = datetime.fromtimestamp(pdf.stat().st_mtime).strftime("%d/%m %H:%M")
                size_kb = pdf.stat().st_size / 1024
                name = pdf.name

                # Extract doc type from filename
                doc_type = ""
                if "PETICAO" in name.upper(): doc_type = "PETIÇÃO"
                elif "DECISAO" in name.upper(): doc_type = "DECISÃO"
                elif "SENTENCA" in name.upper(): doc_type = "SENTENÇA"

                tipo_pill = f'<span class="p-auto" style="font-size:10px;padding:2px 8px;">{doc_type}</span>' if doc_type else ""

                st.markdown(f"""<div style="display:flex;justify-content:space-between;align-items:center;padding:8px 12px;
                    background:var(--surface-container);border-radius:4px;margin:3px 0;font-size:13px;">
                    <span style="color:var(--on-surface-variant);flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{name}</span>
                    <span style="color:#555;margin:0 12px;white-space:nowrap;">{tipo_pill} {size_kb:.0f} KB · {mod_time}</span>
                </div>""", unsafe_allow_html=True)


# ============================================
# PAGE: RESULTADOS
# ============================================

def pg_resultados():
    if not st.session_state.pipeline_rodou:
        st.info("Execute uma consulta na página 'Nova Consulta' para ver resultados.")
        return

    d = st.session_state.dados_empresa
    n_rev = d.get("n_revisao", 0)

    st.markdown('<p class="overline">Análise</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-title">Resultados</p>', unsafe_allow_html=True)

    # Company card
    empresa_nome = d.get("empresa", "")
    empresa_cidade = d.get("cidade_uf", "")
    empresa_atividade = d.get("atividade", "")
    nome_display = empresa_nome if empresa_nome else _fmt(d.get('cnpj',''))
    detalhes = []
    if empresa_cidade: detalhes.append(empresa_cidade)
    if empresa_atividade: detalhes.append(empresa_atividade)
    detalhes_str = " · ".join(detalhes) if detalhes else ""

    st.markdown(f"""<div class="card-empresa">
        <p class="overline" style="margin-bottom:4px;">Empresa</p>
        <p style="color:var(--on-surface);font-size:18px;font-family:Manrope;font-weight:600;margin:0 0 4px;">{nome_display}</p>
        <p style="color:var(--primary);font-size:14px;margin:0 0 4px;">{_fmt(d.get('cnpj',''))}</p>
        {"<p style='color:#777;font-size:13px;margin:0 0 4px;'>" + detalhes_str + "</p>" if detalhes_str else ""}
        """, unsafe_allow_html=True)

    # Metrics — hide opportunities if pendentes > 0
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="m-card"><p class="m-val">{d.get("n_processos",0)}</p><p class="m-lbl">Processos</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="m-card"><p class="m-val">{d.get("n_identificados",0)}</p><p class="m-lbl">Serviços Identificados</p></div>', unsafe_allow_html=True)
    with c3:
        if n_rev > 0:
            st.markdown(f'<div class="m-card" style="border-left:3px solid var(--error);"><p class="m-val" style="color:var(--error);">{n_rev}</p><p class="m-lbl">Aguardando Revisão</p></div>', unsafe_allow_html=True)
        else:
            st.markdown(f'<div class="m-card-hl"><p class="m-val-a">{d.get("n_oportunidades",0)}</p><p class="m-lbl">Oportunidades</p></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Serviços Identificados")

    # Lista de teses (para o dropdown de correcao) — carregada uma vez por render.
    from core.input_loader import carregar_lista_servicos, nomes_teses as gn
    _opts_corr = ["(manter classificação atual)"] + sorted(gn(carregar_lista_servicos()))

    for item in st.session_state.servicos_identificados:
        pill = _pill(item.confianca)
        with st.expander(f"{item.numero_processo} · {item.tipo_documento} · {item.tipo_de_servico} · {item.confianca}"):
            c1, c2 = st.columns(2)
            with c1:
                st.markdown(f"**Tipo de serviço:** {item.tipo_de_servico}")
                st.markdown(f"**Método:** {item.metodo}")
                st.markdown(f"**Status:** {pill}", unsafe_allow_html=True)
            with c2:
                st.markdown(f"**Processo:** {item.numero_processo}")
                st.markdown(f"**Documento:** {item.tipo_documento}")
            if item.trecho_extraido:
                st.markdown("**Trecho extraído:**")
                st.markdown(f'<div class="t-ext">{item.trecho_extraido}</div>', unsafe_allow_html=True)
            if item.observacao:
                st.markdown("**Análise do sistema:**")
                st.markdown(f'<div class="sug-box">{item.observacao}</div>', unsafe_allow_html=True)

            # Correcao manual da classificacao (Change 3)
            # UID estavel baseado no conteudo — evita colisao entre linhas.
            _corr_uid = abs(hash(f"{item.numero_processo}|{item.tipo_documento}|{(item.trecho_extraido or '')[:80]}"))
            st.markdown("<br>", unsafe_allow_html=True)
            st.markdown('<p class="overline">Corrigir classificação</p>', unsafe_allow_html=True)
            st.markdown('<p style="color:#777;font-size:12px;margin:0 0 8px;">Se a classificação acima estiver incorreta, cole a parte relevante do texto, selecione o serviço correto e clique em Corrigir. A correção também gera uma regra sugerida na página Revisão.</p>', unsafe_allow_html=True)

            rel_corr = st.text_area("Parte Relevante",
                                    key=f"corr_rel_{_corr_uid}",
                                    height=80,
                                    placeholder="Cole as 2-3 linhas do trecho extraído que definem o serviço...",
                                    label_visibility="collapsed")

            cc1, cc2 = st.columns([3, 1])
            with cc1:
                nova_tese = st.selectbox("Serviço correto", _opts_corr,
                                         key=f"corr_svc_{_corr_uid}",
                                         label_visibility="collapsed")
            with cc2:
                corrigir = st.button("Corrigir", key=f"corr_btn_{_corr_uid}", use_container_width=True)

            if corrigir:
                if nova_tese == "(manter classificação atual)":
                    st.warning("Selecione um serviço da lista antes de clicar em Corrigir.")
                elif nova_tese == item.tipo_de_servico:
                    st.info("A classificação selecionada é a mesma que já está registrada.")
                elif not rel_corr.strip():
                    st.warning("Cole a parte relevante do texto para gerar a regra sugerida.")
                else:
                    antigo = item.tipo_de_servico
                    item.tipo_de_servico = nova_tese
                    item.confianca = "Confirmado"
                    item.metodo = "CORRECAO_MANUAL"

                    # Extrai keywords da parte relevante para gerar regra sugerida
                    # (mesmo fluxo da pagina Revisao).
                    from classificacao.regras import _extrair_keywords
                    kws = _extrair_keywords(rel_corr.strip())
                    kw_str = " ".join(kws)

                    st.session_state.regras_sugeridas.append({
                        "palavras": kw_str,
                        "tipo": nova_tese,
                        "processo": item.numero_processo,
                        "origem": "correcao_resultados",
                        "texto_original": rel_corr.strip(),
                    })
                    _recalc_gap()
                    st.toast(f"Classificação corrigida ('{antigo}' → '{nova_tese}'). Aprove a nova regra na página Revisão.")
                    st.rerun()


# ============================================
# PAGE: REVISÃO
# ============================================

def pg_revisao():
    if not st.session_state.pipeline_rodou:
        st.info("Execute uma consulta primeiro."); return

    st.markdown('<p class="overline">Human in the Loop</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-title">Revisão de Classificação</p>', unsafe_allow_html=True)

    tri = st.session_state.triagem_pendente

    if not tri:
        st.success("Todos os itens revisados. Oportunidades atualizadas.")
        st.session_state.revisao_concluida = True
        return

    # Tabs: Revisão | Regras Sugeridas
    tab_rev, tab_regras = st.tabs([f"Revisão ({len(tri)})", "Regras Sugeridas"])

    with tab_rev:
        st.markdown(f'<p class="page-sub">{len(tri)} itens aguardando revisão</p>', unsafe_allow_html=True)

        from core.input_loader import carregar_lista_servicos, nomes_teses as gn
        opts = ["(Selecionar tipo de serviço)"] + sorted(gn(carregar_lista_servicos())) + ["Não é uma tese (ignorar)"]

        for idx, item in enumerate(tri):
            # UID estavel baseado em hash do conteudo — imune a pop/shift do indice.
            # Bug anterior: usar idx posicional fazia Streamlit reutilizar estado
            # cacheado do item anterior apos pop, causando texto "fantasma".
            _uid_str = f"{item.numero_processo}|{item.tipo_documento}|{(item.trecho_extraido or '')[:80]}"
            uid = abs(hash(_uid_str))

            st.markdown(f"""<div class="rev-card">
                <span class="p-rev">Item {idx+1} de {len(tri)}</span>
                <span style="float:right;font-family:monospace;color:#777;font-size:13px;">{item.numero_processo}</span>
            </div>""", unsafe_allow_html=True)

            left, right = st.columns([3, 2])

            with left:
                st.markdown('<p class="overline">Texto Extraído</p>', unsafe_allow_html=True)
                st.text_area("t", value=item.trecho_extraido, height=280,
                             disabled=True, label_visibility="collapsed", key=f"ta_{uid}")

            with right:
                if item.observacao:
                    st.markdown('<p class="overline">Sugestão do Sistema</p>', unsafe_allow_html=True)
                    st.markdown(f'<div class="sug-box">{item.observacao}</div>', unsafe_allow_html=True)

                st.markdown('<p class="overline" style="margin-top:16px;">Parte Relevante</p>', unsafe_allow_html=True)
                rel = st.text_area("r", key=f"rel_{uid}", height=80,
                                   placeholder="Cole as 2-3 linhas que definem o serviço...",
                                   label_visibility="collapsed")

                escolha = st.selectbox("Tipo de serviço", opts, key=f"svc_{uid}",
                                       label_visibility="collapsed")

                ca, cb = st.columns(2)
                with ca:
                    conf = st.button("Confirmar", key=f"c_{uid}", type="primary", use_container_width=True)
                with cb:
                    skip = st.button("Pular", key=f"s_{uid}", use_container_width=True)

            if conf:
                if escolha == "(Selecionar tipo de serviço)":
                    st.warning("Selecione um tipo de serviço.")
                elif escolha == "Não é uma tese (ignorar)":
                    # "Ignorar" só afeta o documento atual (nao propaga para o processo)
                    st.session_state.triagem_pendente.pop(idx)
                    _recalc_gap()
                    st.rerun()
                else:
                    # Se parte relevante foi fornecida, extrai keywords e sugere regra
                    # (apenas uma vez, a partir do documento efetivamente classificado).
                    if rel.strip():
                        from classificacao.regras import _extrair_keywords
                        kws = _extrair_keywords(rel.strip())
                        kw_str = " ".join(kws)
                        st.session_state.regras_sugeridas.append({
                            "palavras": kw_str,
                            "tipo": escolha,
                            "processo": item.numero_processo,
                            "origem": "revisao_manual",
                            "texto_original": rel.strip(),
                        })
                        st.toast(f"Regra sugerida adicionada. Aprove na aba 'Regras Sugeridas'.")

                    # Propagacao no nivel do processo (Change 5):
                    # Todos os documentos do mesmo processo recebem a mesma classificacao
                    # e sao removidos da fila de revisao em uma unica operacao.
                    proc_alvo = item.numero_processo
                    n_afetados = 0
                    for it in st.session_state.triagem_pendente:
                        if it.numero_processo == proc_alvo:
                            it.tipo_de_servico = escolha
                            it.confianca = "Confirmado"
                            it.metodo = "REVISAO_MANUAL"
                            n_afetados += 1
                    # Filtra (remove todos os documentos deste processo)
                    st.session_state.triagem_pendente = [
                        it for it in st.session_state.triagem_pendente
                        if it.numero_processo != proc_alvo
                    ]
                    if n_afetados > 1:
                        st.toast(f"{n_afetados} documentos deste processo foram classificados.")
                    _recalc_gap()
                    st.rerun()

            if skip:
                st.toast("Item pulado.")

            st.markdown("<br>", unsafe_allow_html=True)

    with tab_regras:
        if st.session_state.regras_sugeridas:
            st.markdown('<p class="overline">Regras Sugeridas</p>', unsafe_allow_html=True)
            st.markdown('<p class="page-sub">Regras detectadas pelo LLM ou extraídas da revisão manual. Aprove para adicionar ao classificador determinístico.</p>', unsafe_allow_html=True)
            for i, s in enumerate(st.session_state.regras_sugeridas):
                origem_raw = s.get("origem", "")
                if origem_raw == "revisao_manual":
                    origem = "Revisão Manual"
                elif origem_raw == "correcao_resultados":
                    origem = "Correção em Resultados"
                else:
                    origem = "LLM"
                titulo = f"[{origem}] '{s['palavras']}' → {s['tipo']}" if s['palavras'] else f"[{origem}] → {s['tipo']}"
                with st.expander(titulo):
                    if s['palavras']:
                        st.markdown(f"**Keywords:** {s['palavras']}")
                    st.markdown(f"**Serviço:** {s['tipo']}")
                    st.markdown(f"**Processo:** {s['processo']}")
                    if s.get("texto_original"):
                        st.markdown(f"**Parte relevante original:**")
                        st.markdown(f'<div class="sug-box">{s["texto_original"]}</div>', unsafe_allow_html=True)
                    # Botao "Aprovar" so aparece quando ha palavras-chave para salvar na CSV.
                    # Entradas de "Correcao em Resultados" sem palavras sao informativas
                    # (registram que a classificacao foi corrigida manualmente).
                    if s['palavras']:
                        if st.button("Aprovar Regra", key=f"ap_{i}"):
                            csv_a = settings.DATA_ENTRADA_DIR / "mapeamento_tipo_servico_ATIVO.csv"
                            from classificacao.motor import _append_regra_csv
                            ok = _append_regra_csv(s["palavras"], s["tipo"], csv_a)
                            st.toast("Regra aprovada e salva!" if ok else "Regra já existe.")
                    else:
                        st.info("Este registro é informativo (correção manual sem palavras-chave). Sem regra determinística para aprovar.")
        else:
            st.info("Nenhuma regra sugerida ainda. Classifique itens na aba Revisão ou execute uma consulta.")


# ============================================
# PAGE: OPORTUNIDADES
# ============================================

def pg_oportunidades():
    if not st.session_state.pipeline_rodou:
        st.info("Execute uma consulta primeiro."); return

    st.markdown('<p class="overline">Relatório Estratégico</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-title">Relatório de Oportunidades</p>', unsafe_allow_html=True)
    st.markdown('<p class="page-sub">Mapeamento de lacunas tributárias e serviços pendentes de implementação.</p>', unsafe_allow_html=True)

    n_tri = len(st.session_state.triagem_pendente)
    if n_tri > 0 and not st.session_state.revisao_concluida:
        st.markdown(f"""<div class="blk-warn">
            <strong>{n_tri} itens aguardando revisão.</strong><br>
            Revise todos os itens na página "Revisão" antes de visualizar as oportunidades finais.
        </div>""", unsafe_allow_html=True)
        return

    ops = st.session_state.oportunidades
    d = st.session_state.dados_empresa

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown(f'<div class="m-card"><p class="m-val">74</p><p class="m-lbl">Todos os Serviços</p></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div class="m-card"><p class="m-val">{d.get("n_identificados",0)}</p><p class="m-lbl">Serviços Identificados</p></div>', unsafe_allow_html=True)
    with c3:
        st.markdown(f'<div class="m-card-hl"><p class="m-val-a">{len(ops)}</p><p class="m-lbl">Oportunidades Ativas</p></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("#### Oportunidades Identificadas")

    for i, op in enumerate(ops):
        area = f" · {op.area_responsavel}" if op.area_responsavel else ""
        with st.expander(f"**{i+1}.** {op.servico_disponivel}{area}"):
            if op.area_responsavel: st.markdown(f"**Área:** {op.area_responsavel}")
            if op.ramo_de_atividade: st.markdown(f"**Ramo:** {op.ramo_de_atividade}")
            if op.regime_tributario: st.markdown(f"**Regime:** {op.regime_tributario}")
            if op.objeto_da_tese: st.markdown(f"**Objeto:** {op.objeto_da_tese}")

    st.markdown("---")
    if st.button("Exportar Relatório Excel", type="primary"):
        from scripts.gerar_relatorio import gerar_relatorio_excel
        dt = datetime.now().strftime("%Y%m%d")
        cnpj = d.get("cnpj","")
        path = settings.DATA_SAIDA_DIR / f"relatorio_de_oportunidades_{cnpj}_{dt}.xlsx"
        f = gerar_relatorio_excel(dados_empresa=d, servicos_identificados=st.session_state.servicos_identificados,
                                  oportunidades=ops, triagem_pendente=st.session_state.triagem_pendente, caminho_saida=path)
        st.success(f"Relatório salvo: {f}")


# ============================================
# ROUTER
# ============================================

p = st.session_state.page
if p == "nova_consulta": pg_nova_consulta()
elif p == "download": pg_download()
elif p == "resultados": pg_resultados()
elif p == "revisao": pg_revisao()
elif p == "oportunidades": pg_oportunidades()