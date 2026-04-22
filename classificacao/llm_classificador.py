"""
automacao-juridica-trf1 — Camada 2: Classificação por LLM (v3)

5-step classification process:
    1. LOCATE — find the request section (DO PEDIDO / diante do exposto)
    2. EXTRACT — pull the 2-3 key lines
    3. KEYWORDS — extract tax terms + actions + geographic indicators
    4. MATCH — compare keywords against tese names (abbreviation-aware)
    5. CLASSIFY — decide service type or REVISÃO

If not 100% sure → REVISÃO. Zero false positives is the goal.

Uso:
    from classificacao.llm_classificador import ClassificadorLLM

    clf = ClassificadorLLM(teses=lista_de_TeseMestra, iniciais=dict_iniciais)
    resultado = clf.classificar(texto)
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional

from core.config import settings
from core.modelos import (
    MetodoClassificacao,
    NivelConfianca,
    ResultadoClassificacao,
    TeseMestra,
)

logger = logging.getLogger(__name__)


# ============================================
# SYSTEM PROMPT — 5-STEP PROCESS
# ============================================

_SYSTEM_PROMPT = """\
You are a Brazilian tax law classifier. You follow a strict 5-step process to classify \
legal documents into service types (teses tributárias). You NEVER guess. If you are not \
100% certain, you return NAO_IDENTIFICADO.

═══════════════════════════════════════════
STEP 1 — LOCATE THE REQUEST SECTION
═══════════════════════════════════════════
For PETIÇÃO documents, the answer is ONLY in the REQUEST section. Search for:
- Headings: "DO PEDIDO", "DOS PEDIDOS", "DOS REQUERIMENTOS", "O PEDIDO"
- Anchors: "diante do exposto", "ante o exposto", "ante ao exposto", \
"razão do exposto", "pelo exposto", "requer-se", "requer a"
- The text AFTER these markers (2-3 lines) contains the specific legal claim.

For DECISÃO documents, search for:
- "Trata-se de" at the beginning — this summarizes what the case is about.
- If the text is purely procedural (competência, redistribuição, prazo, citação, \
intimação, embargos de declaração) with NO tax substance → return NAO_IDENTIFICADO.

═══════════════════════════════════════════
STEP 2 — EXTRACT THE RELEVANT LINES
═══════════════════════════════════════════
From the located section, extract the 2-3 lines that describe:
- WHAT tax or contribution is being discussed
- WHAT action is being requested (suspensão, exclusão, crédito, restituição, etc.)
- WHERE geographically (ZFM, ALCs, specific states) if mentioned
Report these lines in the "parte_relevante" field of your response.

═══════════════════════════════════════════
STEP 3 — EXTRACT KEYWORDS
═══════════════════════════════════════════
From the relevant lines, extract the specific legal/tax keywords:
- TAX names: PIS, COFINS, ICMS, IRPJ, CSLL, IPI, ISS, INSS, CPRB, FGTS
- ACTION words: exclusão, crédito, suspensão, restituição, compensação, \
aproveitamento, manutenção, não-incidência, descontar, tomada
- GEOGRAPHIC terms: ZFM, ALCs, Zona Franca, Área de Livre Comércio, Manaus, Suframa
- SPECIFIC qualifiers: presumidos, subvenções, insumos, importação, vendas, \
aquisições, base de cálculo, tributação concentrada, não-cumulativo

CRITICAL ABBREVIATIONS (expand these mentally when matching):
- ZFM = Zona Franca de Manaus
- ALC = Área de Livre Comércio (includes Boa Vista, Bonfim, Macapá, Santana, \
Tabatinga, Guajará-Mirim, Cruzeiro do Sul, Brasiléia, Epitaciolândia)
- TCIF = Taxa de Controle de Incentivos Fiscais
- IPI = Imposto sobre Produtos Industrializados
- ISS = Imposto sobre Serviços
- BC = Base de Cálculo

═══════════════════════════════════════════
STEP 4 — MATCH KEYWORDS AGAINST TESE NAMES
═══════════════════════════════════════════
Compare your extracted keywords against the tese names in the list. \
The tese NAME contains abbreviated clues:
- "PIS COFINS Vendas ALCs" → requires: PIS/COFINS + vendas + Área de Livre Comércio
- "PIS COFINS Crédito Nacionais ZFM Tributadas" → requires: PIS/COFINS + crédito + \
nacionais/aquisições + ZFM (NOT ALCs)
- "IRPJ CSLL Subvenções ICMS" → requires: IRPJ + CSLL + subvenções/créditos presumidos + ICMS
- "PIS COFINS Subvenções ICMS" → requires: PIS + COFINS + subvenções/créditos presumidos + ICMS \
(NOT IRPJ/CSLL)

The keywords from Step 3 must match the components in the tese name. If the keywords \
mention "Área de Livre Comércio" or "ALC" but the tese says "ZFM", they are DIFFERENT services.

═══════════════════════════════════════════
STEP 5 — CLASSIFY OR REVISÃO
═══════════════════════════════════════════
- If keywords clearly match exactly ONE tese → classify with "ALTA" confidence
- If keywords partially match but you're not 100% sure → NAO_IDENTIFICADO
- If the document discusses a tax topic NOT in the list → NAO_IDENTIFICADO
- If no request section was found (procedural decision) → NAO_IDENTIFICADO
- If keywords could match MULTIPLE teses → NAO_IDENTIFICADO

GOLDEN RULE: It is FAR better to send a document to human review (NAO_IDENTIFICADO) \
than to classify it incorrectly. Zero false positives is the goal.

═══════════════════════════════════════════
EXAMPLES OF CORRECT CLASSIFICATION
═══════════════════════════════════════════

Example 1 — PETIÇÃO → IRPJ CSLL Subvenções ICMS:
  Relevant part: "Seja DEFERIDA A MEDIDA LIMINAR para determinar que seja suspensa a \
exigibilidade de IRPJ e CSLL sobre os créditos presumidos de ICMS"
  Keywords: suspensa, exigibilidade, IRPJ, CSLL, créditos presumidos, ICMS
  Match: IRPJ + CSLL + créditos presumidos/subvenções + ICMS → "IRPJ CSLL Subvenções ICMS" ✓

Example 2 — PETIÇÃO → PIS COFINS Vendas ALCs:
  Relevant part: "determinando a suspensão da exigibilidade do PIS e da COFINS sobre \
as vendas de mercadorias para empresas localizadas na Área de Livre Comércio"
  Keywords: suspensão, exigibilidade, PIS, COFINS, vendas, mercadorias, Área de Livre Comércio
  Match: PIS + COFINS + vendas + Área Livre Comércio (=ALC) → "PIS COFINS Vendas ALCs" ✓
  NOTE: This is NOT "PIS COFINS Crédito Nacionais ZFM" because it says ALCs, not ZFM.

Example 3 — PETIÇÃO → PIS COFINS Subvenções ICMS:
  Relevant part: "suspensa a exigibilidade do PIS e da COFINS sobre créditos presumidos de ICMS"
  Keywords: suspensa, exigibilidade, PIS, COFINS, créditos presumidos, ICMS
  Match: PIS + COFINS + créditos presumidos + ICMS → "PIS COFINS Subvenções ICMS" ✓
  NOTE: This is NOT "IRPJ CSLL Subvenções" because tax is PIS/COFINS, not IRPJ/CSLL.

Example 4 — DECISÃO → REVISÃO (procedural):
  Text: "Da leitura dos presentes autos verifico óbice instransponível ao conhecimento \
da ação por este Juízo..."
  No tax substance, purely procedural → NAO_IDENTIFICADO ✓

Example 5 — PETIÇÃO → REVISÃO (not in list):
  Relevant part: "MEDIDA LIMINAR para determinar que a Autoridade coatora dê seguimento \
ao despacho aduaneiro da mercadoria vinculada"
  Keywords: despacho, aduaneiro, mercadoria
  Match: No tese in the list matches customs/import clearance → NAO_IDENTIFICADO ✓

═══════════════════════════════════════════
RESPONSE FORMAT
═══════════════════════════════════════════
RESPOND ONLY with valid JSON, no markdown, no preamble:
{
  "parte_relevante": "the 2-3 key lines you found in Step 2 (verbatim from document)",
  "keywords_detectados": "keywords from Step 3, separated by semicolons",
  "tese_match": "the tese name your keywords matched in Step 4, or empty if none",
  "confianca": "ALTA" or "NAO_IDENTIFICADO",
  "tipo_de_servico": "exact tese name from the list, or NAO_IDENTIFICADO",
  "palavras_chave": "5-8 keywords for deterministic rule (only if classified, else empty)",
  "razao": "1-2 sentences in Portuguese explaining your reasoning"
}
"""


def _build_tese_list(teses: list[TeseMestra], iniciais: dict[str, str]) -> str:
    """Constrói a lista de teses com Objeto + Inicial para o prompt."""
    entries = []
    for t in teses:
        parts = [f"- {t.tese}"]
        if t.objeto_da_tese:
            parts.append(f"  Objeto: {t.objeto_da_tese[:200].strip()}")
        ini = iniciais.get(t.tese, "")
        if ini:
            parts.append(f"  Inicial: {ini[:200].strip()}")
        entries.append("\n".join(parts))
    return "\n\n".join(entries)


def _build_user_prompt(texto: str, tese_list_str: str) -> str:
    """Monta o prompt do usuário."""
    return (
        f"AVAILABLE SERVICE TYPES (with descriptions):\n\n{tese_list_str}\n\n"
        f"---\n\n"
        f"DOCUMENT EXCERPT TO CLASSIFY:\n{texto}"
    )


# ============================================
# PARSER
# ============================================

def _parse_response(raw: str, nomes_teses_lower: dict[str, str]) -> Optional[dict]:
    """Parseia resposta JSON do LLM."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[-1]
    if text.endswith("```"):
        text = text.rsplit("```", 1)[0]
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        logger.error("JSON inválido: %s — %s", e, raw[:200])
        return None

    tipo = (data.get("tipo_de_servico") or "").strip()
    confianca = (data.get("confianca") or "").strip().upper()
    parte = (data.get("parte_relevante") or "").strip()
    keywords = (data.get("keywords_detectados") or "").strip()
    palavras = (data.get("palavras_chave") or "").strip()
    razao = (data.get("razao") or "").strip()

    if tipo == "NAO_IDENTIFICADO" or confianca == "NAO_IDENTIFICADO":
        return {
            "tipo": "NAO_IDENTIFICADO", "confianca": "NAO_IDENTIFICADO",
            "parte": parte, "keywords": keywords,
            "palavras": "", "razao": razao,
        }

    # Validate against tese list
    tipo_lower = tipo.lower()
    if tipo_lower in nomes_teses_lower:
        tipo = nomes_teses_lower[tipo_lower]
    else:
        for key, original in nomes_teses_lower.items():
            if tipo_lower in key or key in tipo_lower:
                logger.warning("Match parcial: '%s' → '%s'", tipo, original)
                tipo = original
                break
        else:
            logger.warning("Tipo não reconhecido: '%s' → NAO_IDENTIFICADO", tipo)
            return {
                "tipo": "NAO_IDENTIFICADO", "confianca": "NAO_IDENTIFICADO",
                "parte": parte, "keywords": keywords,
                "palavras": "", "razao": f"Tipo '{tipo}' não está na lista.",
            }

    return {
        "tipo": tipo, "confianca": confianca,
        "parte": parte, "keywords": keywords,
        "palavras": palavras, "razao": razao,
    }


# ============================================
# CLASSIFICADOR
# ============================================

class ClassificadorLLM:
    """Camada 2 — GPT-4o-mini with 5-step classification process."""

    def __init__(
        self,
        teses: list[TeseMestra],
        iniciais: Optional[dict[str, str]] = None,
        model: str = "gpt-4o-mini",
        max_retries: int = 2,
    ) -> None:
        if not teses:
            raise ValueError("Lista de teses vazia.")

        self._teses = teses
        self._nomes_teses = [t.tese for t in teses]
        self._nomes_teses_lower = {t.tese.lower(): t.tese for t in teses}
        self._iniciais = iniciais or {}
        self._model = model
        self._max_retries = max_retries
        self._client = None

        self._tese_list_str = _build_tese_list(teses, self._iniciais)

        self._calls = 0
        self._tokens_input = 0
        self._tokens_output = 0
        self._errors = 0
        self._last_revisao_info: Optional[dict] = None  # keywords/parte from last NAO_IDENTIFICADO

        n_obj = sum(1 for t in teses if t.objeto_da_tese)
        n_ini = sum(1 for t in teses if t.tese in self._iniciais)
        logger.info(
            "ClassificadorLLM: %d teses (%d Objeto, %d Inicial), modelo=%s",
            len(teses), n_obj, n_ini, model,
        )

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            if not settings.OPENAI_API_KEY:
                raise ValueError("OPENAI_API_KEY não definida.")
            self._client = OpenAI(api_key=settings.OPENAI_API_KEY)
        return self._client

    def classificar(self, texto: str) -> Optional[ResultadoClassificacao]:
        """Classifica um trecho. Returns ResultadoClassificacao or None (→ REVISÃO)."""
        self._last_revisao_info = None
        if not texto or not texto.strip():
            return None

        client = self._get_client()
        user_prompt = _build_user_prompt(texto, self._tese_list_str)

        for attempt in range(1, self._max_retries + 1):
            try:
                t0 = time.time()
                response = client.chat.completions.create(
                    model=self._model,
                    max_tokens=600,
                    temperature=0,
                    messages=[
                        {"role": "system", "content": _SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                )
                elapsed = time.time() - t0
                self._calls += 1

                usage = response.usage
                self._tokens_input += usage.prompt_tokens
                self._tokens_output += usage.completion_tokens
                raw = response.choices[0].message.content

                logger.debug("LLM #%d: %d/%d tokens, %.1fs",
                             self._calls, usage.prompt_tokens, usage.completion_tokens, elapsed)

                parsed = _parse_response(raw, self._nomes_teses_lower)
                if parsed is None:
                    logger.warning("Tentativa %d/%d: parsing falhou.", attempt, self._max_retries)
                    continue

                if parsed["tipo"] == "NAO_IDENTIFICADO":
                    self._last_revisao_info = {
                        "parte": parsed.get("parte", ""),
                        "keywords": parsed.get("keywords", ""),
                        "razao": parsed.get("razao", ""),
                    }
                    logger.info("LLM → REVISÃO. Keywords: %s | Razão: %s",
                                parsed["keywords"], parsed["razao"])
                    return None

                return ResultadoClassificacao(
                    tipo_de_servico=parsed["tipo"],
                    confianca=NivelConfianca.LLM,
                    metodo=MetodoClassificacao.LLM,
                    razao_llm=(
                        f"[Parte relevante] {parsed['parte']}\n"
                        f"[Keywords] {parsed['keywords']}\n"
                        f"[Razão] {parsed['razao']}"
                    ),
                    regra_match=parsed["palavras"],
                )

            except Exception as e:
                self._errors += 1
                logger.error("Erro LLM (%d/%d): %s", attempt, self._max_retries, e)
                if attempt == self._max_retries:
                    return None

        return None

    @property
    def custo_estimado(self) -> float:
        return (self._tokens_input * 0.15 / 1_000_000
                + self._tokens_output * 0.60 / 1_000_000)

    def diagnostico(self) -> str:
        return (
            f"[LLM] Diagnóstico — {self._model}\n"
            f"  Chamadas: {self._calls}\n"
            f"  Tokens input: {self._tokens_input:,}\n"
            f"  Tokens output: {self._tokens_output:,}\n"
            f"  Erros: {self._errors}\n"
            f"  Custo estimado: ${self.custo_estimado:.6f}"
        )

    def resumo(self) -> str:
        return (
            f"[LLM] ClassificadorLLM\n"
            f"  Modelo: {self._model}\n"
            f"  Teses: {len(self._teses)}\n"
            f"  Retries: {self._max_retries}"
        )