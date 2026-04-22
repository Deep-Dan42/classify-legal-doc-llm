"""
automacao-juridica-trf1 — Gap Analysis

Lógica central do produto:
    LISTA MESTRA (todos os serviços do escritório)
      MENOS (−)
    SERVIÇOS ENCONTRADOS nos documentos do CNPJ
      IGUAL (=)
    OPORTUNIDADES DE PROSPECÇÃO

Regras:
    - Itens com confiança REVISÃO NÃO contam como encontrados (conservador)
    - Resolver revisão → recalcular gap automaticamente
    - Gap ≥ 0 sempre (validação lógica)

Uso:
    from core.gap_analysis import calcular_gap, GapResult

    resultado = calcular_gap(
        servicos_encontrados={"PIS COFINS Exclusão ISS", "REINTEGRA Ampliação"},
        servicos_revisao={"Defesa em Auto de Infração"},
    )
    print(f"{resultado.n_oportunidades} oportunidades")
    for op in resultado.oportunidades:
        print(f"  - {op.servico_disponivel}")
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from core.input_loader import carregar_lista_servicos, nomes_teses
from core.modelos import (
    NivelConfianca,
    Oportunidade,
    TeseMestra,
)

logger = logging.getLogger(__name__)


# ============================================
# RESULTADO DO GAP
# ============================================

@dataclass
class GapResult:
    """Resultado completo do gap analysis para um CNPJ."""
    # Dados da empresa (preenchidos pelo chamador)
    empresa: str = ""
    cnpj: str = ""
    cidade_uf_matriz: str = ""
    atividade_principal: str = ""
    capital_social: str = ""

    # Conjuntos
    total_teses: int = 0
    servicos_encontrados: set = field(default_factory=set)
    servicos_revisao: set = field(default_factory=set)

    # Oportunidades
    oportunidades: list[Oportunidade] = field(default_factory=list)

    @property
    def n_oportunidades(self) -> int:
        return len(self.oportunidades)

    @property
    def n_encontrados(self) -> int:
        return len(self.servicos_encontrados)

    @property
    def n_revisao(self) -> int:
        return len(self.servicos_revisao)

    def resumo(self) -> str:
        return (
            f"[GAP ANALYSIS] {self.cnpj or '(CNPJ não definido)'}\n"
            f"  Total teses na lista mestra: {self.total_teses}\n"
            f"  Serviços encontrados:        {self.n_encontrados}\n"
            f"  Aguardando revisão:          {self.n_revisao}\n"
            f"  Oportunidades:               {self.n_oportunidades}\n"
            f"  ---\n"
            f"  Verificação: {self.n_encontrados} + {self.n_oportunidades} + {self.n_revisao} = "
            f"{self.n_encontrados + self.n_oportunidades + self.n_revisao} "
            f"(deve ser ≤ {self.total_teses})"
        )


# ============================================
# CALCULAR GAP
# ============================================

def calcular_gap(
    servicos_encontrados: set[str],
    servicos_revisao: Optional[set[str]] = None,
    dados_empresa: Optional[dict] = None,
    teses: Optional[list[TeseMestra]] = None,
) -> GapResult:
    """
    Calcula oportunidades de prospecção.

    Args:
        servicos_encontrados: set de nomes de teses classificadas com confiança
                              ALTA ou LLM (confirmadas).
        servicos_revisao: set de nomes de teses com confiança REVISÃO
                          (NÃO contam como encontradas — conservador).
        dados_empresa: dict com metadados da empresa (empresa, cnpj, etc.)
        teses: lista de TeseMestra. Se None, carrega do CSV.

    Returns:
        GapResult com oportunidades e estatísticas.
    """
    if teses is None:
        teses = carregar_lista_servicos()

    servicos_revisao = servicos_revisao or set()
    dados_empresa = dados_empresa or {}

    # Normalizar para comparação case-insensitive
    encontrados_lower = {s.lower() for s in servicos_encontrados}
    revisao_lower = {s.lower() for s in servicos_revisao}

    # Dados da empresa para preencher oportunidades
    empresa = dados_empresa.get("empresa", "")
    cnpj = dados_empresa.get("cnpj", "")
    cidade_uf = dados_empresa.get("cidade_uf_matriz", "")
    atividade = dados_empresa.get("atividade_principal", "")
    capital = dados_empresa.get("capital_social", "")

    oportunidades: list[Oportunidade] = []

    for tese in teses:
        tese_lower = tese.tese.lower()

        # Encontrado → não é oportunidade
        if tese_lower in encontrados_lower:
            continue

        # Em revisão → não é oportunidade AINDA (conservador)
        if tese_lower in revisao_lower:
            continue

        # Gap: tese não encontrada → oportunidade
        oportunidades.append(Oportunidade(
            empresa=empresa,
            cnpj=cnpj,
            cidade_uf_matriz=cidade_uf,
            atividade_principal=atividade,
            capital_social=capital,
            servico_disponivel=tese.tese,
            area_responsavel=tese.area_responsavel,
            ramo_de_atividade=" | ".join(tese.ramo_de_atividade),
            regime_tributario=" | ".join(tese.regime_tributario),
            objeto_da_tese=tese.objeto_da_tese,
            observacao="",
        ))

    resultado = GapResult(
        empresa=empresa,
        cnpj=cnpj,
        cidade_uf_matriz=cidade_uf,
        atividade_principal=atividade,
        capital_social=capital,
        total_teses=len(teses),
        servicos_encontrados=servicos_encontrados,
        servicos_revisao=servicos_revisao,
        oportunidades=oportunidades,
    )

    logger.info(
        "Gap analysis: %d teses, %d encontrados, %d revisão → %d oportunidades",
        len(teses), len(servicos_encontrados), len(servicos_revisao),
        len(oportunidades),
    )

    return resultado


def recalcular_gap(
    gap_anterior: GapResult,
    novos_encontrados: Optional[set[str]] = None,
    novos_revisao: Optional[set[str]] = None,
    teses: Optional[list[TeseMestra]] = None,
) -> GapResult:
    """
    Recalcula gap após resolução de itens de revisão.

    Usado quando o operador confirma ou reclassifica itens na tela de revisão.
    Mantém dados da empresa do gap anterior.

    Args:
        gap_anterior: resultado anterior do gap analysis.
        novos_encontrados: itens de revisão confirmados (viram encontrados).
        novos_revisao: itens que permanecem em revisão.
        teses: lista mestra. Se None, carrega do CSV.
    """
    encontrados = set(gap_anterior.servicos_encontrados)
    revisao = set(gap_anterior.servicos_revisao)

    if novos_encontrados:
        encontrados.update(novos_encontrados)
        revisao -= novos_encontrados

    if novos_revisao is not None:
        revisao = novos_revisao

    dados = {
        "empresa": gap_anterior.empresa,
        "cnpj": gap_anterior.cnpj,
        "cidade_uf_matriz": gap_anterior.cidade_uf_matriz,
        "atividade_principal": gap_anterior.atividade_principal,
        "capital_social": gap_anterior.capital_social,
    }

    return calcular_gap(
        servicos_encontrados=encontrados,
        servicos_revisao=revisao,
        dados_empresa=dados,
        teses=teses,
    )