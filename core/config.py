"""
automacao-juridica-trf1 — Configuração central

Carrega variáveis de ambiente do .env e expõe como objeto `settings`.
Fail-fast: se chaves obrigatórias estiverem faltando, o programa para imediatamente.

Uso:
    from core.config import settings
    print(settings.OPENAI_API_KEY)
    print(settings.DATA_ENTRADA_DIR)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os


# ------------------------------------------
# Carregar .env do diretório raiz do projeto
# ------------------------------------------
# Raiz do projeto: 1 nível acima de core/
PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = PROJECT_ROOT / ".env"

if ENV_PATH.exists():
    load_dotenv(ENV_PATH)
else:
    # Não é erro fatal — pode estar rodando em ambiente com variáveis já definidas
    pass


# ------------------------------------------
# Helper para leitura segura
# ------------------------------------------
def _get(key: str, default: Optional[str] = None, required: bool = False) -> str:
    """Lê variável de ambiente. Se required=True e não encontrada, para o programa."""
    value = os.getenv(key, default)
    if required and not value:
        print(f"[ERRO] Variável de ambiente obrigatória não definida: {key}")
        print(f"       Copie .env.example para .env e preencha o valor.")
        sys.exit(1)
    return value or ""


def _get_float(key: str, default: float) -> float:
    raw = os.getenv(key, str(default))
    try:
        return float(raw)
    except ValueError:
        print(f"[AVISO] {key}={raw} não é um número válido. Usando default: {default}")
        return default


def _get_int(key: str, default: int) -> int:
    raw = os.getenv(key, str(default))
    try:
        return int(raw)
    except ValueError:
        print(f"[AVISO] {key}={raw} não é um inteiro válido. Usando default: {default}")
        return default


# ------------------------------------------
# Classe de configuração
# ------------------------------------------
class Settings:
    """Configurações carregadas do .env + defaults."""

    def __init__(self) -> None:
        # --- API Keys ---
        # Nota: não são required=True aqui porque o pipeline pode rodar parcialmente
        # (ex: apenas download, sem classificação). A validação de chaves é feita
        # no momento do uso (Camada 2 e Camada 3).
        self.OPENAI_API_KEY: str = _get("OPENAI_API_KEY", "")
        self.ANTHROPIC_API_KEY: str = _get("ANTHROPIC_API_KEY", "")

        # --- Extensão whom.doc9 ---
        self.WHOM_DOC9_EXTENSION_PATH: str = _get("WHOM_DOC9_EXTENSION_PATH", "")
        self.BROWSER_PROFILE_DIR: Path = PROJECT_ROOT / _get("BROWSER_PROFILE_DIR", "data/navegador")

        # --- Classificação ---
        self.EMBEDDING_SIMILARITY_THRESHOLD: float = _get_float("EMBEDDING_SIMILARITY_THRESHOLD", 0.85)

        # --- Extração ---
        self.EXTRACT_CHARS_SENTENCA: int = _get_int("EXTRACT_CHARS_SENTENCA", 1000)
        self.EXTRACT_CHARS_DECISAO: int = _get_int("EXTRACT_CHARS_DECISAO", 1000)
        self.EXTRACT_CHARS_PETICAO: int = _get_int("EXTRACT_CHARS_PETICAO", 6000)

        # --- Pipeline ---
        self.MIN_PROCESS_YEAR: int = _get_int("MIN_PROCESS_YEAR", 2016)
        self.MAX_ATTEMPTS_PER_CNPJ: int = _get_int("MAX_ATTEMPTS_PER_CNPJ", 3)
        self.PAUSE_BETWEEN_CNPJS_SECONDS: float = _get_float("PAUSE_BETWEEN_CNPJS_SECONDS", 2.0)

        # --- Caminhos de dados (relativos à raiz do projeto) ---
        self.DATA_ENTRADA_DIR: Path = PROJECT_ROOT / _get("DATA_ENTRADA_DIR", "data/entrada")
        self.DATA_SAIDA_DIR: Path = PROJECT_ROOT / _get("DATA_SAIDA_DIR", "data/saida")
        self.DATA_DOCUMENTOS_DIR: Path = PROJECT_ROOT / _get("DATA_DOCUMENTOS_DIR", "data/documentos")
        self.DATA_EMBEDDINGS_DIR: Path = PROJECT_ROOT / _get("DATA_EMBEDDINGS_DIR", "data/embeddings")

        # --- Arquivos de entrada (derivados) ---
        self.CNPJS_CSV: Path = self.DATA_ENTRADA_DIR / "cnpjs.csv"
        self.MAPEAMENTO_CSV: Path = self.DATA_ENTRADA_DIR / "mapeamento_tipo_servico.csv"
        self.LISTA_SERVICOS_CSV: Path = self.DATA_ENTRADA_DIR / "lista_servicos.csv"

        # --- Arquivos de saída (derivados) ---
        self.REGISTRO_DOWNLOADS_CSV: Path = self.DATA_SAIDA_DIR / "registro_de_downloads.csv"
        self.AUDITORIA_LOG: Path = self.DATA_SAIDA_DIR / "auditoria.log"

        # --- Raiz do projeto ---
        self.PROJECT_ROOT: Path = PROJECT_ROOT

    def validar_api_keys(self, camada: str = "todas") -> bool:
        """
        Verifica se as chaves de API necessárias estão definidas.
        camada: 'embedding', 'llm', ou 'todas'
        Retorna True se válidas, False se não.
        """
        ok = True

        if camada in ("embedding", "todas"):
            if not self.OPENAI_API_KEY:
                print("[AVISO] OPENAI_API_KEY não definida. Camada 2 (embeddings) desabilitada.")
                ok = False

        if camada in ("llm", "todas"):
            if not self.ANTHROPIC_API_KEY:
                print("[AVISO] ANTHROPIC_API_KEY não definida. Camada 3 (LLM) desabilitada.")
                ok = False

        return ok

    def validar_extensao(self) -> bool:
        """Verifica se o caminho da extensão whom.doc9 existe."""
        if not self.WHOM_DOC9_EXTENSION_PATH:
            print("[AVISO] WHOM_DOC9_EXTENSION_PATH não definido.")
            return False

        ext_path = Path(self.WHOM_DOC9_EXTENSION_PATH)
        if not ext_path.exists():
            print(f"[AVISO] Extensão não encontrada: {ext_path}")
            return False

        return True

    def garantir_pastas(self) -> None:
        """Cria pastas de dados se não existirem."""
        for d in [
            self.DATA_ENTRADA_DIR,
            self.DATA_SAIDA_DIR,
            self.DATA_DOCUMENTOS_DIR,
            self.DATA_EMBEDDINGS_DIR,
            self.BROWSER_PROFILE_DIR,
        ]:
            d.mkdir(parents=True, exist_ok=True)

    def resumo(self) -> str:
        """Retorna resumo legível da configuração atual (sem expor chaves)."""
        api_openai = "✓ definida" if self.OPENAI_API_KEY else "✗ não definida"
        api_anthropic = "✓ definida" if self.ANTHROPIC_API_KEY else "✗ não definida"
        ext = "✓ definida" if self.WHOM_DOC9_EXTENSION_PATH else "✗ não definida"

        return (
            f"[CONFIG] automacao-juridica-trf1\n"
            f"  Raiz do projeto       : {self.PROJECT_ROOT}\n"
            f"  OpenAI API Key        : {api_openai}\n"
            f"  Anthropic API Key     : {api_anthropic}\n"
            f"  Extensão whom.doc9    : {ext}\n"
            f"  Threshold embedding   : {self.EMBEDDING_SIMILARITY_THRESHOLD}\n"
            f"  Chars SENTENÇA        : {self.EXTRACT_CHARS_SENTENCA}\n"
            f"  Chars DECISÃO         : {self.EXTRACT_CHARS_DECISAO}\n"
            f"  Chars PETIÇÃO         : {self.EXTRACT_CHARS_PETICAO}\n"
            f"  Ano mínimo processo   : {self.MIN_PROCESS_YEAR}\n"
            f"  Tentativas por CNPJ   : {self.MAX_ATTEMPTS_PER_CNPJ}\n"
            f"  Pausa entre CNPJs (s) : {self.PAUSE_BETWEEN_CNPJS_SECONDS}\n"
            f"  Pasta entrada         : {self.DATA_ENTRADA_DIR}\n"
            f"  Pasta saída           : {self.DATA_SAIDA_DIR}\n"
            f"  Pasta documentos      : {self.DATA_DOCUMENTOS_DIR}\n"
            f"  Pasta embeddings      : {self.DATA_EMBEDDINGS_DIR}\n"
        )


# ------------------------------------------
# Instância global (singleton)
# ------------------------------------------
settings = Settings()
