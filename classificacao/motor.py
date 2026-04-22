"""
automacao-juridica-trf1 — Motor de Classificação (v3)

Orquestra: Regras → LLM → REVISÃO
Process-level aggregation: PETIÇÃO is classified first (anchor),
other documents in the same process must match or go to REVISÃO.

Auto-learning: LLM palavras_chave are suggested (not auto-appended).
Operator approves before they become deterministic rules.

Uso:
    from classificacao.motor import MotorClassificacao

    motor = MotorClassificacao()
    resultado = motor.classificar_documento(texto)
    print(motor.diagnostico())
"""
from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from classificacao.regras import ClassificadorRegras
from classificacao.llm_classificador import ClassificadorLLM
from core.config import settings
from core.input_loader import carregar_mapeamento, nomes_teses, carregar_lista_servicos
from core.modelos import (
    MetodoClassificacao,
    NivelConfianca,
    RelatorioExtracao,
    ResultadoClassificacao,
)

logger = logging.getLogger(__name__)


# ============================================
# ESTATÍSTICAS
# ============================================

@dataclass
class EstatisticasMotor:
    total_documentos: int = 0
    camada1_regras: int = 0
    camada2_llm: int = 0
    revisao: int = 0
    erros: int = 0
    regras_sugeridas: int = 0

    def resumo(self) -> str:
        return (
            f"[MOTOR] Estatísticas:\n"
            f"  Total documentos:  {self.total_documentos}\n"
            f"  Camada 1 (Regras): {self.camada1_regras}\n"
            f"  Camada 2 (LLM):    {self.camada2_llm}\n"
            f"  Revisão:           {self.revisao}\n"
            f"  Erros:             {self.erros}\n"
            f"  Regras sugeridas:  {self.regras_sugeridas}"
        )


# ============================================
# REGRA SUGERIDA (para aprovação do operador)
# ============================================

@dataclass
class RegraSugerida:
    """Regra sugerida pelo LLM, aguardando aprovação do operador."""
    palavras_chave: str
    tipo_de_servico: str
    origem_pdf: str = ""
    numero_processo: str = ""


# ============================================
# CARREGAR INICIAIS DO CSV
# ============================================

def _carregar_iniciais() -> dict[str, str]:
    """Lê coluna Inicial de lista_servicos.csv."""
    csv_path = settings.LISTA_SERVICOS_CSV
    if not csv_path.exists():
        return {}

    iniciais: dict[str, str] = {}
    with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        for row in reader:
            tese = (row.get("Tese") or "").strip()
            inicial = (row.get("Inicial") or "").strip()
            if tese and inicial:
                inicial = " ".join(inicial.replace("\r", "").split())
                iniciais[tese] = inicial

    logger.info("Iniciais carregadas: %d teses", len(iniciais))
    return iniciais


# ============================================
# APPEND REGRA AO CSV (para auto-aprender)
# ============================================

def _append_regra_csv(
    trecho_chave: str,
    tipo_de_servico: str,
    csv_path: Path,
) -> bool:
    """Adiciona regra ao CSV. Verifica duplicatas. Retorna True se adicionou."""
    trecho_limpo = trecho_chave.strip()
    if not trecho_limpo or not tipo_de_servico.strip():
        return False

    existentes: set[str] = set()
    if csv_path.exists():
        with csv_path.open("r", newline="", encoding="utf-8-sig") as f:
            first_line = f.readline()
            f.seek(0)
            delimiter = ";" if ";" in first_line else ","
            reader = csv.reader(f, delimiter=delimiter)
            next(reader, None)
            for row in reader:
                if row:
                    existentes.add(row[0].strip().lower())

    if trecho_limpo.lower() in existentes:
        return False

    # Garantir newline antes de append
    if csv_path.exists() and csv_path.stat().st_size > 0:
        with csv_path.open("rb") as f:
            f.seek(-1, 2)
            if f.read(1) not in (b"\n", b"\r"):
                with csv_path.open("a", encoding="utf-8") as fa:
                    fa.write("\n")

    with csv_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow([trecho_limpo, tipo_de_servico.strip()])

    logger.info("Nova regra: '%s' → '%s'", trecho_limpo[:60], tipo_de_servico)
    return True


# ============================================
# MOTOR DE CLASSIFICAÇÃO
# ============================================

class MotorClassificacao:
    """
    Orquestrador: Regras → LLM → REVISÃO.

    Process-level: PETIÇÃO classified first as anchor.
    Auto-learning: regras sugeridas pelo LLM, operador aprova.
    """

    def __init__(
        self,
        mapeamento_csv: Optional[Path] = None,
        auto_aprender: bool = True,
    ) -> None:
        self._mapeamento_csv = mapeamento_csv or settings.MAPEAMENTO_CSV
        self._auto_aprender = auto_aprender

        # Camada 1
        self._regras = ClassificadorRegras(path=self._mapeamento_csv)

        # Camada 2
        teses = carregar_lista_servicos()
        self._nomes_teses = nomes_teses(teses)
        iniciais = _carregar_iniciais()
        self._llm = ClassificadorLLM(teses=teses, iniciais=iniciais)

        # State
        self.stats = EstatisticasMotor()
        self.regras_sugeridas: list[RegraSugerida] = []

        # Process-level tracking: {numero_processo: tipo_de_servico}
        self._classificacao_por_processo: dict[str, str] = {}

        logger.info(
            "Motor: %d regras, %d teses, auto_aprender=%s",
            self._regras.n_regras, len(self._nomes_teses), auto_aprender,
        )

    def classificar_documento(
        self,
        texto: str,
        numero_processo: str = "",
        tipo_documento: str = "",
        caminho_pdf: str = "",
    ) -> Optional[ResultadoClassificacao]:
        """
        Classifica um documento. Respects process-level constraint:
        if the process already has a classification (from PETIÇÃO),
        this document must match or go to REVISÃO.
        """
        self.stats.total_documentos += 1

        if not texto or not texto.strip():
            self.stats.erros += 1
            return None

        # --- Check process-level constraint ---
        tipo_ja_definido = self._classificacao_por_processo.get(numero_processo)

        # --- Camada 1: Regras ---
        resultado = self._regras.classificar(texto)
        if resultado is not None:
            # Validate against process constraint
            if tipo_ja_definido and resultado.tipo_de_servico != tipo_ja_definido:
                logger.info(
                    "Regra match '%s' difere do processo '%s' → REVISÃO",
                    resultado.tipo_de_servico, tipo_ja_definido,
                )
                self.stats.revisao += 1
                return ResultadoClassificacao(
                    tipo_de_servico="REVISAO",
                    confianca=NivelConfianca.REVISAO,
                    metodo=MetodoClassificacao.FALLBACK,
                    razao_llm=f"Regra sugere '{resultado.tipo_de_servico}' mas processo já definido como '{tipo_ja_definido}'",
                )

            self.stats.camada1_regras += 1
            if numero_processo and not tipo_ja_definido:
                self._classificacao_por_processo[numero_processo] = resultado.tipo_de_servico
            return resultado

        # --- Camada 2: LLM ---
        try:
            resultado = self._llm.classificar(texto)
        except Exception as e:
            logger.error("Erro LLM: %s", e)
            self.stats.erros += 1
            resultado = None

        if resultado is not None:
            # Validate against process constraint
            if tipo_ja_definido and resultado.tipo_de_servico != tipo_ja_definido:
                logger.info(
                    "LLM match '%s' difere do processo '%s' → REVISÃO",
                    resultado.tipo_de_servico, tipo_ja_definido,
                )
                self.stats.revisao += 1
                return ResultadoClassificacao(
                    tipo_de_servico="REVISAO",
                    confianca=NivelConfianca.REVISAO,
                    metodo=MetodoClassificacao.FALLBACK,
                    razao_llm=f"LLM sugere '{resultado.tipo_de_servico}' mas processo já definido como '{tipo_ja_definido}'",
                )

            self.stats.camada2_llm += 1

            # Set process anchor
            if numero_processo and not tipo_ja_definido:
                self._classificacao_por_processo[numero_processo] = resultado.tipo_de_servico

            # Auto-learning: suggest rule (don't auto-append)
            if self._auto_aprender and resultado.regra_match:
                sugestao = RegraSugerida(
                    palavras_chave=resultado.regra_match,
                    tipo_de_servico=resultado.tipo_de_servico,
                    origem_pdf=caminho_pdf,
                    numero_processo=numero_processo,
                )
                self.regras_sugeridas.append(sugestao)
                self.stats.regras_sugeridas += 1
                logger.info(
                    "Regra SUGERIDA: '%s' → '%s' (aguardando aprovação)",
                    resultado.regra_match[:60], resultado.tipo_de_servico,
                )

            return resultado

        # --- REVISÃO ---
        self.stats.revisao += 1

        # Include LLM's analysis even though it didn't classify
        sugestao_texto = ""
        llm_info = getattr(self._llm, '_last_revisao_info', None)
        if llm_info:
            parts = []
            if llm_info.get("keywords"):
                parts.append(f"[Keywords detectados] {llm_info['keywords']}")
            if llm_info.get("parte"):
                parts.append(f"[Parte relevante] {llm_info['parte']}")
            if llm_info.get("razao"):
                parts.append(f"[Razão] {llm_info['razao']}")
            sugestao_texto = "\n".join(parts)

        return ResultadoClassificacao(
            tipo_de_servico="REVISAO",
            confianca=NivelConfianca.REVISAO,
            metodo=MetodoClassificacao.FALLBACK,
            razao_llm=sugestao_texto,
        )

    def aprovar_regra(self, idx: int) -> bool:
        """Operador aprova uma regra sugerida → append ao CSV."""
        if idx < 0 or idx >= len(self.regras_sugeridas):
            return False
        sugestao = self.regras_sugeridas[idx]
        ok = _append_regra_csv(
            sugestao.palavras_chave,
            sugestao.tipo_de_servico,
            self._mapeamento_csv,
        )
        if ok:
            self._regras = ClassificadorRegras(path=self._mapeamento_csv)
        return ok

    def aprovar_todas_regras(self) -> int:
        """Aprova todas as regras sugeridas. Returns count of added."""
        count = 0
        for i in range(len(self.regras_sugeridas)):
            if self.aprovar_regra(i):
                count += 1
        return count

    def diagnostico(self) -> str:
        partes = [
            self.stats.resumo(),
            "",
            self._regras.resumo(),
            "",
            self._llm.diagnostico(),
        ]
        if self.regras_sugeridas:
            partes.append("")
            partes.append(f"[REGRAS SUGERIDAS] {len(self.regras_sugeridas)} aguardando aprovação:")
            for i, s in enumerate(self.regras_sugeridas):
                partes.append(f"  [{i}] '{s.palavras_chave}' → '{s.tipo_de_servico}'")
        return "\n".join(partes)

    def recarregar_regras(self) -> None:
        self._regras = ClassificadorRegras(path=self._mapeamento_csv)
        logger.info("Regras recarregadas: %d", self._regras.n_regras)