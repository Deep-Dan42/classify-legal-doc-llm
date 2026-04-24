# Known Issues — Developer Memory

Internal log of known behaviors that need investigation but are not blocking
production. Not user-facing.

---

## KI-001 — "Gerar Consulta" does not advance past "Extraindo texto" on installer-launched window

**First seen**: v1.0.0 deployment, 2026-04-23.

**Symptom**: When the operator runs `instalar.bat` successfully, the installer
launches the Streamlit server and opens the browser automatically. If the operator
immediately enters a CNPJ and clicks "Gerar Consulta" on this automatically-opened
window, the pipeline stalls at the "Extraindo texto" stage and never advances to
"Classificando 1/N...".

**Workaround (documented to office staff)**: close the automatically-opened browser
window and Streamlit server. Re-open via the Desktop shortcut "Consulta TRF1"
(which calls `iniciar_servidor.bat`). The pipeline then runs normally.

**Tested on**: developer's personal Windows PC (Windows 10/11, Python 3.14.4, fresh
install, no prior installation).

**Hypotheses (not verified)**:
1. Subprocess environment state leaking from `instalar.bat` into the Streamlit
   server it spawns, causing the classification subprocess to fail silently.
2. Working directory or PATH variable differences between the installer-spawned
   Streamlit server and a manually-launched one.
3. The classification pipeline may be calling out to a library that expects a
   clean console state, which the installer-spawned process does not have.

**Deferred**: first deployment was time-critical. Workaround is acceptable for the
office. Plan: investigate in a future version with proper diagnostic logging added
to the classification pipeline.

**Files involved (likely)**: `instalar.bat` (launch sequence), `ui/app.py`
(`_run_pipeline`), `classificacao/motor.py`, `classificacao/llm_classificador.py`.

---

## KI-002 — Keyword extraction from Parte Relevante is too permissive

**First seen**: v1.1.0 smoke test, 2026-04-23.

**Symptom**: When the operator pastes a legal passage into "Parte Relevante"
(either in Revisao or in the new Resultados correction), the generated rule in
Regras Sugeridas sometimes contains nearly the entire sentence instead of a
distilled set of keywords. LLM-generated entries look clean
(e.g. `'não inclusão; ISS; PIS; COFINS; suspensão'`) but manually-generated
entries look like full sentences
(e.g. `'suspender exigibilidade creditos tributarios referentes contribuicao...'`).

**Root cause**: `classificacao/regras.py::_extrair_keywords` only removes a small
set of Portuguese stopwords and single-character tokens. For legal passages,
almost every word is a content word, so nearly all tokens survive.

**Deferred**: did NOT fix in v1.1.1 because:
1. Deterministic rule engine semantics require ALL keywords to match; longer
   rules simply fire less often (not wrong, just less useful).
2. Changing the extractor touches core classification code and needs real-world
   validation data before we decide what "good keyword extraction" looks like
   in this domain.
3. Office is testing v1.1.x now — we need data on how operators actually phrase
   their "Parte Relevante" before tuning the extractor.

**Future plan**: once enough operator-approved rules exist in `mapeamento_tipo_servico.csv`,
consider an LLM-based keyword extraction (send the relevant text to GPT-4o-mini
with a prompt like "Extract 4-6 keywords suitable for deterministic rule matching
on Brazilian legal documents"). This would replace the current word-filter approach
with a semantically-aware one. Cost impact: marginal, ~$0.0001 per approval.

**Files involved**: `classificacao/regras.py::_extrair_keywords`.
