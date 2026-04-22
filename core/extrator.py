"""
automacao-juridica-trf1 — Extrator de trechos relevantes de PDFs

Estratégia de extração:
  DECISÃO — heading-based: localiza heading → extrai N chars após.
            Cascata: heading → anchor semântico → embedding → fallback posicional.
  PETIÇÃO — positional: últimos N chars limpos do documento.
            Heading detection é auditoria apenas (não dirige extração).
            Embedding dispara como safety net se quality gate falha.

Configuração via .env:
  EXTRACT_CHARS_DECISAO=1000  (chars após heading de decisão)
  EXTRACT_CHARS_PETICAO=6000  (chars do final do documento de petição)

Validado contra 79 PDFs reais:
  - 52 ok, 20 vazios, 7 com fallback (2 edge cases genuínos)
  - 1 texto_ilegivel (PDF com encoding quebrado — irrecuperável)

Uso:
    from core.extrator import extrair_texto, extrair_lote
    resultado = extrair_texto("caminho/doc.pdf", TipoDocumento.DECISAO)
    resultados = extrair_lote(registros_download, cnpj="84466424000136")
"""
from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import fitz  # PyMuPDF

from core.config import settings
from core.modelos import RelatorioExtracao, TipoDocumento


# ============================================
# CONSTANTES
# ============================================

MIN_CHARS_DOCUMENTO_UTIL = 200   # abaixo disto → documento_vazio
MIN_CHARS_TRECHO_VALIDO = 80     # abaixo disto → revisar
MIN_ALPHA_RATIO = 0.50           # abaixo disto → texto_ilegivel

_AUDIT_COLUMNS = [
    "caminho_pdf", "tipo_documento", "variation_tag", "estrategia_usada",
    "heading_encontrado", "heading_audit", "fallback_usado", "embedding_usado",
    "pattern_match", "pagina_heading", "paginas_total", "paginas_conteudo",
    "capa_trf1_detectada", "chars_texto_bruto", "chars_texto_limpo",
    "chars_extraidos", "quality_alpha_ratio", "status", "trecho_preview",
]


# ============================================
# PERFIL INTERNO DO PDF
# ============================================

@dataclass
class PerfilPDF:
    """Perfil completo de diagnóstico de um PDF processado."""

    caminho_pdf: str = ""
    tipo_documento: str = ""

    # Estrutura
    paginas_total: int = 0
    paginas_conteudo: int = 0
    capa_trf1_detectada: bool = False
    chars_texto_bruto: int = 0
    chars_texto_limpo: int = 0

    # Heading (auditoria para PETIÇÃO, ativo para DECISÃO)
    heading_encontrado: bool = False
    heading_audit: str = ""
    heading_texto_original: str = ""
    pagina_heading: int = 0

    # Extração
    variation_tag: str = ""
    estrategia_usada: str = ""
    fallback_usado: bool = False
    embedding_usado: bool = False
    pattern_match: str = ""
    chars_extraidos: int = 0
    quality_alpha_ratio: float = 0.0
    trecho: str = ""

    # Status: ok | ok_com_fallback | revisar | texto_ilegivel | documento_vazio | erro_abertura
    status: str = ""
    erro: str = ""

    # Dados internos (não exportados)
    _paginas_texto: list = field(default_factory=list, repr=False)
    _texto_limpo: str = field(default="", repr=False)

    def to_audit_row(self) -> dict:
        """Gera linha para CSV de auditoria (preview truncado a 250 chars)."""
        preview = self.trecho[:250].replace("\n", " ").strip() if self.trecho else ""
        return {
            "caminho_pdf": Path(self.caminho_pdf).name if self.caminho_pdf else "",
            "tipo_documento": self.tipo_documento,
            "variation_tag": self.variation_tag,
            "estrategia_usada": self.estrategia_usada,
            "heading_encontrado": self.heading_encontrado,
            "heading_audit": self.heading_audit[:80],
            "fallback_usado": self.fallback_usado,
            "embedding_usado": self.embedding_usado,
            "pattern_match": self.pattern_match[:100] if self.pattern_match else "",
            "pagina_heading": self.pagina_heading,
            "paginas_total": self.paginas_total,
            "paginas_conteudo": self.paginas_conteudo,
            "capa_trf1_detectada": self.capa_trf1_detectada,
            "chars_texto_bruto": self.chars_texto_bruto,
            "chars_texto_limpo": self.chars_texto_limpo,
            "chars_extraidos": self.chars_extraidos,
            "quality_alpha_ratio": round(self.quality_alpha_ratio, 3),
            "status": self.status,
            "trecho_preview": preview,
        }

    def to_relatorio(self) -> Optional[RelatorioExtracao]:
        """Converte para RelatorioExtracao (API pública). Retorna None se vazio/erro."""
        if self.status in ("documento_vazio", "erro_abertura", "tipo_nao_suportado"):
            return None
        return RelatorioExtracao(
            caminho_pdf=self.caminho_pdf,
            tipo_documento=TipoDocumento(self.tipo_documento),
            estrategia_usada=self.estrategia_usada,
            heading_encontrado=self.heading_encontrado,
            fallback_usado=self.fallback_usado,
            pattern_match=self.pattern_match,
            chars_extraidos=self.chars_extraidos,
            paginas_analisadas=self.paginas_total,
            trecho=self.trecho,
            erro=self.erro if self.status in ("texto_ilegivel", "revisar") else None,
        )


# ============================================
# DETECÇÃO DE CAPA TRF1 (por conteúdo)
# ============================================

_RE_CAPA_JF = re.compile(r"Justi[cç]a\s+Federal\s+da\s+1", re.IGNORECASE)
_RE_CAPA_PJE = re.compile(r"PJe\s*-\s*Processo\s+Judicial\s+Eletr[oô]nico", re.IGNORECASE)
_RE_CAPA_PARTES = re.compile(r"Partes\s+Procurador", re.IGNORECASE)


def _is_capa_trf1(page_text: str) -> bool:
    topo = page_text[:600]
    if _RE_CAPA_JF.search(topo) and _RE_CAPA_PJE.search(topo):
        return True
    if _RE_CAPA_JF.search(topo) and _RE_CAPA_PARTES.search(page_text[:1500]):
        return True
    return False


# ============================================
# LIMPEZA DE TEXTO
# ============================================

_PATTERNS_RUIDO = [
    re.compile(r"^Assinado eletronicamente por:.*$", re.MULTILINE),
    re.compile(r"^https?://pje1g\.trf1\.jus\.br.*$", re.MULTILINE),
    re.compile(r"^Número do documento:.*$", re.MULTILINE),
    re.compile(r"Num\.\s*\d+\s*-\s*Pág\.\s*\d+", re.MULTILINE),
    re.compile(r"^Documento id \d+ - .*$", re.MULTILINE),
    re.compile(r"^[_]{10,}$", re.MULTILINE),
    re.compile(r"^PODER JUDICIÁRIO\s*$", re.MULTILINE),
    re.compile(r"^JUSTIÇA FEDERAL\s*$", re.MULTILINE),
    re.compile(r"^Seção Judiciária d[eo].*$", re.MULTILINE),
    re.compile(r"^\d+ª?\s*Vara Federal.*$", re.MULTILINE),
]

_PATTERNS_ESCRITORIO = [
    re.compile(r"^(?:AMARAL E AMARAL|VIEIRA DA ROCHA|BENEVIDES|FROTA)"
               r"(?:\s+(?:ADVOGADOS|ASSOCIADOS|E\s+\w+))*.*$",
               re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*A\s*D\s*V\s*O\s*G\s*A\s*D\s*O\s*S\s*$", re.MULTILINE),
    re.compile(r"^(?:Av\.|Rua)\s+(?:Coronel Teodolino|Agnelo de Brito|"
               r"Belo Horizonte|Arizona|Cometa Halley).*$", re.MULTILINE),
    re.compile(r"^Cidade Monções.*$", re.MULTILINE),
    re.compile(r"^Aleixo\s*-\s*69.*Manaus.*$", re.MULTILINE),
    re.compile(r"^www\.vrbf\.com\.br$", re.MULTILINE),
]


def _limpar_texto(texto: str) -> str:
    for p in _PATTERNS_RUIDO:
        texto = p.sub("", texto)
    for p in _PATTERNS_ESCRITORIO:
        texto = p.sub("", texto)
    texto = re.sub(r"\n{3,}", "\n\n", texto)
    return texto.strip()


# ============================================
# QUALITY GATE
# ============================================

def _alpha_ratio(texto: str) -> float:
    if not texto:
        return 0.0
    alpha = sum(1 for c in texto if c.isalpha())
    total = len(texto.replace(" ", "").replace("\n", ""))
    return alpha / total if total > 0 else 0.0


def _aplicar_quality_gate(perfil: PerfilPDF) -> None:
    perfil.quality_alpha_ratio = _alpha_ratio(perfil.trecho)

    if len(perfil.trecho) < MIN_CHARS_TRECHO_VALIDO:
        if perfil.status == "ok":
            perfil.status = "revisar"
            perfil.erro = f"trecho_curto_{len(perfil.trecho)}_chars"
        return

    if perfil.quality_alpha_ratio < MIN_ALPHA_RATIO:
        perfil.status = "texto_ilegivel"
        perfil.erro = f"alpha_ratio_{perfil.quality_alpha_ratio:.2f}"


# ============================================
# DECISÃO — HEADING DETECTION
# ============================================

_RE_DECISAO = re.compile(r"^\s*DECIS[AÃ]O\s*\.?\s*$", re.IGNORECASE)
_RE_DESPACHO = re.compile(r"^\s*DESPACHO\s*/\s*DECIS[AÃ]O\s*$", re.IGNORECASE)
_RE_DECIDO = re.compile(r"^\s*(?:Fundamento\s+e\s+)?decido\s*\.\s*$", re.IGNORECASE)

_ANCHORS_DECISAO = [
    re.compile(r"Trata-se\s+de\s+(?:Mandado|a[cç][aã]o)", re.IGNORECASE),
    re.compile(r"Cuida-se\s+de", re.IGNORECASE),
    re.compile(r"A\s+quest[aã]o\s+controvertida", re.IGNORECASE),
    re.compile(r"Busca\s+a\s+impetrante", re.IGNORECASE),
    re.compile(r"Cumprir\s+decis[aã]o\s+judicial", re.IGNORECASE),
    re.compile(r"O\s+caso\s+[eé]\s+somente\s+de", re.IGNORECASE),
]


def _texto_apos_linha(paginas: list[str], pg_idx: int, line_idx: int, n_chars: int) -> str:
    lines = paginas[pg_idx].split("\n")
    after = "\n".join(lines[line_idx + 1:])
    for pg in paginas[pg_idx + 1:]:
        after += "\n" + pg
    return _limpar_texto(after[:n_chars]).strip()


def _buscar_heading_decisao(paginas: list[str], n_chars: int):
    """Busca heading DECISÃO (frente→fundo). Retorna (trecho, pg, heading, tag) ou None."""
    checks = [
        (_RE_DECISAO, "decisao_heading_decisao", True),
        (_RE_DESPACHO, "decisao_heading_despacho_decisao", True),
        (_RE_DECIDO, "decisao_heading_decido", False),
    ]
    for pattern, tag, space_norm in checks:
        for pi, page_text in enumerate(paginas):
            for i, line in enumerate(page_text.split("\n")):
                test = re.sub(r"\s+", "", line.strip()) if space_norm else line.strip()
                if pattern.match(test):
                    trecho = _texto_apos_linha(paginas, pi, i, n_chars)
                    return (trecho, pi + 1, line.strip(), tag)
    return None


def _buscar_anchor_decisao(paginas: list[str], n_chars: int):
    """Busca anchor semântico DECISÃO (frente→fundo). Retorna (trecho, pg, anchor) ou None."""
    for pi, page_text in enumerate(paginas):
        for anchor in _ANCHORS_DECISAO:
            m = anchor.search(page_text)
            if m:
                after = page_text[m.start():]
                for pg in paginas[pi + 1:]:
                    after += "\n" + pg
                return (_limpar_texto(after[:n_chars]).strip(), pi + 1, m.group())
    return None


# ============================================
# PETIÇÃO — HEADING DETECTION (auditoria)
# ============================================

_PETICAO_HEADING_PATTERNS = [
    (re.compile(r"^\s*(?:(?:\d+|[IVXLC]+)\s*[-–.]\s*)?(?:D[OA]S?\s*PEDIDO[S]?|O\s*PEDIDO)\s*$",
                re.IGNORECASE), "pedido"),
    (re.compile(r"^\s*(?:(?:\d+|[IVXLC]+)\s*[-–.]\s*)?(?:D?[OA]S?\s*REQUERIMENTO[S]?)\s*$",
                re.IGNORECASE), "requerimentos"),
    (re.compile(r"^\s*(?:(?:\d+|[IVXLC]+)\s*[-–.]\s*)?D[OA]S?\s*PLEITO[S]?\s*$",
                re.IGNORECASE), "pleito"),
    (re.compile(r"^\s*(?:(?:\d+|[IVXLC]+)\s*[-–.]\s*)?"
                r"DA\s+PRESTA[CÇ][AÃ]O\s+JURISDICIONAL\s+REQUERIDA\s*$",
                re.IGNORECASE), "prestacao_jurisdicional"),
    (re.compile(r"^\s*PEDIDO[S]?\s*$", re.IGNORECASE), "pedido_solto"),
]


def _audit_heading_peticao(paginas: list[str]) -> tuple[str, int, str]:
    """Busca heading PETIÇÃO para auditoria (reverso). Retorna (heading, pg, familia)."""
    for pi in range(len(paginas) - 1, -1, -1):
        for line in paginas[pi].split("\n"):
            for pattern, familia in _PETICAO_HEADING_PATTERNS:
                if pattern.match(line.strip()):
                    return (line.strip(), pi + 1, familia)
    return ("", 0, "")


# ============================================
# EMBEDDING FALLBACK
# ============================================

_EMBEDDING_QUERIES = {
    "DECISAO": [
        "trecho onde o juiz decide o pedido",
        "trecho com deferimento indeferimento ou determinação judicial",
    ],
    "PETICAO": [
        "trecho onde o autor faz o pedido ao juiz",
        "trecho com os requerimentos finais da petição",
    ],
}


def _embedding_fallback(texto_limpo: str, tipo: str, n_chars: int) -> Optional[tuple[str, float]]:
    """Fallback semântico via OpenAI embeddings. Retorna (trecho, score) ou None."""
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        print("[EXTRATOR] ⚠ OPENAI_API_KEY não definida — embedding indisponível")
        return None

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
    except Exception as e:
        print(f"[EXTRATOR] ⚠ OpenAI init error: {e}")
        return None

    # Chunking com overlap
    overlap = 300
    chunks = []
    if len(texto_limpo) <= n_chars:
        chunks = [texto_limpo]
    else:
        pos = 0
        while pos < len(texto_limpo):
            chunk = texto_limpo[pos:pos + n_chars]
            if len(chunk.strip()) > MIN_CHARS_TRECHO_VALIDO:
                chunks.append(chunk)
            pos += n_chars - overlap

    if not chunks:
        return None

    queries = _EMBEDDING_QUERIES.get(tipo, [])
    if not queries:
        return None

    try:
        all_texts = queries + chunks
        response = client.embeddings.create(model="text-embedding-3-small", input=all_texts)
        embeddings = [item.embedding for item in response.data]
        q_embs = embeddings[:len(queries)]
        c_embs = embeddings[len(queries):]

        def cosine(a, b):
            dot = sum(x * y for x, y in zip(a, b))
            na = math.sqrt(sum(x * x for x in a))
            nb = math.sqrt(sum(x * x for x in b))
            return dot / (na * nb) if na and nb else 0.0

        best_score, best_idx = -1.0, 0
        for qe in q_embs:
            for ci, ce in enumerate(c_embs):
                s = cosine(qe, ce)
                if s > best_score:
                    best_score = s
                    best_idx = ci

        print(f"[EXTRATOR] Embedding: chunk={best_idx}/{len(chunks)}, score={best_score:.3f}")
        return (chunks[best_idx].strip(), best_score)

    except Exception as e:
        print(f"[EXTRATOR] ⚠ Embedding error: {e}")
        return None


# ============================================
# PIPELINE PRINCIPAL
# ============================================

def perfilar_pdf(caminho_pdf: str, tipo_documento: TipoDocumento) -> PerfilPDF:
    """
    Perfila e extrai trecho relevante de um PDF judicial.

    DECISÃO: heading → anchor → embedding → fallback → quality gate
    PETIÇÃO: últimos N chars limpos → quality gate → embedding se falha
    """
    perfil = PerfilPDF(caminho_pdf=caminho_pdf, tipo_documento=tipo_documento.value)
    path = Path(caminho_pdf)

    # --- Abrir PDF ---
    if not path.exists():
        perfil.status = "erro_abertura"
        perfil.erro = "arquivo_nao_encontrado"
        _log(perfil)
        return perfil

    try:
        doc = fitz.open(str(path))
    except Exception as e:
        perfil.status = "erro_abertura"
        perfil.erro = str(e)[:200]
        _log(perfil)
        return perfil

    perfil.paginas_total = len(doc)

    # --- Extrair texto, filtrar capas ---
    paginas_bruto = []
    capa = False
    for page in doc:
        pt = page.get_text("text") or ""
        if _is_capa_trf1(pt):
            capa = True
            continue
        paginas_bruto.append(pt)
    doc.close()

    perfil.capa_trf1_detectada = capa
    perfil.paginas_conteudo = len(paginas_bruto)
    texto_bruto = "\n".join(paginas_bruto)
    perfil.chars_texto_bruto = len(texto_bruto)

    # --- Check vazio (pré-limpeza) ---
    if len(texto_bruto.strip()) < MIN_CHARS_DOCUMENTO_UTIL:
        perfil.status = "documento_vazio"
        perfil.variation_tag = f"{tipo_documento.value.lower()}_vazio"
        _log(perfil)
        return perfil

    # --- Limpar ---
    texto_limpo = _limpar_texto(texto_bruto)
    perfil.chars_texto_limpo = len(texto_limpo)
    perfil._texto_limpo = texto_limpo

    # --- Check vazio (pós-limpeza) ---
    if len(texto_limpo.strip()) < MIN_CHARS_DOCUMENTO_UTIL:
        perfil.status = "documento_vazio"
        perfil.variation_tag = f"{tipo_documento.value.lower()}_vazio_apos_limpeza"
        _log(perfil)
        return perfil

    # --- Páginas limpas para busca page-aware ---
    paginas_limpas = [_limpar_texto(pt) for pt in paginas_bruto if len(_limpar_texto(pt).strip()) > 50]
    perfil._paginas_texto = paginas_limpas

    if not paginas_limpas:
        perfil.status = "documento_vazio"
        perfil.variation_tag = f"{tipo_documento.value.lower()}_vazio_todas_paginas"
        _log(perfil)
        return perfil

    # === EXTRAIR ===
    if tipo_documento == TipoDocumento.DECISAO:
        _pipeline_decisao(perfil)
    elif tipo_documento == TipoDocumento.PETICAO:
        _pipeline_peticao(perfil)
    elif tipo_documento == TipoDocumento.SENTENCA:
        _pipeline_decisao(perfil)
        perfil.variation_tag = perfil.variation_tag.replace("decisao", "sentenca")
        perfil.estrategia_usada = perfil.estrategia_usada.replace("DECISAO", "SENTENCA")
    else:
        perfil.status = "tipo_nao_suportado"
        _log(perfil)
        return perfil

    # --- Quality gate ---
    _aplicar_quality_gate(perfil)

    # --- Embedding safety net (se quality gate falhou) ---
    if perfil.status in ("texto_ilegivel", "revisar") and not perfil.embedding_usado:
        _tentar_embedding_safety(perfil)

    _log(perfil)
    return perfil


def _pipeline_decisao(perfil: PerfilPDF) -> None:
    """DECISÃO: heading → anchor → embedding → fallback posicional."""
    n = settings.EXTRACT_CHARS_DECISAO

    # 1. Heading
    r = _buscar_heading_decisao(perfil._paginas_texto, n)
    if r:
        perfil.trecho, perfil.pagina_heading, perfil.heading_texto_original, perfil.variation_tag = r
        perfil.heading_encontrado = True
        perfil.heading_audit = perfil.heading_texto_original
        perfil.estrategia_usada = "DECISAO.heading"
        perfil.pattern_match = perfil.heading_texto_original
        perfil.status = "ok"
        perfil.chars_extraidos = len(perfil.trecho)
        return

    # 2. Anchor
    r = _buscar_anchor_decisao(perfil._paginas_texto, n)
    if r:
        perfil.trecho, perfil.pagina_heading, anchor = r
        perfil.variation_tag = "decisao_anchor"
        perfil.estrategia_usada = "DECISAO.anchor"
        perfil.pattern_match = anchor
        perfil.fallback_usado = True
        perfil.status = "ok_com_fallback"
        perfil.chars_extraidos = len(perfil.trecho)
        return

    # 3. Embedding
    result = _embedding_fallback(perfil._texto_limpo, "DECISAO", n)
    if result:
        perfil.trecho = _limpar_texto(result[0]).strip()
        perfil.embedding_usado = True
        perfil.variation_tag = "decisao_embedding"
        perfil.estrategia_usada = "DECISAO.embedding"
        perfil.pattern_match = f"emb_score={result[1]:.3f}"
        perfil.fallback_usado = True
        perfil.status = "ok_com_fallback"
        perfil.chars_extraidos = len(perfil.trecho)
        return

    # 4. Fallback posicional
    perfil.trecho = perfil._texto_limpo[:n].strip()
    perfil.variation_tag = "decisao_fallback_inicio"
    perfil.estrategia_usada = "DECISAO.fallback_inicio"
    perfil.fallback_usado = True
    perfil.status = "ok_com_fallback"
    perfil.chars_extraidos = len(perfil.trecho)


def _pipeline_peticao(perfil: PerfilPDF) -> None:
    """PETIÇÃO: últimos N chars limpos. Heading é só auditoria."""
    n = settings.EXTRACT_CHARS_PETICAO

    # Auditoria de heading
    h_text, h_pg, h_familia = _audit_heading_peticao(perfil._paginas_texto)
    if h_text:
        perfil.heading_encontrado = True
        perfil.heading_audit = f"{h_familia}: {h_text}"
        perfil.heading_texto_original = h_text
        perfil.pagina_heading = h_pg

    # Extração: últimos N chars
    perfil.trecho = perfil._texto_limpo[-n:].strip()
    perfil.chars_extraidos = len(perfil.trecho)
    perfil.estrategia_usada = "PETICAO.positional"
    perfil.status = "ok"

    if h_text:
        perfil.variation_tag = f"peticao_positional_h_{h_familia}"
    else:
        perfil.variation_tag = "peticao_positional_sem_heading"


def _tentar_embedding_safety(perfil: PerfilPDF) -> None:
    """Embedding safety net: dispara quando quality gate falha."""
    tipo = perfil.tipo_documento
    n = settings.EXTRACT_CHARS_DECISAO if tipo == "DECISAO" else settings.EXTRACT_CHARS_PETICAO
    status_original = perfil.status

    result = _embedding_fallback(perfil._texto_limpo, tipo, n)
    if result:
        trecho, score = _limpar_texto(result[0]).strip(), result[1]
        new_ar = _alpha_ratio(trecho)

        if new_ar > perfil.quality_alpha_ratio and len(trecho) >= MIN_CHARS_TRECHO_VALIDO:
            perfil.trecho = trecho
            perfil.embedding_usado = True
            perfil.variation_tag = f"{tipo.lower()}_embedding"
            perfil.estrategia_usada = f"{tipo}.embedding"
            perfil.pattern_match = f"emb_score={score:.3f}"
            perfil.fallback_usado = True
            perfil.chars_extraidos = len(trecho)
            perfil.quality_alpha_ratio = new_ar
            perfil.status = "ok_com_fallback"
            print(f"[EXTRATOR] Embedding melhorou extração (alpha={new_ar:.2f})")
        else:
            perfil.status = status_original
    else:
        perfil.status = status_original


# ============================================
# LOGGING
# ============================================

def _log(perfil: PerfilPDF) -> None:
    tag = perfil.variation_tag or perfil.status
    c = perfil.chars_extraidos
    pg = f"pg{perfil.pagina_heading}" if perfil.pagina_heading else "—"
    s = perfil.status
    f = Path(perfil.caminho_pdf).name if perfil.caminho_pdf else "?"
    flags = ""
    if perfil.embedding_usado:
        flags += " [EMB]"
    if perfil.fallback_usado:
        flags += " [FB]"
    ar = f" ar={perfil.quality_alpha_ratio:.2f}" if perfil.quality_alpha_ratio else ""
    cl = f" limpo={perfil.chars_texto_limpo}" if perfil.chars_texto_limpo else ""
    ha = f" h={perfil.heading_audit[:25]}" if perfil.heading_audit else ""
    err = f" err={perfil.erro}" if perfil.erro else ""
    print(f"[EXTRATOR] {tag:50s} | {c:5d}c | {pg:5s} | {s}{flags}{cl}{ar}{ha}{err} | {f}")


# ============================================
# API PÚBLICA
# ============================================

def extrair_texto(caminho_pdf: str, tipo_documento: TipoDocumento,
                  cnpj: str = "", numero_processo: str = "") -> Optional[RelatorioExtracao]:
    """Extrai trecho relevante de um PDF judicial. Retorna None se documento vazio."""
    return perfilar_pdf(caminho_pdf, tipo_documento).to_relatorio()


def extrair_lote(registros: list, cnpj: str = "",
                 salvar_auditoria: bool = True) -> list[RelatorioExtracao]:
    """Extrai trechos de uma lista de RegistroDownload. Documentos vazios são excluídos."""
    perfis, resultados = [], []

    for reg in registros:
        perfil = perfilar_pdf(reg.caminho_pdf, reg.tipo_documento)
        perfis.append(perfil)
        r = perfil.to_relatorio()
        if r is not None:
            resultados.append(r)

    # --- Estatísticas ---
    total = len(registros)
    by_status, by_tag = {}, {}
    for p in perfis:
        by_status[p.status] = by_status.get(p.status, 0) + 1
        t = p.variation_tag or "sem_tag"
        by_tag[t] = by_tag.get(t, 0) + 1

    print(f"\n[EXTRATOR] === Resumo ({total} PDFs) ===")
    print(f"  Status:")
    for s, c in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"    {s:25s} {c:3d}  ({c / total * 100:5.1f}%)")
    print(f"  Variações:")
    for t, c in sorted(by_tag.items(), key=lambda x: -x[1]):
        print(f"    {t:50s} {c:3d}")

    embs = [p for p in perfis if p.embedding_usado]
    if embs:
        print(f"  Embeddings ({len(embs)}):")
        for p in embs:
            print(f"    {Path(p.caminho_pdf).name}")

    fbs = [p for p in perfis if p.fallback_usado and p.status != "documento_vazio"]
    if fbs:
        print(f"  Fallbacks ({len(fbs)}):")
        for p in fbs:
            print(f"    [{p.variation_tag}] {Path(p.caminho_pdf).name}")

    attn = [p for p in perfis if p.status in ("revisar", "texto_ilegivel")]
    if attn:
        print(f"  ⚠ Atenção ({len(attn)}):")
        for p in attn:
            print(f"    [{p.status}] {Path(p.caminho_pdf).name} — {p.erro}")

    if salvar_auditoria and perfis:
        csv_name = f"auditoria_extracao_{cnpj}.csv" if cnpj else "auditoria_extracao.csv"
        _salvar_auditoria(perfis, settings.DATA_SAIDA_DIR / csv_name)

    return resultados


def _salvar_auditoria(perfis: list[PerfilPDF], caminho_csv: Path) -> None:
    """Salva CSV de auditoria (sobrescreve — 1 arquivo por CNPJ)."""
    caminho_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho_csv, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=_AUDIT_COLUMNS, delimiter=";")
        writer.writeheader()
        for perfil in perfis:
            writer.writerow(perfil.to_audit_row())
    print(f"[EXTRATOR] Auditoria: {caminho_csv} ({len(perfis)} registros)")