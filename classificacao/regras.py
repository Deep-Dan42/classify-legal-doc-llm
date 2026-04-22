"""
automacao-juridica-trf1 — Camada 1: Classificação por Regras

Classificação determinística baseada em keywords extraídas do
mapeamento_tipo_servico.csv. Todos os keywords de uma regra devem
aparecer no texto para considerar match.

Uso:
    from classificacao.regras import ClassificadorRegras

    clf = ClassificadorRegras()          # carrega regras do CSV
    resultado = clf.classificar(texto)   # ResultadoClassificacao | None
"""
from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from core.input_loader import carregar_mapeamento, RegraMapeamento
from core.modelos import (
    MetodoClassificacao,
    NivelConfianca,
    ResultadoClassificacao,
)

logger = logging.getLogger(__name__)

# ============================================
# STOPWORDS — palavras funcionais do português
# que não carregam semântica relevante para match
# ============================================

STOPWORDS_PT: set[str] = {
    "a", "ao", "aos", "as", "à", "às",
    "com", "como",
    "da", "das", "de", "do", "dos",
    "e", "em", "entre",
    "na", "nas", "no", "nos",
    "o", "os",
    "ou",
    "para", "pela", "pelas", "pelo", "pelos", "por",
    "que",
    "se", "seu", "sua",
    "um", "uma",
}


# ============================================
# NORMALIZAÇÃO DE TEXTO
# ============================================

_RE_WHITESPACE = re.compile(r"\s+")


def _remover_acentos(texto: str) -> str:
    """Remove acentos (á→a, ç→c, etc.) para matching robusto."""
    nfkd = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _normalizar(texto: str) -> str:
    """Lowercase, remove acentos, colapsa espaços."""
    t = texto.lower()
    t = _remover_acentos(t)
    t = _RE_WHITESPACE.sub(" ", t).strip()
    return t


def _extrair_keywords(texto: str) -> list[str]:
    """
    Extrai keywords relevantes de um texto:
    normaliza, tokeniza por espaço, remove stopwords e tokens curtos (≤1 char).
    """
    normalizado = _normalizar(texto)
    tokens = normalizado.split()
    return [t for t in tokens if t not in STOPWORDS_PT and len(t) > 1]


# ============================================
# REGRA COMPILADA
# ============================================

@dataclass(frozen=True)
class RegraCompilada:
    """Regra pré-processada para matching rápido."""
    texto_pdf_original: str
    tipo_de_servico: str
    keywords: tuple[str, ...]       # keywords normalizadas (sem stopwords)
    n_keywords: int                 # len(keywords) — pré-calculado

    @classmethod
    def from_mapeamento(cls, regra: RegraMapeamento) -> "RegraCompilada":
        kw = _extrair_keywords(regra.texto_pdf)
        return cls(
            texto_pdf_original=regra.texto_pdf,
            tipo_de_servico=regra.tipo_de_servico,
            keywords=tuple(kw),
            n_keywords=len(kw),
        )


# ============================================
# RESULTADO DE MATCH INTERNO
# ============================================

@dataclass
class _MatchInfo:
    """Informação interna de um match (para desempate)."""
    regra: RegraCompilada
    keywords_encontradas: int       # quantas keywords da regra aparecem no texto
    proporcao: float                # keywords_encontradas / n_keywords


# ============================================
# CLASSIFICADOR
# ============================================

class ClassificadorRegras:
    """
    Camada 1 — classificação determinística por keywords.

    Carrega regras do mapeamento_tipo_servico.csv, extrai keywords de cada
    regra e busca match completo (todas as keywords presentes) no texto.
    """

    def __init__(self, regras: Optional[List[RegraMapeamento]] = None, path: Optional[Path] = None) -> None:
        """
        Args:
            regras: lista de RegraMapeamento. Se None, carrega do CSV.
            path: caminho do CSV de regras. Se None, usa settings.MAPEAMENTO_CSV.
        """
        raw = regras if regras is not None else carregar_mapeamento(path)
        self._regras: list[RegraCompilada] = []

        for r in raw:
            compilada = RegraCompilada.from_mapeamento(r)
            if compilada.n_keywords == 0:
                logger.warning(
                    "Regra ignorada (0 keywords após stopwords): '%s'",
                    r.texto_pdf,
                )
                continue
            self._regras.append(compilada)

        logger.info(
            "ClassificadorRegras: %d regras carregadas (%d keywords únicas no total)",
            len(self._regras),
            len({kw for r in self._regras for kw in r.keywords}),
        )

    @property
    def n_regras(self) -> int:
        return len(self._regras)

    def classificar(self, texto: str) -> Optional[ResultadoClassificacao]:
        """
        Tenta classificar um trecho de texto usando as regras determinísticas.

        Args:
            texto: texto extraído de um documento (DECISÃO ou PETIÇÃO).

        Returns:
            ResultadoClassificacao com confianca=ALTA e metodo=REGRA se match,
            None se nenhuma regra fez match.
        """
        if not texto or not texto.strip():
            return None

        texto_norm = _normalizar(texto)

        # Fase 1: encontrar todas as regras com match completo
        matches: list[_MatchInfo] = []

        for regra in self._regras:
            encontradas = sum(1 for kw in regra.keywords if kw in texto_norm)

            if encontradas == regra.n_keywords:
                matches.append(_MatchInfo(
                    regra=regra,
                    keywords_encontradas=encontradas,
                    proporcao=1.0,
                ))

        if not matches:
            return None

        # Fase 2: desempate (raro — regras devem ser únicas)
        if len(matches) > 1:
            logger.warning(
                "Múltiplas regras fizeram match (%d). Usando desempate por n_keywords > len(texto_pdf).",
                len(matches),
            )
            matches.sort(
                key=lambda m: (m.regra.n_keywords, len(m.regra.texto_pdf_original)),
                reverse=True,
            )

        melhor = matches[0]

        return ResultadoClassificacao(
            tipo_de_servico=melhor.regra.tipo_de_servico,
            confianca=NivelConfianca.ALTA,
            metodo=MetodoClassificacao.REGRA,
            regra_match=melhor.regra.texto_pdf_original,
        )

    def resumo(self) -> str:
        """Resumo legível das regras carregadas."""
        linhas = [f"[REGRAS] {len(self._regras)} regras carregadas:"]
        for r in self._regras:
            linhas.append(f"  {r.tipo_de_servico:40s} ← {r.n_keywords} keywords: {', '.join(r.keywords[:5])}{'...' if r.n_keywords > 5 else ''}")
        return "\n".join(linhas)