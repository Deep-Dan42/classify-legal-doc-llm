# Stage 2 — Plano de Execução Final v5

**Projeto:** automacao-juridica-trf1
**Prazo:** 2 dias
**Status:** DEFINITIVO v5 — atualizado com descobertas de implementação D1-1 a D1-4

---

## 0. Decisões e Considerações Consolidadas

| # | Decisão / Consideração | Escolha |
|---|------------------------|---------|
| 1 | Repositório | `automacao-juridica-trf1` (novo repo) |
| 2 | Embedding model | OpenAI `text-embedding-3-small` |
| 3 | LLM classifier | Claude `claude-haiku-4-5` |
| 4 | Browser automation | `undetected-chromedriver` + perfil dedicado em `data/navegador/chrome_automacao/` |
| 5 | Acesso TRF1 | Autenticado (extensão redireciona para dashboard) |
| 6 | UI | Streamlit — linguagem de negócio, sem termos técnicos |
| 7 | Deploy | Python + Streamlit (Docker futuro) |
| 8 | Tipos de serviço | 30-50 valores no mapeamento |
| 9 | Documentos-alvo | SENTENÇA, DECISÃO, PETIÇÃO/PETIÇÃO INICIAL |
| 10 | Metadados empresa | Scraping do TRF1 PJe (detalhe do processo) |
| 11 | Dedup de downloads | Não re-baixar PDFs já existentes no diretório |
| 12 | Gap analysis | Objetivo principal: encontrar serviços NÃO presentes |
| 13 | Lista mestra de serviços | Arquivo separado fornecido pelo usuário |
| 14 | Segurança de dados | Seção dedicada (Seção 8) |
| 15 | Fluxo auth | Perfil dedicado + whom.doc9 → JFAM manual → automação assume após consulta |
| 16 | UI/UX | Profissional jurídico. Cores: laranja, preto, prata. Sem estilo marketing. |
| 17 | Lista mestra formato | `lista_servicos.csv`: `;` delimitador, 11 colunas, 70 teses com metadados (Tese, Área, Ramo, Regime, etc.). Carregada como `TeseMestra` objects. |
| 18 | Abordagem UI filtros | Approach C: carregar todos metadados, filtros dropdown na tela Oportunidades (Área, Ramo, Regime). Sem auto-filter. |
| 19 | Python version | 3.13 (macOS). Requer `setuptools` para `undetected-chromedriver` (distutils removido em 3.13). |
| 20 | Perfil Chrome automação | Perfil dedicado isolado em `data/navegador/chrome_automacao/`. Extensão whom.doc9 instalada 1x. Não usa perfil pessoal. |

---

## 1. Propósito do Sistema

### O que o sistema faz

O sistema **gera consultas** para CNPJs, analisando processos judiciais no TRF1 PJe para identificar **oportunidades de serviço** — serviços que o escritório pode oferecer ao potencial cliente porque **NÃO foram encontrados** nos documentos judiciais existentes.

### Lógica de negócio central

```
LISTA MESTRA DE SERVIÇOS (tudo que o escritório oferece)
  MENOS (−)
SERVIÇOS JÁ ENCONTRADOS nos documentos do CNPJ (SENTENÇA, DECISÃO, PETIÇÃO)
  IGUAL (=)
OPORTUNIDADES DE PROSPECÇÃO (serviços que a equipe pode oferecer)
```

---

## 2. Glossário de Nomes — Convenção de Domínio

### 2.1 Arquivos de Saída

| Arquivo | Nome Final | Conteúdo |
|---------|-----------|----------|
| Relatório completo | `relatorio_de_oportunidades_{cnpj}_{YYYYMMDD}.xlsx` | Aba 1: dados da empresa + serviços encontrados. Aba 2: oportunidades (gap). |
| Triagem pendente | `triagem_pendente_{cnpj}_{YYYYMMDD}.xlsx` | Itens que precisam de decisão humana |
| Consolidado multi-CNPJ | `relatorio_de_oportunidades_consolidado_{YYYYMMDD}.xlsx` | Todos os CNPJs processados em um arquivo |
| Registro de downloads | `registro_de_downloads.csv` | Log de todos os PDFs baixados (para dedup) |
| Auditoria | `auditoria.log` | Ações do sistema e do usuário |

### 2.2 Colunas do Relatório — Aba "Serviços Identificados"

| Coluna | Nome no Excel | Fonte |
|--------|--------------|-------|
| Empresa | `empresa` | TRF1 PJe (detalhe processo) |
| CNPJ | `cnpj` | Input |
| Cidade/UF | `cidade_uf_matriz` | TRF1 PJe |
| Atividade Principal | `atividade_principal` | TRF1 PJe |
| Atividade Secundária | `atividade_secundaria` | TRF1 PJe |
| Capital Social | `capital_social` | TRF1 PJe |
| Nº do Processo | `numero_processo` | TRF1 PJe |
| Local do Processo | `local_processo` | TRF1 PJe |
| Advogado | `advogado` | TRF1 PJe |
| Tipo do Processo | `tipo_processo` | TRF1 PJe |
| Tipo do Documento | `tipo_documento` | Download |
| Trecho Extraído | `trecho_extraido` | Extrator |
| Tipo de Serviço | `tipo_de_servico` | Classificação |
| Confiança | `confianca` | Classificação |
| Método | `metodo` | Classificação |

### 2.3 Colunas do Relatório — Aba "Oportunidades" (GAP ANALYSIS)

| Coluna | Nome no Excel |
|--------|--------------|
| Empresa | `empresa` |
| CNPJ | `cnpj` |
| Cidade/UF | `cidade_uf_matriz` |
| Atividade Principal | `atividade_principal` |
| Capital Social | `capital_social` |
| Serviço Disponível | `servico_disponivel` |
| Observação | `observacao` |

### 2.4 Arquivos de Entrada

| Arquivo | Nome | Formato |
|---------|------|---------|
| Lista de CNPJs | `data/entrada/cnpjs.csv` | Coluna: `cnpj` |
| Regras de mapeamento | `data/entrada/mapeamento_tipo_servico.csv` | Colunas: `texto_pdf`, `tipo_de_servico` |
| Lista mestra de serviços | `data/entrada/lista_servicos.csv` | Delimitador: `;` (ponto e vírgula). Coluna principal: `Tese`. Metadados: Status, Área responsável, Objeto da tese, Estado, Ramo de atividade, Regime tributário, Tipo de produto, Observações, Clientes possíveis, Data de criação. 70 teses ativas. |

---

## 3. Fluxo de Navegação Autenticada

### 3.1 MVP vs Stage 2

```
MVP:  Playwright → consulta pública URL direta → pesquisa CNPJ → sem login
S2:   undetected-chromedriver → perfil dedicado + whom.doc9
      → login manual JFAM (1x por sessão) → automação assume na consulta
```

### 3.2 Abordagem: undetected-chromedriver + perfil dedicado

**Decisões técnicas confirmadas durante implementação:**

- **Playwright não funciona** com extensões Chrome (Chrome/Edge removeram side-loading flags). Playwright's bundled Chromium não reconhece credenciais do whom.doc9.
- **Selenium padrão é bloqueado** pelo Chrome (security detection reseta perfil e desconecta).
- **`undetected-chromedriver`** resolve: patcha automação detection, Chrome não reseta settings.
- **Perfil principal do Chrome não funciona** com automação (profile lock, security guards).
- **Perfil dedicado** em `data/navegador/chrome_automacao/` resolve: isolado, sem conflitos, extensão instalada 1x.

### 3.3 Fluxo detalhado

```
1. Usuário fecha Chrome pessoal (Cmd+Q) — obrigatório
2. Script abre Chrome com perfil dedicado (undetected-chromedriver)
   → Chrome abre: perfil de automação com whom.doc9 já instalado
3. ETAPA MANUAL (ÚNICA): usuário clica whom.doc9 → seleciona "JFAM - Pje - 1o grau" → Acessar
   → Redireciona para TRF1 PJe "Quadro de avisos"
   → Script aguarda detectar URL do TRF1 para continuar
4. AUTOMAÇÃO: fechar popup de aviso/certificado (se houver)
   → Seletor: a[aria-label="Fechar"] ou JS: fecharPopupAlertaCertificadoProximoDeExpirar()
   → Popup certificado: div#popupAlertaCertificadoProximoDeExpirar
5. AUTOMAÇÃO: navegar direto para URL de consulta
   → URL direta: /pje/Processo/ConsultaProcesso/listView.seam
   → NÃO precisa clicar no menu ☰ — URL é acessível diretamente
6. AUTOMAÇÃO: preencher CNPJ, pesquisar, filtrar processos, abrir, baixar PDFs
```

**Etapa manual (3):** Feita 1x por sessão. A sessão persiste no perfil dedicado.
O motivo de ser manual: whom.doc9 gerencia certificados digitais via interface própria —
não é possível automatizar a interação com a popup da extensão.

**Etapas 4-6 são 100% automatizadas** — seletores confirmados via HTML real.

### 3.4 O que muda do MVP

| Componente | MVP (Playwright) | Stage 2 (undetected-chromedriver) |
|------------|------------------|-----------------------------------|
| Biblioteca | `playwright` | `undetected-chromedriver` + `selenium` |
| Browser | Chromium bundled | Chrome real do sistema |
| Perfil | Novo a cada vez | Dedicado persistente em `data/navegador/chrome_automacao/` |
| Extensão | Não funciona | whom.doc9 instalado no perfil dedicado |
| Login | Nenhum (consulta pública) | Manual via whom.doc9 (1x por sessão). ÚNICA etapa manual. Popup + navegação são automatizados. |
| URL de consulta | `pje1g-consultapublica.trf1.jus.br/...` | `pje1g.trf1.jus.br/pje/Processo/ConsultaProcesso/listView.seam` |
| Metadados empresa | Não coleta | Scraping no detalhe do processo |
| Download | `expect_download()` | `driver.switch_to.alert.accept()` + download direto |
| Setup 1x | `playwright install chromium` | Instalar whom.doc9 no perfil dedicado |

### 3.5 Mapa de Seletores Confirmados (extraído de HTML real)

| Etapa | Elemento | Seletor Selenium |
|-------|---------|------------------|
| Popup: fechar aviso | `<a class="btn-fechar" aria-label="Fechar">` | `By.CSS_SELECTOR, 'a[aria-label="Fechar"]'` |
| Popup: certificado | `<div id="popupAlertaCertificadoProximoDeExpirar">` | JS: `fecharPopupAlertaCertificadoProximoDeExpirar()` |
| Popup: modal genérico | `<a data-dismiss="modal">` | `By.CSS_SELECTOR, '[data-dismiss="modal"]'` |
| Navegação: URL consulta | Navegação direta (sem menu) | `driver.get(base_url + "/pje/Processo/ConsultaProcesso/listView.seam")` |
| Consulta: Radio CNPJ | `<input id="cnpj">` | `By.ID, "cnpj"` |
| Consulta: Campo CNPJ | `<input id="fPP:dpDec:documentoParte">` | `By.ID, "fPP:dpDec:documentoParte"` |
| Consulta: Pesquisar | `<input id="fPP:searchProcessos">` | `By.ID, "fPP:searchProcessos"` |
| Resultados: Tabela | `<table id="fPP:processosTable">` | `By.ID, "fPP:processosTable"` |
| Resultados: Tabela interna | `<table id="fPP:processosTable:scTabela_table">` | `By.ID, "..."` |
| Resultados: Colunas | Ações, Processo, Órgão, Autuado em, Classe, Polo ativo, Polo passivo, Última mov. | CSS `td.rich-table-cell` |
| Resultados: Click processo | Onclick com `idProcessoSelecionado` | JS submit via A4J.AJAX |
| Alerta: abrir processo | Browser `confirm()` | `driver.switch_to.alert.accept()` |
| Processo: Lista docs | Timeline entries: `{doc_id} - Sentença Tipo A` | Text matching no `divTimeLine` |
| Processo: Preview iframe | `<iframe id="frameHtml">` | `By.ID, "frameHtml"` |
| Processo: Download doc | `<a id="detalheDocumento:download">` | `By.ID, "detalheDocumento:download"` |
| Alerta: download | Browser `confirm()` | `driver.switch_to.alert.accept()` |
| PDF URL direto | `/pje/seam/resource/rest/pje-legacy/documento/download/{doc_id}` | Construção de URL |

### 3.6 Estrutura dos documentos no TRF1

Documentos aparecem em timeline (`divTimeLine`) com padrão:
```
{doc_id_numerico} - {Nome do Documento}
```

**IDs variam de 7 dígitos (2016) a 10+ dígitos (2019+).** Regex deve usar `\d{5,}`.

Exemplos reais:
```
1003793 - Petição Inicial          (7 dígitos, 2016)
3747817 - Petição Inicial          (7 dígitos, 2017)
35667540 - Decisão                 (8 dígitos, 2019)
2185276896 - Sentença Tipo A       (10 dígitos, recente)
```

**Documentos-alvo (confirmados em produção):**
- DECISÃO: nome começa com "Decisão" (inclui "Decisão Interlocutória")
- PETIÇÃO: nome começa com "Petição Inicial" ou "Inicial" (exclui "Emendas a Inicial")
- SENTENÇA: comentada, pode ser reativada

**Download correto:** click doc na timeline → preview no painel → botão `detalheDocumento:download` → confirm → PDF salva via CDP.
**Download incorreto:** `abrirLinkDocumento()` abre nova aba com formato bruto (pode ser HTML, não PDF).

### 3.7 Alertas JavaScript (2 pontos)

1. **Ao clicar em processo** na tabela de resultados: `confirm()` sobre responsabilização → `accept()`
2. **Ao clicar em download** do documento: `confirm()` sobre download → `accept()`

Ambos são `window.confirm()` padrão, tratados com `driver.switch_to.alert.accept()`.

---

## 4. Deduplicação de Downloads

### Regras

| Situação | Ação |
|----------|------|
| CNPJ + processo + tipo_doc já no registro | Pular, usar PDF existente |
| CNPJ existe mas processo é novo | Baixar apenas novos |
| PDF no registro mas arquivo sumiu | Re-baixar e atualizar |
| Forçar re-download | Flag `--forcar-download` / toggle na UI |

---

## 5. Scraping de Metadados da Empresa

Campos extraídos da página de detalhe do processo: `empresa`, `cidade_uf_matriz`, `atividade_principal`, `atividade_secundaria`, `capital_social`, `local_processo`, `advogado`.

Cache por CNPJ: coletar no primeiro processo, reutilizar para os seguintes.

---

## 6. Gap Analysis

### Fluxo

```
1. Classificação → set de serviços encontrados para o CNPJ
2. Carregar lista_servicos.csv → set completo
3. Gap = lista_mestra − servicos_encontrados
4. Itens REVISÃO NÃO contam como encontrados (conservador)
5. Resolver revisão → recalcular gap automaticamente
```

### Estrutura do relatório Excel (4 abas)

```
relatorio_de_oportunidades_{cnpj}_{date}.xlsx
├── Aba 1: "Dados da Empresa" (resumo, 1 linha)
├── Aba 2: "Serviços Identificados" (1 linha por documento)
├── Aba 3: "Oportunidades" ← PRODUTO PRINCIPAL
└── Aba 4: "Triagem Pendente" (se houver)
```

---

## 7. Extrator de Trechos (D1-5 — Implementado)
### Estratégia final (validada contra 79 PDFs reais)

Princípio: extrair a zona certa com a regra mais simples possível. O classificador (D1-9) decide o tipo de serviço — o extrator apenas entrega o texto.
DECISÃO — heading-based (cascata):

Heading: DECISÃO, DESPACHO/DECISÃO, FUNDAMENTO E DECIDO (space-normalized)
Anchor: sinais semânticos ("Trata-se de Mandado", "Cuida-se de", etc.)
Embedding: OpenAI text-embedding-3-small com chunking
Fallback: primeiros 1000 chars


Resultado: 92%+ dos documentos usam heading com sucesso

PETIÇÃO — positional:

Extrai últimos 6000 chars limpos do documento
Heading detection existe apenas para auditoria (não dirige extração)
Resultado: funciona para todos os documentos com conteúdo, independente do escritório

Configuração via .env:
EXTRACT_CHARS_DECISAO=1000
EXTRACT_CHARS_PETICAO=6000
Limpeza de texto

Capas TRF1 detectadas por conteúdo (Justiça Federal + PJe)
Footers: assinaturas eletrônicas, URLs PJe, números de documento
Headers: nomes de escritórios, endereços repetidos
Dupla verificação de documento vazio (pré e pós limpeza)

Quality gate

Alpha ratio mínimo: 0.50 (detecta PDFs com encoding quebrado)
Comprimento mínimo: 80 chars
Embedding safety net dispara automaticamente quando quality gate falha

Auditoria

CSV por CNPJ: data/saida/auditoria_extracao_{cnpj}.csv (sobrescreve)
19 colunas incluindo variation_tag, heading_audit, quality_alpha_ratio

---

## 8. Segurança de Dados

### 8.1 Medidas implementadas

| Categoria | Medida |
|-----------|--------|
| Credenciais | API keys em `.env` (nunca no código). `.env` no `.gitignore`. |
| Dados de clientes | PDFs e relatórios apenas no disco local. Nenhum upload automático. |
| APIs externas | Apenas trechos de texto enviados. Nunca CNPJ, nome empresa, número processo ou PDF completo. |
| Acesso | Streamlit em localhost/rede local. Sem exposição à internet. |
| Integridade | Validação CNPJ, path sanitization, auditoria.log. |
| Código | Sem eval/exec, sem SQL, dependências fixadas. |

### 8.2 Checklist de deploy

```
□ .env criado (nunca compartilhar)
□ .gitignore inclui: .env, data/navegador/, data/documentos/, data/saida/
□ Disco criptografado (BitLocker/FileVault)
□ Backup regular de data/saida/
□ Acesso à máquina restrito a operadores
□ Rede protegida (não expor Streamlit à internet)
□ Atualizar API keys periodicamente
□ Revisar auditoria.log semanalmente
```

---

## 9. UI/UX — Design Profissional para Escritório Jurídico-Tributário

### 9.1 Filosofia de Design

O sistema será usado diariamente por operadores de um escritório de advocacia tributária. A interface deve transmitir **seriedade profissional**, **confiança nos dados** e **eficiência operacional** — como uma ferramenta interna de alta performance, não um produto SaaS ou uma landing page.

| Princípio | Significado | Anti-padrão a evitar |
|-----------|------------|---------------------|
| **Sobriedade** | Cores contidas, tipografia limpa, sem elementos decorativos | Gradientes, ícones coloridos, animações desnecessárias |
| **Densidade controlada** | Informação suficiente sem sobrecarregar; detalhes sob demanda | Tabelas com 15+ colunas visíveis; trechos jurídicos longos sem collapse |
| **Rastreabilidade** | Cada classificação tem justificativa visível para o operador | "Caixa preta" — resultado sem explicação de como chegou ali |
| **Eficiência** | Fluxo mínimo de cliques do input ao resultado final | Múltiplas telas de confirmação; wizards desnecessários |
| **Linguagem de domínio** | Todos os termos são do vocabulário jurídico-tributário | Jargão técnico: "pipeline", "embedding", "API call", "threshold" |

### 9.2 Paleta de Cores

#### Cores primárias

| Cor | Hex | Uso |
|-----|-----|-----|
| **Preto** | `#1A1A1A` | Texto principal, cabeçalhos, barra de navegação |
| **Grafite** | `#2D2D2D` | Texto secundário, subtítulos |
| **Prata** | `#C0C0C0` | Bordas, separadores, elementos inativos |
| **Prata clara** | `#E8E8E8` | Fundos de seção, alternância de linhas em tabelas |
| **Laranja** | `#D4700A` | Ação principal (botões CTA), barra de acento, aba ativa |
| **Laranja suave** | `#F5E6D0` | Fundo de destaques, avisos moderados |
| **Branco** | `#FFFFFF` | Fundo principal, cards |

#### Cores de status (restritas a indicadores de estado)

| Status | Cor fundo | Cor texto | Uso |
|--------|-----------|-----------|-----|
| **Confirmado** | `#E6F4E6` | `#1A6B1A` | Classificação por regra (alta confiança) |
| **Automático** | `#F5E6D0` | `#8B5E0A` | Classificação por embedding ou LLM |
| **Pendente** | `#FCE8E8` | `#A33030` | Itens que precisam de revisão humana |

#### Regras de aplicação

- **Laranja é reservado para ação**: botão "Gerar Consulta", aba ativa, barra de acento no topo de cards. Nunca para fundo de página ou decoração.
- **Preto e prata dominam**: 90% da interface é preto (texto), branco (fundo) e prata (estrutura). Laranja aparece em < 10% da área visual.
- **Cores de status só em indicadores**: pills de status, contadores, ícones. Nunca em fundos de seção inteira.
- **Sem gradientes, sombras ou efeitos**: superfícies planas, bordas finas (0.5px prata). Estilo editorial, não material design.

### 9.3 Tipografia

| Elemento | Tamanho | Peso | Cor |
|----------|---------|------|-----|
| Título de página | 20px | 500 (medium) | `#1A1A1A` |
| Título de seção | 16px | 500 | `#1A1A1A` |
| Texto padrão | 14px | 400 (regular) | `#1A1A1A` |
| Texto secundário | 13px | 400 | `#2D2D2D` |
| Label de campo | 12px | 400 | `#666666` |
| Dado em tabela | 13px | 400 | `#1A1A1A` |
| Cabeçalho de tabela | 13px | 500 | `#2D2D2D` |
| Botão principal | 14px | 500 | `#FFFFFF` sobre `#D4700A` |
| Botão secundário | 13px | 400 | `#1A1A1A` com borda prata |

**Sem fontes serifadas.** Fonte do sistema (sans-serif) para toda a interface. Serifa transmite editorial/marketing; sans-serif transmite ferramenta/operação.

### 9.4 Componentes de Interface

#### Card de empresa

```
┌────────────────────────────────────────────────────────┐
│ ▊ (barra laranja 4px no topo)                          │
│                                                         │
│ ABC Comércio e Serviços Ltda          CNPJ formatado    │
│                                                         │
│ Cidade/UF: São Paulo/SP      Capital: R$ 1.200.000     │
│ Atividade: Comércio varejista  Processos: 8 encontrados │
│                                                         │
└────────────────────────────────────────────────────────┘
```

- Borda: 0.5px prata. Sem sombra.
- Barra de acento laranja no topo (4px) — único elemento de cor no card.
- Dados em grid 2 colunas. Labels em cinza, valores em preto.

#### Tabela de serviços identificados

```
┌──────────┬──────────────────┬──────────────┬────────────┐
│ Processo │ Tipo de serviço  │ Documento    │ Status     │
├──────────┼──────────────────┼──────────────┼────────────┤
│ 0001234  │ Excl. ICMS PIS.. │ SENTENÇA     │ ● Confirm. │
│ 0005678  │ Anulatória multa │ DECISÃO      │ ● Automát. │
│ 0009012  │ —                │ PETIÇÃO      │ ● Pendente │
└──────────┴──────────────────┴──────────────┴────────────┘
```

- Linhas alternadas: branco / `#F5F5F5` (sem cor, apenas cinza neutro).
- Status é uma pill colorida (cores de status acima).
- Clicar na linha expande para mostrar trecho extraído (disclosure progressivo).
- **Trecho NÃO aparece por padrão** — evita sobrecarga visual.
- Cabeçalho fixo (freeze) para tabelas longas.

#### Métricas resumo

```
┌───────────────┐  ┌───────────────┐  ┌───────────────┐
│      28       │  │      12       │  │       3       │
│ Oportunidades │  │ Serv. ident.  │  │ Aguar. revis. │
│   (verde)     │  │  (laranja)    │  │  (vermelho)   │
└───────────────┘  └───────────────┘  └───────────────┘
```

- Cards de métrica com fundo sutil da cor de status.
- Número grande (22px, peso 500). Label pequeno (12px).
- 3 cards máximo em uma linha. Sem excesso de métricas.

#### Botões

| Tipo | Estilo | Quando usar |
|------|--------|-------------|
| Primário | Fundo laranja, texto branco | "Gerar Consulta", "Confirmar" |
| Secundário | Fundo branco, borda prata | "Exportar Relatório", "Ver detalhes" |
| Terciário | Sem fundo, texto cinza | "Configurações", "Pular" |

- **Apenas 1 botão primário por tela.** Se há duas ações importantes, uma é primária e a outra é secundária.
- Botões sem ícones por padrão. Se ícone necessário, usar apenas texto unicode simples (📥 para download).

#### Navegação (abas)

```
┌──────────────┬────────────┬────────────────┬──────────┐
│ Nova consulta│ Resultados │ Oportunidades  │ Revisão  │
│  (ATIVA)     │            │                │   (3)    │
└──────────────┴────────────┴────────────────┴──────────┘
```

- Aba ativa: fundo laranja, texto branco.
- Abas inativas: fundo prata clara, texto grafite.
- Badge numérico na aba "Revisão" quando há itens pendentes (ex: "(3)").
- **Ordem das abas segue o fluxo de trabalho**: Input → Resultados → Oportunidades → Revisão.

### 9.5 Telas Detalhadas

#### Tela 1: "Nova Consulta"

**Objetivo:** O operador insere CNPJ(s) e inicia a consulta com o mínimo de cliques.

```
┌─────────────────────────────────────────────────────┐
│  automação jurídica trf1                             │
│  ▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔▔                          │
│  ┌───────────┬──────────┬──────────────┬──────────┐  │
│  │Nova conslt│Resultados│Oportunidades │ Revisão  │  │
│  └───────────┴──────────┴──────────────┴──────────┘  │
│                                                      │
│  CNPJ                                                │
│  ┌──────────────────────────────────┐                │
│  │ 12.345.678/0001-99              │                │
│  └──────────────────────────────────┘                │
│                                                      │
│  — ou —                                              │
│                                                      │
│  📎 Carregar lista de CNPJs (arquivo CSV)            │
│                                                      │
│  ┌──────────────────┐                                │
│  │  Gerar Consulta  │  ← botão laranja              │
│  └──────────────────┘                                │
│                                                      │
│  ┌─── Progresso ──────────────────────────────────┐  │
│  │ ✓ CNPJs validados: 3 de 3                      │  │
│  │ ✓ Conexão com TRF1 estabelecida                │  │
│  │ ⏳ Baixando documentos... (5 de 12)             │  │
│  │ ○ Extraindo trechos                             │  │
│  │ ○ Classificando serviços                        │  │
│  │ ○ Gerando relatório                             │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ▸ Configurações avançadas                           │
│    □ Forçar re-download de documentos já baixados    │
└─────────────────────────────────────────────────────┘
```

**Decisões de design:**
- Campo CNPJ com máscara automática (XX.XXX.XXX/XXXX-XX).
- Progresso usa linguagem clara: "Baixando documentos" (não "Downloading PDFs").
- "Configurações avançadas" oculto por padrão (collapsible) — operadores comuns não precisam ver.
- Sem barra lateral. Navegação horizontal por abas.
- **Único botão primário na tela: "Gerar Consulta".**

#### Tela 2: "Resultados"

**Objetivo:** Visão geral da empresa + serviços identificados. Ponto de partida para análise.

```
┌─────────────────────────────────────────────────────┐
│  [abas: Nova consulta | RESULTADOS | Oportunidades | Revisão (3)] │
│                                                      │
│  ┌─ Card empresa ─────────────────────────────────┐  │
│  │ ▊ ABC Comércio Ltda      12.345.678/0001-99    │  │
│  │ São Paulo/SP  |  Comércio varejista  |  R$1.2M  │  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐     │
│  │    28      │  │    12      │  │     3      │     │
│  │Oportunid.  │  │Serv.ident. │  │Aguar.rev.  │     │
│  └────────────┘  └────────────┘  └────────────┘     │
│                                                      │
│  Serviços identificados                              │
│  ┌──────────┬─────────────────┬──────────┬────────┐  │
│  │ Processo │ Tipo de serviço │Documento │ Status │  │
│  ├──────────┼─────────────────┼──────────┼────────┤  │
│  │ 0001234..│ Excl. ICMS PIS  │SENTENÇA  │●Conf.  │  │
│  │ ▸ (expandir para ver trecho)                   │  │
│  │ 0005678..│ Anulatória mult │DECISÃO   │●Autom. │  │
│  │ 0009012..│ —               │PETIÇÃO   │●Pend.  │  │
│  └──────────┴─────────────────┴──────────┴────────┘  │
│                                                      │
│  ┌────────────────────┐                              │
│  │ Exportar relatório │  ← botão secundário          │
│  └────────────────────┘                              │
└─────────────────────────────────────────────────────┘
```

**Decisões de design:**
- Card empresa no topo, compacto. Dados essenciais em uma linha.
- Métricas resumo destacam o que importa: oportunidades primeiro (é o produto).
- Tabela mostra 4 colunas por padrão. Trecho extraído está oculto (expandir clicando na linha).
- Status com linguagem: "Confirmado", "Automático", "Pendente" — nunca "HIGH", "MEDIUM", "REVIEW".
- Exportar é botão secundário (não é a ação principal desta tela — o operador quer ver primeiro).

#### Tela 3: "Oportunidades" (TELA PRINCIPAL DO NEGÓCIO)

**Objetivo:** Mostrar os serviços que a equipe pode oferecer. Esta é a tela que o time de prospecção abre.

```
┌─────────────────────────────────────────────────────┐
│  [abas: Nova consulta | Resultados | OPORTUNIDADES | Revisão (3)] │
│                                                      │
│  ┌─ Card empresa (compacto) ──────────────────────┐  │
│  │ ▊ ABC Comércio Ltda  |  São Paulo/SP  |  R$1.2M│  │
│  └────────────────────────────────────────────────┘  │
│                                                      │
│  28 serviços disponíveis para oferecer               │
│                                                      │
│  Estes serviços não foram encontrados nos            │
│  processos deste CNPJ:                               │
│                                                      │
│  ┌───┬─────────────────────────────────────────────┐ │
│  │ # │ Serviço disponível                          │ │
│  ├───┼─────────────────────────────────────────────┤ │
│  │ 1 │ Mandado de Segurança - Exclusão IRPJ       │ │
│  │ 2 │ Repetição de Indébito - IPI Alíquota Zero  │ │
│  │ 3 │ Ação Declaratória - ISS base de cálculo    │ │
│  │...│ ...                                         │ │
│  │28 │ Compensação tributária - INSS patronal      │ │
│  └───┴─────────────────────────────────────────────┘ │
│                                                      │
│  ┌──────────────────────────┐                        │
│  │ Exportar oportunidades   │                        │
│  └──────────────────────────┘                        │
│                                                      │
│  ┌─ Aviso ───────────────────────────────────────┐   │
│  │ ⚠ 3 itens estão aguardando revisão.           │   │
│  │   Resolver pode revelar mais oportunidades.   │   │
│  │   [ Ir para revisão → ]                       │   │
│  └───────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────┘
```

**Decisões de design:**
- **Tabela simples**: apenas número e nome do serviço. Sem colunas extras. O operador quer uma lista limpa para prospecção.
- Texto introdutório curto e direto: "Estes serviços não foram encontrados nos processos deste CNPJ."
- Aviso sobre itens pendentes em box sutil (fundo laranja suave). Link direto para revisão.
- Card empresa no topo para contexto rápido (quem é o cliente).

#### Tela 4: "Revisão"

**Objetivo:** Resolver classificações incertas. Interface guiada, um item por vez.

```
┌─────────────────────────────────────────────────────┐
│  [abas: Nova consulta | Resultados | Oportunidades | REVISÃO (3)] │
│                                                      │
│  Triagem pendente — 3 itens                          │
│                                                      │
│  ┌─ Item 1 de 3 ────────────────────────────────┐    │
│  │                                               │    │
│  │ Processo: 0009012-45.2021.4.01.3400          │    │
│  │ Documento: SENTENÇA                           │    │
│  │                                               │    │
│  │ Trecho do documento:                          │    │
│  │ ┌─────────────────────────────────────────┐   │    │
│  │ │ "Vistos etc. Trata-se de mandado de     │   │    │
│  │ │  segurança impetrado por ABC Comércio   │   │    │
│  │ │  Ltda em face da União Federal, em que  │   │    │
│  │ │  se pretende a exclusão do ICMS..."     │   │    │
│  │ └─────────────────────────────────────────┘   │    │
│  │                                               │    │
│  │ Sugestões do sistema:                         │    │
│  │  • Mandado de Segurança - ICMS (72%)         │    │
│  │  • Mandado de Segurança - ISS (58%)          │    │
│  │                                               │    │
│  │ Tipo de serviço: [ Selecionar ▾          ]   │    │
│  │                                               │    │
│  │ □ Adicionar ao mapeamento de regras           │    │
│  │   (futuras ocorrências serão classificadas    │    │
│  │    automaticamente)                           │    │
│  │                                               │    │
│  │ ┌───────────┐  ┌────────┐                    │    │
│  │ │ Confirmar │  │ Pular  │                    │    │
│  │ └───────────┘  └────────┘                    │    │
│  │                                               │    │
│  └───────────────────────────────────────────────┘    │
│                                                      │
│  Ao confirmar, as oportunidades são recalculadas     │
│  automaticamente.                                    │
└─────────────────────────────────────────────────────┘
```

**Decisões de design:**
- **Um item por vez** (não tabela). Reduz carga cognitiva e evita erros.
- Trecho exibido em box cinza com fonte monospace para destaque.
- "Sugestões do sistema" em linguagem simples com % (não "cosine similarity 0.72").
- Dropdown com todos os tipos de serviço disponíveis.
- Checkbox "Adicionar ao mapeamento" com explicação em linguagem clara.
- **"Confirmar" é o botão primário (laranja). "Pular" é terciário (sem cor).**
- Feedback imediato: ao confirmar, oportunidades são recalculadas.

### 9.6 Riscos de UI/UX Identificados e Mitigações

#### Risco 1: Sobrecarga de informação (ALTO)

**Problema:** O operador vê dados da empresa + tabela de serviços + trechos jurídicos + classificação + métodos em uma única tela. Paralisia de informação.

**Mitigação:**
- Disclosure progressivo: trecho jurídico oculto por padrão (expandir ao clicar).
- Coluna "método" (REGRA/EMBEDDING/LLM) **não aparece** na interface padrão — apenas no Excel exportado. Operador vê apenas "Confirmado/Automático/Pendente".
- Card empresa compacto (1 linha), não expansível na tela de resultados.
- Máximo 4 colunas visíveis na tabela principal.

#### Risco 2: Navegação ambígua (MÉDIO)

**Problema:** O operador não sabe se já gerou consulta para um CNPJ, ou em que etapa está.

**Mitigação:**
- Badge numérico na aba "Revisão" mostrando itens pendentes.
- Indicador na aba "Resultados" e "Oportunidades": cinza se sem dados, preto se com dados carregados.
- Na tela "Nova Consulta", se o CNPJ já tem dados: mostrar aviso "Este CNPJ já foi consultado em DD/MM. Gerar novamente?"
- Progresso linear visível durante execução com estados claros (✓ concluído, ⏳ em andamento, ○ aguardando).

#### Risco 3: Rastreabilidade jurídica (ALTO)

**Problema:** O operador (ou o advogado) precisa justificar por que um serviço foi classificado de determinada forma. Se a interface é opaca, a ferramenta perde credibilidade.

**Mitigação:**
- Ao expandir uma linha na tabela de serviços, o operador vê:
  - O trecho do documento que gerou a classificação
  - A regra ou sugestão que determinou o tipo de serviço
  - O nível de confiança em linguagem simples
- No Excel exportado, colunas adicionais: `metodo`, `trecho_extraido`, `observacao`.
- Log de auditoria registra quem reclassificou o quê e quando.
- O sistema **nunca esconde que uma classificação é automática**. O indicador "Automático" é visível.

#### Risco 4: Eficiência de workflow (MÉDIO)

**Problema:** O operador processa 10-20 CNPJs por dia. Se cada CNPJ requer múltiplos cliques para chegar às oportunidades, produtividade cai.

**Mitigação:**
- De "Gerar Consulta" até "Oportunidades": máximo 2 cliques (gerar → aba oportunidades).
- Exportar Excel: 1 clique a partir de qualquer tela de resultados.
- Batch processing: carregar CSV com múltiplos CNPJs e gerar tudo de uma vez.
- Consolidado multi-CNPJ em um único Excel para análise cruzada.
- Revisão em fila (um por um) evita vai-e-vem entre tabela e formulário.

#### Risco 5: Densidade em telas pequenas (BAIXO-MÉDIO)

**Problema:** Se o operador usa notebook (1366x768), tabelas e métricas podem ficar comprimidas.

**Mitigação:**
- Layout responsivo: métricas em 3 colunas → 1 coluna em telas menores.
- Tabela com scroll horizontal se necessário (melhor que comprimir colunas até ficarem ilegíveis).
- Tamanhos de fonte mínimos: 13px para dados, 12px para labels. Nada menor.
- Streamlit `wide` layout desabilitado por padrão (centered é melhor para leitura de tabelas).

#### Risco 6: Acessibilidade (BAIXO-MÉDIO)

**Problema:** Contraste insuficiente, elementos sem label, navegação por teclado deficiente.

**Mitigação:**
- Contraste mínimo 4.5:1 para todo texto (verificar preto sobre branco: 15.3:1 ✓; laranja sobre branco: verificar).
- Laranja `#D4700A` sobre branco = ratio 4.56:1 (passa WCAG AA para texto grande). Para texto pequeno, usar laranja como fundo com texto branco (`#FFFFFF` sobre `#D4700A` = 4.56:1 — AA para texto ≥ 14px bold).
- Todas as cores de status têm texto escuro sobre fundo claro (verde escuro/claro, vermelho escuro/claro) — testados para contraste.
- Labels descritivos em todos os campos de formulário.
- Tab order lógico na tela de revisão (trecho → sugestões → dropdown → checkbox → botões).
- Sem informação transmitida apenas por cor — pills de status têm texto ("Confirmado", "Pendente") além da cor.

### 9.7 O Que a Interface NÃO Mostra

Tão importante quanto o que exibir é o que **omitir** da interface para manter a limpeza profissional:

| Informação | Onde aparece | Onde NÃO aparece |
|-----------|-------------|-----------------|
| Método de classificação (REGRA/EMBEDDING/LLM) | Excel exportado, log de auditoria | Interface — operador vê apenas "Confirmado/Automático/Pendente" |
| Score de embedding (0.85, 0.72) | Excel exportado (coluna `observacao`) | Interface — operador vê "72%" em linguagem simples na tela de revisão |
| Número de tokens extraídos | Log de auditoria | Interface — irrelevante para operador |
| Tempo de processamento por PDF | Log de auditoria | Interface — apenas barra de progresso geral |
| Erros de API (OpenAI, Anthropic) | Log de auditoria, console | Interface — se camada falha, item vai para REVISÃO silenciosamente |
| Configurações técnicas (threshold, n_chars) | Painel "Configurações avançadas" (colapsado) | Visível por padrão — apenas para admin/dev |
| Nome do modelo LLM usado | Log | Interface — operador não precisa saber que é "Claude Haiku" |

### 9.8 Implementação no Streamlit

#### Custom CSS para o tema jurídico

```python
st.markdown("""
<style>
    /* Paleta escritório jurídico */
    :root {
        --cor-laranja: #D4700A;
        --cor-laranja-suave: #F5E6D0;
        --cor-preto: #1A1A1A;
        --cor-grafite: #2D2D2D;
        --cor-prata: #C0C0C0;
        --cor-prata-clara: #E8E8E8;
    }

    /* Botão primário */
    .stButton > button[kind="primary"] {
        background-color: var(--cor-laranja);
        color: white;
        border: none;
        font-weight: 500;
    }

    /* Remover estilo Streamlit padrão */
    .stApp header { display: none; }           /* Esconder hamburger */
    .stDeployButton { display: none; }          /* Esconder "Deploy" */
    #MainMenu { visibility: hidden; }           /* Esconder menu principal */
    footer { visibility: hidden; }              /* Esconder "Made with Streamlit" */

    /* Tabela limpa */
    .stDataFrame { border: 0.5px solid var(--cor-prata); }
    .stDataFrame th { background: var(--cor-prata-clara); }

    /* Abas */
    .stTabs [data-baseweb="tab-list"] button[aria-selected="true"] {
        background-color: var(--cor-laranja);
        color: white;
    }
</style>
""", unsafe_allow_html=True)
```

#### Mapeamento de termos: técnico → negócio

```python
TERMOS_NEGOCIO = {
    # Confiança
    "HIGH": "Confirmado",
    "MEDIUM": "Automático",
    "LLM": "Automático",
    "REVIEW": "Pendente",

    # Status de progresso
    "loading_cnpjs": "Validando CNPJs...",
    "downloading": "Baixando documentos...",
    "extracting": "Extraindo trechos relevantes...",
    "classifying": "Classificando serviços...",
    "generating": "Gerando relatório...",
    "done": "Consulta concluída.",

    # Erros (sem jargão)
    "api_error": "Classificação automática temporariamente indisponível. Item adicionado à revisão.",
    "pdf_error": "Não foi possível ler este documento. Verifique o arquivo manualmente.",
    "login_error": "Sessão expirada. Faça login novamente pelo whom.doc9.",
    "no_results": "Nenhum processo encontrado para este CNPJ no TRF1.",
}
```

---

## 10. Arquitetura

```
┌──────────────────────────────────────────────────────────────┐
│                      STREAMLIT UI                             │
│  Tema: profissional jurídico (laranja, preto, prata)         │
│  Tela 1: Nova Consulta   Tela 2: Resultados                 │
│  Tela 3: Oportunidades   Tela 4: Revisão                    │
│  Linguagem 100% domínio, zero jargão técnico                 │
└──────────────────────┬───────────────────────────────────────┘
                       │
┌──────────────────────▼───────────────────────────────────────┐
│                 ORQUESTRADOR DE CONSULTA                      │
│  Etapa 1: input_loader → CNPJs                               │
│  Etapa 2: downloader (whom.doc9 → dashboard → consulta)      │
│           → dedup → metadados empresa → PDFs                 │
│  Etapa 3: extrator (strategy pattern por tipo_doc)           │
│  Etapa 4: classificação (3 camadas → tipo_de_servico)        │
│  Etapa 5: gap analysis (lista mestra − encontrados)          │
│  Etapa 6: relatório Excel 4 abas + triagem                  │
│  ✅ Validação após cada etapa                                │
└──────────────────────────────────────────────────────────────┘
```

---

## 11. Gates de Validação

| Gate | Checks principais | Ação se falhar |
|------|-------------------|----------------|
| **1. Input** | CNPJs válidos, arquivos existem | Parar com mensagem clara |
| **2. Auth/Download** | Extensão OK, login OK, ≥ 1 PDF, dedup funciona, metadados coletados | Parar ou warning |
| **3. Extração** | PDF legível, texto extraído, heading encontrado | Warning, usar fallback |
| **4. Classificação** | Mapping OK, index OK, APIs OK, taxa REVISÃO < 70% | Warning por camada |
| **5. Gap** | Lista mestra OK, gap ≥ 0, REVISÃO excluído | Validação lógica |
| **6. Output** | Excel 4 abas, colunas corretas, nomeação correta | Parar ou auto-corrigir |

---

## 12. Plano de Execução — Dia a Dia

### DIA 1: Fundação + Pipeline + Classificação + Gap Analysis

| Bloco | Est. | Tarefa | Validação |
|-------|------|--------|-----------|
| **D1-1** | 45min | ✅ **CONCLUÍDO** — Scaffold repo: pastas, .env.example, .gitignore, requirements.txt, pyproject.toml, setup.sh, validar_ambiente.py | `from core.config import settings` ✓ |
| **D1-2** | 30min | ✅ **CONCLUÍDO** — config.py (settings singleton, .env loader, fail-fast), modelos.py (TipoDocumento, NivelConfianca, MetodoClassificacao, RegistroDownload, DadosEmpresa, RelatorioExtracao, ResultadoClassificacao, TeseMestra, ItemRelatorio, Oportunidade, StatusPipeline, TERMOS_NEGOCIO) | Import + instanciação ✓ |
| **D1-3** | 30min | ✅ **CONCLUÍDO** — input_loader.py: carregar_cnpjs(), carregar_mapeamento(), carregar_lista_servicos() (retorna TeseMestra com metadados), nomes_teses(), validar_inputs(), formatar_cnpj(). Auto-detect delimitador (`;` ou `,`). Testado com dados reais (70 teses). | Gate 1 ✓ |
| **D1-4** | 2h | ✅ **CONCLUÍDO** — `core/downloader.py` (~1790 linhas, 30 funções). Browser automation completa com `undetected-chromedriver`. 34/34 processos capturados para CNPJ de teste. Docs-alvo: DECISÃO (nome startswith "Decisão") + PETIÇÃO (nome startswith "Petição Inicial" ou "Inicial", excluindo "Emendas"). SENTENÇA comentada. Download via preview + `detalheDocumento:download` + confirm dialog (réplica exata do fluxo humano). Timeline search server-side para contornar scroll infinito. Dedup via `registro_de_downloads.csv`. Ver Seção 13c para lições. | 34/34 processos ✓, todos docs-alvo ✓ |
| D1-5 | 1.5h | ✅ CONCLUÍDO — core/extrator.py (683 linhas, 20 funções). PyMuPDF text extraction. Estratégia simplificada: DECISÃO usa heading-based (heading→anchor→embedding→fallback, 1000 chars); PETIÇÃO usa positional (últimos 6000 chars limpos — office-agnostic, sem dependência de heading). Quality gate com alpha ratio. Embedding safety net via OpenAI. Auditoria CSV por CNPJ. Validado contra 79 PDFs: 57 ok, 20 vazios, 2 fallback, 1 texto_ilegivel (PDF encoding quebrado). Heading detection para PETIÇÃO é apenas auditoria. | 79/79 PDFs com status correto ✓ |
| **D1-6** | 30min | **Camada 1: regras** | 5 trechos corretos |
| **D1-7** | 1.5h | **Camada 2: embeddings** + construir_embeddings.py | Index OK, top-1 OK |
| **D1-8** | 1.5h | **Camada 3: LLM** (Claude Haiku) | JSON válido 5+ trechos |
| **D1-9** | 45min | **Motor orquestrador** C1→C2→C3→REVISÃO | Cascade OK |
| **D1-10** | 1h | **Gap analysis**: lista mestra − encontrados, REVISÃO excluído | Gap correto |
| **D1-11** | 1.5h | **CLI gerar_consulta.py + Excel 4 abas** | Pipeline completo 1-2 CNPJs |
| **D1-12** | 30min | **Validação Dia 1** | Outputs validados |

### DIA 2: Streamlit UI + Segurança + Polish

| Bloco | Est. | Tarefa | Validação |
|-------|------|--------|-----------|
| **D2-1** | 3h | **Streamlit telas 1-2**: tema jurídico (CSS custom), Nova Consulta + Resultados. Card empresa, métricas, tabela com disclosure, progresso. Termos de negócio. | Input → gerar → ver resultados |
| **D2-2** | 1.5h | **Tela 3: Oportunidades**: lista gap, aviso pendentes, exportar | Gap exibido, contagem OK |
| **D2-3** | 1.5h | **Tela 4: Revisão**: item por vez, sugestões %, dropdown, "Adicionar ao mapeamento", recalcular gap ao confirmar | Override → gap atualiza |
| **D2-4** | 45min | **Consolidado multi-CNPJ** | Excel consolidado OK |
| **D2-5** | 1h | **Segurança**: validação inputs, sanitização, auditoria.log, .env check | Inputs ruins rejeitados |
| **D2-6** | 45min | **Sessão**: detectar expirada, "Testar Conexão", mensagens claras | Re-login funciona |
| **D2-7** | 1h | **Teste end-to-end** via UI | Fluxo suave |
| **D2-8** | 30min | **README** | Setup do zero funciona |

---

## 13. Estrutura de Pastas

```
automacao-juridica-trf1/
├── .env.example
├── .gitignore
├── pyproject.toml
├── requirements.txt
├── README.md
│
├── core/
│   ├── __init__.py
│   ├── config.py
│   ├── modelos.py
│   ├── input_loader.py
│   ├── downloader.py
│   ├── extrator.py
│   └── gap_analysis.py
│
├── classificacao/
│   ├── __init__.py
│   ├── regras.py
│   ├── embeddings.py
│   ├── llm_classificador.py
│   └── motor.py
│
├── ui/
│   └── app.py
│
├── scripts/
│   ├── gerar_consulta.py
│   ├── construir_embeddings.py
│   ├── testar_extensao.py          # Discovery (Selenium, já usado)
│   └── exportar_cookies.py         # Backup: export cookies (se undetected-chromedriver falhar)
│
├── data/
│   ├── entrada/
│   ├── saida/
│   ├── documentos/
│   ├── embeddings/
│   └── navegador/
│
└── testes/
```

---

## 13b. Dependências Atualizadas (requirements.txt)

```
# Pipeline core
undetected-chromedriver>=3.5
selenium>=4.15
setuptools                    # Necessário para Python 3.13 (distutils removido)
pymupdf>=1.23
pandas>=2.0
openpyxl>=3.1
pydantic>=2.0

# Classificação — Camada 2 (embeddings)
openai>=1.0
faiss-cpu>=1.7
numpy>=1.24

# Classificação — Camada 3 (LLM)
anthropic>=0.40

# UI
streamlit>=1.30

# Configuração e segurança
python-dotenv>=1.0

# Utilitários
httpx>=0.25
```

**Removido:** `playwright` (não funciona com extensões Chrome).
**Adicionado:** `undetected-chromedriver`, `selenium`, `setuptools`.

---

## 13c. Lições de Implementação (D1-1 a D1-4)

Registradas para referência e para evitar re-trabalho em futuras sessões.

### Browser automation
1. **Playwright não carrega extensões Chrome** — Chrome/Edge removeram flags de side-loading. Chromium bundled do Playwright não reconhece credenciais do whom.doc9.
2. **CDP (Chrome DevTools Protocol)** — tentado e falhou. Chrome no macOS não aceita `--remote-debugging-port` de forma confiável (processo pai ignora a flag).
3. **Selenium padrão** — Chrome detecta `navigator.webdriver=true` e reseta o perfil (security feature).
4. **Perfil principal do Chrome** — tem profile lock e security guards que impedem automação.
5. **Solução final:** `undetected-chromedriver` + perfil dedicado em `data/navegador/chrome_automacao/`.
6. **Python 3.13:** removeu `distutils` do stdlib. `undetected-chromedriver` depende dele via `setuptools`.
7. **Versão Chrome vs chromedriver:** devem ser iguais (major version). Script detecta automaticamente com `--version`.
8. **`page_load_strategy='eager'`** necessário para evitar timeout em páginas pesadas do TRF1.

### TRF1 PJe — comportamento do site (confirmado por testes)
1. **Processos SEMPRE abrem em nova aba** — nunca na mesma aba. Não implementar lógica de same-tab.
2. **Timeline usa scroll infinito** (`bindPaginacaoInfinita`) — somente busca server-side via `divTimeLine:txtPesquisa` + `divTimeLine:btnPesquisar` encontra todos os documentos.
3. **RichFaces overlays** (`rich-mpnl-content`, `rich-mpnl-mask-div`) são elementos **estruturais sempre visíveis** no DOM — NÃO são indicadores de loading. Verificar somente `modalStatusContainer` para detectar fim de AJAX.
4. **AJAX da pesquisa de CNPJ** (pipeline completo: reCAPTCHA → A4J.AJAX → server → DOM update) leva 5-8s. `time.sleep(5)` mínimo + RichFaces loading wait + margem 1s antes de ler tabela.
5. **Paginação da tabela**: após AJAX, `cells[N].text.strip()` pode retornar vazio — usar JS `innerText` como fallback.
6. **Dois alerts JavaScript** obrigatórios: ao abrir processo (`confirm()`) e ao baixar documento (`confirm("Confirma o download do documento?")`).
7. **Document IDs variam de 7 dígitos** (processos antigos, 2016) **a 10+ dígitos** (processos recentes). Regex deve usar `\d{5,}` mínimo.
8. **Spans da timeline contêm caracteres Unicode invisíveis** (NBSP `\u00a0`, zero-width joiners `\u200b-\u200d`, BOM `\ufeff`) — stripping agressivo necessário antes de regex matching.
9. **Entre buscas consecutivas na timeline** (ex: "decisão" → "inicial"), é obrigatório limpar o campo e disparar nova busca. Sem limpar, o DOM pode ficar com resultados stale da busca anterior.
10. **Download via `abrirLinkDocumento()` (JS)** abre nova aba com o documento bruto — pode ser HTML, não PDF. **Download correto**: click doc na timeline → preview no painel direito → botão `detalheDocumento:download` → confirm → Chrome salva PDF via CDP.
11. **Tabela de processos usa A4J.AJAX** (RichFaces) — não é navegação de link simples.
12. **mapeamento_tipo_servico.csv** e **lista_servicos.csv** usam delimitador `;`, com multi-valor em células.

### Downloader — regras de negócio para documentos-alvo
1. **DECISÃO**: nome do documento começa com "Decisão" (normalizado: `startswith("decisao")`). Captura "Decisão", "Decisão Interlocutória", etc.
2. **PETIÇÃO**: nome começa com "Petição Inicial" ou "Inicial" (normalizado: `startswith("peticao inicial") or startswith("inicial")`). Exclui "Emendas a Inicial".
3. **SENTENÇA**: comentada no código — projeto opera com DECISÃO + PETIÇÃO apenas. Para reativar: descomentar bloco em `buscar_e_baixar_documentos()`.
4. **Petição intercorrente**: ignorada — não é alvo do gap analysis.

### Downloader — padrões de código críticos
1. **`_buscar_na_timeline()` retorna `bool`** — chamadores devem verificar. Se retorna `False`, não extrair docs (evita dados stale).
2. **Blocos DECISÃO e PETIÇÃO em try/except independentes** — falha num tipo não mata o outro.
3. **`resultado["processos"].append()` no `finally`** — processo nunca é perdido, mesmo com erros parciais.
4. **Metadados e downloads em try/except separados** — falha de metadados não impede download.
5. **Todos os clicks: `.click()` real + fallback JS** `execute_script("arguments[0].click()")`.
6. **`RE_DOC_TIMELINE = re.compile(r"(\d{5,})\s*-\s*(.+)")`** com `.search()` (não `.match()`).
7. **Filtro de classe judicial**: processos com classe vazia são aceitos (problema de timing do DOM em página 2).
8. **`fechar_aba_processo()`**: verifica tabela `fPP:processosTable` pronta antes de retornar ao loop.
9. **Chrome shutdown**: `driver.quit()` + `pkill chromedriver` + `pkill` processos do perfil de automação.

### Downloader — constantes de timing
```python
TIMEOUT_PAGE_LOAD = 60
TIMEOUT_ELEMENT = 15
TIMEOUT_AJAX = 15      # Safety cap para WebDriverWait
PAUSE_BETWEEN_ACTIONS = 1.5  # Conservativo para Seções 1-4
PAUSE_BETWEEN_PROCESSES = 2.0
PAUSE_TIMELINE = 0.8   # Otimizado para Seção 5 (timeline)
```

### Setup do escritório
1. **Cada operador precisa de setup 1x:** abrir Chrome com perfil de automação, instalar whom.doc9, fazer login.
2. **Chrome pessoal do operador nunca é tocado** — perfil de automação é 100% isolado.
3. **Chrome pessoal deve estar FECHADO** durante execução da automação (profile lock do Chrome).

### Extrator - decisões e lições (D1-5)
1. Positional > heading para PETIÇÃO: headings de petição variam por escritório (DO PEDIDO, DOS REQUERIMENTOS, DO PLEITO, DA PRESTAÇÃO JURISDICIONAL REQUERIDA, PEDIDO solto). A zona de pedido sempre fica nos últimos 3000-6000 chars do documento. Uma janela posicional é office-agnostic e mais robusta.
2. Heading funciona bem para DECISÃO: 92%+ das decisões têm heading "DECISÃO" padrão. Os 2 edge cases restantes (assunto sem heading + PDF com encoding quebrado) são capturados por anchor/embedding.
3. Mindset "o que é similar" > "o que é diferente": em vez de mapear toda variação de heading (regex explosion), perguntar "onde a informação sempre está?" — para PETIÇÃO, sempre perto do final.
4. Quality gate com alpha ratio: detecta PDFs com encoding quebrado (caracteres como Â ¬ ¤ ¡) automaticamente via proporção de caracteres alfabéticos.
5. Embedding como safety net, não como estratégia principal: apenas 1 em 79 PDFs usou embedding. Regras simples cobrem 98%+ dos casos.
6. Documento sem tese ≠ falha de extração: extrator entrega texto; classificador (D1-9) identifica que não há tese. Separação de responsabilidades.
7. 6000 chars para PETIÇÃO: cobre pedido (~2500) + subsections (DA PRESTAÇÃO ~1500) + closing/signatures (~1500) + footnotes (~2000). Determinado empiricamente via screenshots de documentos reais.
8. Space-normalized heading matching: PDF rendering insere espaços em headings bold (ex: "DEC ISÃO"). Regex normaliza removendo espaços antes do match.
9. Cover detection por conteúdo: não assume que capa é sempre página 1. Detecta pela presença de "Justiça Federal da 1ª Região" + "PJe - Processo Judicial Eletrônico" nos primeiros 600 chars.
10. Auditoria CSV sobrescreve por CNPJ: evita acúmulo de dados. Cada run do extrator gera snapshot atual.


### Metodologia de desenvolvimento
1. Um passo por vez, confirmação do usuário antes de prosseguir.
2. Nunca inferir estado atual do código — solicitar arquivo compartilhado.
3. Terminal output + observações do browser são o mecanismo primário de feedback.
4. Correções aplicadas imediatamente quando confirmadas por evidência de runtime.
5. Screenshots do usuário são essenciais para diagnóstico de problemas de timing/DOM.
6. Módulos como `extrator.py` podem exigir iteração com screenshots para ajustar patterns de documentos variados.


## 14. Priorização

1. ✅ **ESSENCIAL:** CLI com classificação 3 camadas + gap analysis (Dia 1)
2. ✅ **ESSENCIAL:** Dedup + metadados empresa (Dia 1)
3. ✅ **ESSENCIAL:** Streamlit tema jurídico + Oportunidades + Revisão (Dia 2)
4. ✅ **ESSENCIAL:** Rastreabilidade (disclosure com trecho + método na UI)
5. ⚡ **DESEJÁVEL:** Consolidado multi-CNPJ
6. ⚡ **DESEJÁVEL:** "Adicionar ao mapeamento" direto da UI
7. ⚡ **DESEJÁVEL:** Auditoria.log
8. ⚡ **DESEJÁVEL:** Dashboard com gráficos

---

## 15. Critérios de Sucesso (Final do Dia 2)

| # | Critério |
|---|---------|
| 1 | Pipeline aceita CNPJs via CLI ou Streamlit |
| 2 | whom.doc9 carrega, autentica, navega dashboard→consulta |
| 3 | Metadados empresa coletados (nome, cidade, atividade, etc.) |
| 4 | Downloads deduplicados |
| 5 | Extrator funciona para DECISÃO, PETIÇÃO (SENTENÇA se reativada) |
| 6 | Classificação 3 camadas funciona |
| 7 | **Gap analysis gera lista de oportunidades** |
| 8 | Relatório Excel 4 abas com nomes de domínio |
| 9 | **UI com tema profissional jurídico (laranja, preto, prata)** |
| 10 | **UI usa linguagem 100% de negócio** |
| 11 | **Disclosure progressivo: sem sobrecarga de informação** |
| 12 | **Rastreabilidade: operador pode ver justificativa de classificação** |
| 13 | Revisão recalcula oportunidades automaticamente |
| 14 | Segredos em .env, dados locais, API calls mínimas |
| 15 | README documenta setup completo |

---

*Plano definitivo v5. D1-1 a D1-4 concluídos. Próximo: construir core/extrator.py.*