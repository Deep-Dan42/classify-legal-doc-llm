"""
automacao-juridica-trf1 — Input Loader

Carrega e valida inputs do pipeline:
  - CNPJs de data/entrada/cnpjs.csv
  - Regras de mapeamento de data/entrada/mapeamento_tipo_servico.csv
  - Lista mestra de serviços de data/entrada/lista_servicos.csv

Validações (Gate 1):
  - Pelo menos 1 CNPJ válido (14 dígitos)
  - Arquivos obrigatórios existem
  - Duplicatas removidas
  - Relatório de carga impresso

Uso:
    from core.input_loader import carregar_cnpjs, carregar_mapeamento, carregar_lista_servicos
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, List, Tuple

if TYPE_CHECKING:
    from core.modelos import TeseMestra

from core.config import settings


# ============================================
# CONSTANTES
# ============================================

CNPJ_DIGITS_RE = re.compile(r"^\d{14}$")


# ============================================
# RELATÓRIO DE CARGA
# ============================================

@dataclass(frozen=True)
class RelatorioCarga:
    """Resultado da carga de CNPJs."""
    total_linhas: int
    validos_unicos: int
    invalidos: int
    duplicatas_removidas: int


# ============================================
# CNPJ — SANITIZAÇÃO E VALIDAÇÃO
# ============================================

def sanitizar_cnpj(valor: str) -> str:
    """Remove tudo exceto dígitos."""
    return re.sub(r"\D", "", valor or "")


def cnpj_valido(digitos: str) -> bool:
    """Validação de formato: exatamente 14 dígitos."""
    return bool(CNPJ_DIGITS_RE.match(digitos))


def formatar_cnpj(digitos: str) -> str:
    """
    Formata 14 dígitos como XX.XXX.XXX/XXXX-XX.
    Usado para exibição em relatórios e UI.
    """
    d = sanitizar_cnpj(digitos)
    if len(d) != 14:
        return digitos  # retorna sem formatação se inválido
    return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:14]}"


# ============================================
# LEITURA DE CSV GENÉRICA
# ============================================

def _ler_csv_coluna(path: Path, coluna: str) -> List[str]:
    """
    Lê um CSV e retorna valores de uma coluna específica.
    Se a coluna não existir no header, assume primeira coluna.
    Suporta CSV com ou sem header.
    """
    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {path}")

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        # Auto-detectar delimitador
        first_line = f.readline()
        f.seek(0)
        delimiter = ";" if ";" in first_line else ","

        reader = csv.reader(f, delimiter=delimiter)
        rows = list(reader)

    if not rows:
        return []

    # Detectar header
    header = [c.strip().lower() for c in rows[0]]
    coluna_lower = coluna.strip().lower()

    values: List[str] = []

    if coluna_lower in header:
        idx = header.index(coluna_lower)
        for r in rows[1:]:
            if len(r) <= idx:
                continue
            val = (r[idx] or "").strip()
            if val:
                values.append(val)
    else:
        # Assume primeira coluna (pode não ter header)
        for r in rows:
            if not r:
                continue
            val = (r[0] or "").strip()
            if val:
                values.append(val)

    return values


# ============================================
# CARREGAR CNPJs
# ============================================

def carregar_cnpjs(
    path: Path | None = None,
) -> Tuple[List[str], RelatorioCarga]:
    """
    Carrega CNPJs do CSV, valida formato (14 dígitos), remove duplicatas.
    Retorna (lista_limpa, relatório).

    Gate 1: Se 0 CNPJs válidos, levanta ValueError.
    """
    path = path or settings.CNPJS_CSV

    raw = _ler_csv_coluna(path, "cnpj")
    total = len(raw)

    invalidos = 0
    vistos: set = set()
    limpos: List[str] = []
    duplicatas = 0

    for v in raw:
        digitos = sanitizar_cnpj(v)
        if not cnpj_valido(digitos):
            invalidos += 1
            continue
        if digitos in vistos:
            duplicatas += 1
            continue
        vistos.add(digitos)
        limpos.append(digitos)

    relatorio = RelatorioCarga(
        total_linhas=total,
        validos_unicos=len(limpos),
        invalidos=invalidos,
        duplicatas_removidas=duplicatas,
    )

    if not limpos:
        raise ValueError(
            f"Nenhum CNPJ válido encontrado em {path}. "
            f"Total de linhas: {total}, inválidos: {invalidos}."
        )

    return limpos, relatorio


# ============================================
# CARREGAR MAPEAMENTO (tipo_de_servico)
# ============================================

@dataclass(frozen=True)
class RegraMapeamento:
    """Uma regra de mapeamento: texto_pdf → tipo_de_servico."""
    texto_pdf: str
    tipo_de_servico: str


def carregar_mapeamento(
    path: Path | None = None,
) -> List[RegraMapeamento]:
    """
    Carrega regras de mapeamento de mapeamento_tipo_servico.csv.
    Colunas esperadas: texto_pdf, tipo_de_servico (ou variantes com _ e espaços).

    Gate 1: Se arquivo não existe ou sem regras, levanta erro.
    """
    path = path or settings.MAPEAMENTO_CSV

    if not path.exists():
        raise FileNotFoundError(
            f"Arquivo de mapeamento não encontrado: {path}\n"
            f"Crie o arquivo com colunas: texto_pdf, tipo_de_servico"
        )

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        # Auto-detectar delimitador: ler primeira linha e verificar se ; ou , separa colunas
        first_line = f.readline()
        f.seek(0)
        delimiter = ";" if ";" in first_line else ","

        reader = csv.DictReader(f, delimiter=delimiter)
        if not reader.fieldnames:
            raise ValueError(f"Arquivo de mapeamento vazio: {path}")

        # Normalizar nomes de colunas (aceitar variações)
        campos = {c.strip().lower().replace(" ", "_"): c for c in reader.fieldnames}

        # Encontrar coluna de texto
        col_texto = None
        for candidato in ["texto_pdf", "pdf_text", "texto", "text"]:
            if candidato in campos:
                col_texto = campos[candidato]
                break

        # Encontrar coluna de serviço
        col_servico = None
        for candidato in ["tipo_de_servico", "service_type", "servico", "tipo_servico"]:
            if candidato in campos:
                col_servico = campos[candidato]
                break

        if not col_texto or not col_servico:
            raise ValueError(
                f"Colunas obrigatórias não encontradas em {path}. "
                f"Esperado: 'texto_pdf' e 'tipo_de_servico' (ou variantes). "
                f"Encontrado: {list(reader.fieldnames)}"
            )

        regras: List[RegraMapeamento] = []
        for row in reader:
            texto = (row.get(col_texto) or "").strip()
            servico = (row.get(col_servico) or "").strip()
            if texto and servico:
                regras.append(RegraMapeamento(texto_pdf=texto, tipo_de_servico=servico))

    if not regras:
        raise ValueError(f"Nenhuma regra válida encontrada em {path}")

    return regras


# ============================================
# CARREGAR LISTA MESTRA DE SERVIÇOS (TESES)
# ============================================

def _parse_multi_valor(valor: str) -> list[str]:
    """
    Parseia células multi-valor do CSV (separadas por newline dentro da célula).
    Ex: "Lucro Real\nLucro Presumido\nSimples Nacional" → ["Lucro Real", "Lucro Presumido", "Simples Nacional"]
    """
    if not valor:
        return []
    partes = [p.strip() for p in valor.replace("\r", "").split("\n")]
    return [p for p in partes if p and p.lower() != "não aplicável"]


def carregar_lista_servicos(
    path: Path | None = None,
) -> List["TeseMestra"]:
    """
    Carrega lista mestra de todos os serviços (teses) oferecidos pelo escritório.
    Formato: CSV com separador ; (ponto e vírgula), encoding UTF-8 com BOM.

    Colunas esperadas:
        Status, Tese, Área responsável, Objeto da tese, Estado,
        Ramo de atividade, Regime tributário, Tipo de produto que industrializa,
        Observações, Clientes possíveis, Data de criação

    Retorna lista de TeseMestra com todos os metadados.
    Usada para: gap analysis (coluna Tese) e filtros na UI (demais colunas).

    Gate 1: Se arquivo não existe ou sem teses, levanta erro.
    """
    from core.modelos import TeseMestra

    path = path or settings.LISTA_SERVICOS_CSV

    if not path.exists():
        raise FileNotFoundError(
            f"Lista de serviços não encontrada: {path}\n"
            f"Crie o arquivo com coluna: Tese (separador: ponto e vírgula)"
        )

    with path.open("r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")
        if not reader.fieldnames:
            raise ValueError(f"Arquivo de lista de serviços vazio: {path}")

        teses: List[TeseMestra] = []
        nomes_vistos: set = set()

        for row in reader:
            status = (row.get("Status") or "").strip()
            tese_nome = (row.get("Tese") or "").strip()

            if not tese_nome:
                continue

            # Deduplicar por nome da tese (case-insensitive)
            tese_lower = tese_nome.lower()
            if tese_lower in nomes_vistos:
                continue
            nomes_vistos.add(tese_lower)

            # Área pode ser multi-valor (newline dentro da célula) — juntar com " | "
            area_raw = (row.get("Área responsável") or "").strip()
            area_clean = " | ".join(
                p.strip() for p in area_raw.replace("\r", "").split("\n") if p.strip()
            )

            tese = TeseMestra(
                tese=tese_nome,
                status=status or "Ativo",
                area_responsavel=area_clean,
                objeto_da_tese=(row.get("Objeto da tese") or "").strip(),
                estado=_parse_multi_valor(row.get("Estado") or ""),
                ramo_de_atividade=_parse_multi_valor(row.get("Ramo de atividade") or ""),
                regime_tributario=_parse_multi_valor(row.get("Regime tributário") or ""),
                tipo_produto_industrializa=(row.get("Tipo de produto que industrializa") or "").strip(),
                observacoes=(row.get("Observações") or "").strip(),
                clientes_possiveis=(row.get("Clientes possíveis") or "").strip(),
                data_criacao=(row.get("Data de criação") or "").strip(),
            )
            teses.append(tese)

    if not teses:
        raise ValueError(f"Nenhuma tese válida encontrada em {path}")

    return teses


def nomes_teses(teses: List["TeseMestra"]) -> List[str]:
    """Extrai apenas os nomes das teses (para gap analysis)."""
    return [t.tese for t in teses]


# ============================================
# VALIDAÇÃO GATE 1 (todos os inputs de uma vez)
# ============================================

def validar_inputs() -> dict:
    """
    Valida todos os arquivos de entrada do pipeline.
    Retorna dict com resultados. Levanta exceção no primeiro erro fatal.

    Uso:
        resultado = validar_inputs()
        print(f"CNPJs: {resultado['cnpjs_validos']}")
        print(f"Regras: {resultado['regras_mapeamento']}")
        print(f"Teses: {resultado['teses_lista_mestra']}")
    """
    # CNPJs
    cnpjs, relatorio_cnpjs = carregar_cnpjs()

    # Mapeamento
    regras = carregar_mapeamento()

    # Lista mestra (agora retorna TeseMestra objects)
    teses = carregar_lista_servicos()

    resultado = {
        "cnpjs": cnpjs,
        "cnpjs_validos": len(cnpjs),
        "cnpjs_relatorio": relatorio_cnpjs,
        "regras": regras,
        "regras_mapeamento": len(regras),
        "teses": teses,
        "teses_lista_mestra": len(teses),
        "nomes_teses": nomes_teses(teses),
    }

    return resultado


# ============================================
# CLI
# ============================================

def main() -> None:
    """Execução standalone para validar inputs."""
    print("[INPUT LOADER] Validando arquivos de entrada...")
    print()

    try:
        resultado = validar_inputs()

        print(f"  ✓ CNPJs válidos       : {resultado['cnpjs_validos']}")
        r = resultado["cnpjs_relatorio"]
        print(f"    Total linhas        : {r.total_linhas}")
        print(f"    Inválidos           : {r.invalidos}")
        print(f"    Duplicatas removidas: {r.duplicatas_removidas}")
        print()
        print(f"  ✓ Regras de mapeamento: {resultado['regras_mapeamento']}")
        print()
        print(f"  ✓ Teses (lista mestra): {resultado['teses_lista_mestra']}")

        # Resumo dos metadados das teses
        teses = resultado["teses"]
        areas = sorted(set(t.area_responsavel for t in teses if t.area_responsavel))
        ramos = sorted(set(r for t in teses for r in t.ramo_de_atividade))
        regimes = sorted(set(r for t in teses for r in t.regime_tributario))
        print(f"    Áreas              : {', '.join(areas) if areas else '(nenhuma)'}")
        print(f"    Ramos de atividade : {', '.join(ramos) if ramos else '(nenhum)'}")
        print(f"    Regimes tributários: {', '.join(regimes) if regimes else '(nenhum)'}")
        print()
        print("[INPUT LOADER] Gate 1: PASSOU ✓")

    except (FileNotFoundError, ValueError) as e:
        print(f"  ✗ ERRO: {e}")
        print()
        print("[INPUT LOADER] Gate 1: FALHOU ✗")
        raise SystemExit(1)


if __name__ == "__main__":
    main()