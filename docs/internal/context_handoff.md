# Plano Próxima Sessão — D1-5 em diante

## Situação Atual
D1-4 (`core/downloader.py`) está **completo e validado**: 33/33 processos, todos documentos-alvo de um CNPJ baixados, nenhum processo perdido.

---

## Ordem de Execução (conforme plano original)

| Passo | Deliverable | Módulo | Dependência |
|-------|-------------|--------|-------------|
| 1 | **D1-5** | `core/extrator.py` | PDFs do downloader |
| 2 | **D1-6** | `classificacao/regras.py` | Textos do extrator |
| 3 | **D1-7** | `classificacao/embeddings.py` + `scripts/construir_embeddings.py` | Textos do extrator |
| 4 | **D1-8** | `classificacao/llm_classificador.py` | Textos do extrator |
| 5 | **D1-9** | `classificacao/motor.py` | Camadas 1-3 |
| 6 | **D1-10** | `core/gap_analysis.py` | Classificações + lista_servicos |
| 7 | **D1-11** | `scripts/gerar_consulta.py` + Excel 4 abas | Pipeline completo |

---

## D1-5: core/extrator.py (PRÓXIMO)

### O que faz
Extrai trechos relevantes dos PDFs baixados para alimentar a classificação.

### Estratégia por tipo de documento

**DECISÃO:**
- Abrir PDF com PyMuPDF (`import fitz`)
- Procurar heading "DECISÃO" (regex: `^\s*(DECIS[AÃ]O)\s*$`)
- Extrair 1000 caracteres após o heading
- Se não encontrar heading, extrair primeiros 1000 chars do documento

**PETIÇÃO:**
- Abrir PDF com PyMuPDF
- Procurar heading "DO PEDIDO" / "DOS PEDIDOS" (regex: `^\s*D[OA]S?\s*PEDIDO[S]?\s*$`)
- Extrair 2000 caracteres após o heading
- Fallback patterns: "PEDIDOS", "DOS REQUERIMENTOS"
- Buscar em todas as páginas (petições longas)
- Se nenhum heading encontrar, extrair últimos 2000 chars (pedido geralmente no final)

### Input
```python
# RegistroDownload do downloader:
registro.caminho_pdf  # "data/documentos/84466424000136/..._DECISAO_35667540.pdf"
registro.tipo_documento  # TipoDocumento.DECISAO
registro.numero_processo  # "1003965-30.2025.4.01.3200"
```

### Output
```python
# RelatorioExtracao (já definido em modelos.py):
class RelatorioExtracao(BaseModel):
    cnpj: str
    numero_processo: str
    tipo_documento: TipoDocumento
    texto_extraido: str
    n_paginas: int
    caminho_pdf: str
    heading_encontrado: str = ""
    metodo_extracao: str = ""  # "heading", "fallback", "truncado"
```

### Considerações
- Tamanho estimado: ~150-200 linhas
- Pode exigir iteração com screenshots de variações de documentos para ajustar patterns
- Alguns PDFs são petições digitadas no PJe (HTML renderizado como PDF) — texto pode ter formatação diferente
- Documentos mais antigos podem ter estrutura diferente dos mais recentes

---