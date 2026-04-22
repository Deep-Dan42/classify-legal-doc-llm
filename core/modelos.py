"""
automacao-juridica-trf1 — Modelos de dados

Pydantic models e enums usados em todo o pipeline.
Terminologia de domínio jurídico-tributário.

Uso:
    from core.modelos import (
        TipoDocumento, NivelConfianca, MetodoClassificacao,
        RegistroDownload, DadosEmpresa, RelatorioExtracao,
        ResultadoClassificacao, ItemRelatorio, Oportunidade,
    )
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field


# ============================================
# ENUMS
# ============================================

class TipoDocumento(str, Enum):
    """Tipos de documento-alvo para download e extração."""
    SENTENCA = "SENTENCA"
    DECISAO = "DECISAO"
    PETICAO = "PETICAO"


class NivelConfianca(str, Enum):
    """Nível de confiança da classificação (visível na UI como termos de negócio)."""
    ALTA = "ALTA"          # Regra exata → UI: "Confirmado"
    MEDIA = "MEDIA"        # Embedding similarity → UI: "Automático"
    LLM = "LLM"            # Classificação por LLM → UI: "Automático"
    REVISAO = "REVISAO"    # Nenhuma camada classificou → UI: "Pendente"


class MetodoClassificacao(str, Enum):
    """Método usado para classificação (técnico — não exposto na UI padrão)."""
    REGRA = "REGRA"
    EMBEDDING = "EMBEDDING"
    LLM = "LLM"
    FALLBACK = "FALLBACK"


# Mapeamento de termos técnicos → termos de negócio (para UI)
TERMOS_NEGOCIO = {
    # Confiança → display na UI
    NivelConfianca.ALTA: "Confirmado",
    NivelConfianca.MEDIA: "Automático",
    NivelConfianca.LLM: "Automático",
    NivelConfianca.REVISAO: "Pendente",

    # Status de progresso
    "loading_cnpjs": "Validando CNPJs...",
    "downloading": "Baixando documentos...",
    "extracting": "Extraindo trechos relevantes...",
    "classifying": "Classificando serviços...",
    "gap_analysis": "Identificando oportunidades...",
    "generating": "Gerando relatório...",
    "done": "Consulta concluída.",

    # Erros (sem jargão)
    "api_error": "Classificação automática temporariamente indisponível. Item adicionado à revisão.",
    "pdf_error": "Não foi possível ler este documento. Verifique o arquivo manualmente.",
    "login_error": "Sessão expirada. Faça login novamente pelo whom.doc9.",
    "no_results": "Nenhum processo encontrado para este CNPJ no TRF1.",
}


# ============================================
# MODELOS — DOWNLOAD
# ============================================

class RegistroDownload(BaseModel):
    """Uma linha no registro_de_downloads.csv."""
    cnpj: str
    numero_processo: str
    tipo_documento: TipoDocumento
    nome_documento: str
    caminho_pdf: str
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def chave_dedup(self) -> tuple:
        """Chave de unicidade para deduplicação de downloads."""
        return (self.cnpj, self.numero_processo, self.tipo_documento.value)


# ============================================
# MODELOS — EMPRESA
# ============================================

class DadosEmpresa(BaseModel):
    """Metadados da empresa extraídos da página de detalhe do processo no TRF1."""
    empresa: str = ""
    cnpj: str = ""
    cidade_uf_matriz: str = ""
    atividade_principal: str = ""
    atividade_secundaria: str = ""
    capital_social: str = ""
    local_processo: str = ""
    advogado: str = ""

    def esta_completo(self) -> bool:
        """Retorna True se pelo menos empresa e cnpj estão preenchidos."""
        return bool(self.empresa and self.cnpj)


# ============================================
# MODELOS — EXTRAÇÃO
# ============================================

class RelatorioExtracao(BaseModel):
    """Registro de como a extração foi feita para um PDF (para auditoria/validação)."""
    caminho_pdf: str
    tipo_documento: TipoDocumento
    estrategia_usada: str = ""          # Ex: "SENTENCA.after_heading"
    heading_encontrado: bool = False
    fallback_usado: bool = False
    pattern_match: str = ""             # Qual regex fez match
    chars_extraidos: int = 0
    paginas_analisadas: int = 1
    trecho: str = ""
    erro: Optional[str] = None


# ============================================
# MODELOS — CLASSIFICAÇÃO
# ============================================

class ResultadoClassificacao(BaseModel):
    """Resultado da classificação de um trecho extraído."""
    tipo_de_servico: str                # Valor do mapeamento ou "REVISAO"
    confianca: NivelConfianca
    metodo: MetodoClassificacao
    score: Optional[float] = None       # Score de embedding (Camada 2) ou None
    regra_match: Optional[str] = None   # Texto da regra que fez match (Camada 1) ou None
    razao_llm: Optional[str] = None     # Explicação do LLM (Camada 3) ou None
    sugestoes_embedding: Optional[list[dict]] = None  # Top-3 matches [{tipo, score}, ...] para tela de revisão


# ============================================
# MODELOS — LISTA MESTRA DE SERVIÇOS (TESES)
# ============================================

class TeseMestra(BaseModel):
    """
    Uma tese (serviço) da lista mestra do escritório.
    Carregada de data/entrada/lista_servicos.csv.
    Usada para gap analysis e filtros na UI.
    """
    tese: str                                       # Nome do serviço (coluna principal)
    area_responsavel: str = ""                      # Contencioso, Consultivo, Fiscal, Comercial
    objeto_da_tese: str = ""                        # Descrição do objetivo da tese
    estado: list[str] = Field(default_factory=list) # UFs aplicáveis (multi-valor)
    ramo_de_atividade: list[str] = Field(default_factory=list)   # Indústria, Comércio, etc. (multi-valor)
    regime_tributario: list[str] = Field(default_factory=list)   # Lucro Real, Presumido, etc. (multi-valor)
    tipo_produto_industrializa: str = ""            # Tipo de produto
    observacoes: str = ""
    clientes_possiveis: str = ""
    data_criacao: str = ""
    status: str = "Ativo"


# ============================================
# MODELOS — RELATÓRIO FINAL
# ============================================

class ItemRelatorio(BaseModel):
    """Uma linha no relatório final (aba 'Serviços Identificados')."""
    # Dados da empresa
    empresa: str = ""
    cnpj: str = ""
    cidade_uf_matriz: str = ""
    atividade_principal: str = ""
    atividade_secundaria: str = ""
    capital_social: str = ""

    # Dados do processo
    numero_processo: str = ""
    local_processo: str = ""
    advogado: str = ""
    tipo_processo: str = ""

    # Dados do documento
    tipo_documento: str = ""
    trecho_extraido: str = ""

    # Classificação
    tipo_de_servico: str = ""
    confianca: str = ""
    metodo: str = ""
    observacao: str = ""                # Razão LLM ou nota de revisão

    def confianca_display(self) -> str:
        """Retorna termo de negócio para a confiança."""
        try:
            nivel = NivelConfianca(self.confianca)
            return TERMOS_NEGOCIO.get(nivel, self.confianca)
        except ValueError:
            return self.confianca


class Oportunidade(BaseModel):
    """Uma linha na aba 'Oportunidades' (gap analysis)."""
    empresa: str = ""
    cnpj: str = ""
    cidade_uf_matriz: str = ""
    atividade_principal: str = ""
    capital_social: str = ""
    servico_disponivel: str             # Tese da lista mestra NÃO encontrada
    # Metadados da tese (para filtros na UI)
    area_responsavel: str = ""
    ramo_de_atividade: str = ""         # Multi-valor joined com " | "
    regime_tributario: str = ""         # Multi-valor joined com " | "
    objeto_da_tese: str = ""
    observacao: str = ""                # Nota para equipe de prospecção


# ============================================
# MODELOS — STATUS DO PIPELINE
# ============================================

class StatusPipeline(BaseModel):
    """Status de execução do pipeline (para UI de progresso)."""
    etapa_atual: str = ""               # Chave para TERMOS_NEGOCIO
    cnpjs_total: int = 0
    cnpjs_processados: int = 0
    documentos_baixados: int = 0
    documentos_extraidos: int = 0
    documentos_classificados: int = 0
    itens_revisao: int = 0
    oportunidades: int = 0
    erros: list[str] = Field(default_factory=list)
    concluido: bool = False

    def mensagem_progresso(self) -> str:
        """Retorna mensagem de progresso em linguagem de negócio."""
        return TERMOS_NEGOCIO.get(self.etapa_atual, self.etapa_atual)