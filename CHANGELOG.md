# Changelog

Todas as mudancas relevantes deste projeto serao documentadas aqui.

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
Versionamento: [Semantic Versioning](https://semver.org/lang/pt-BR/)

---

## [1.1.1] — 2026-04-23

Correcoes pontuais em dois comportamentos encontrados durante smoke test
da v1.1.0 (mesmo dia).

### Corrigido
- **Botao "Usar" na lista de CNPJs baixados (Nova Consulta) nao preenchia
  o campo de CNPJ.** Causa: padrao incorreto de Streamlit — quando um widget
  tem `key=` e `value=` simultaneamente, Streamlit prioriza o cache de
  session_state sobre o `value=`, entao clicar no botao atualizava o estado
  mas o widget continuava exibindo o valor antigo. Correcao: escrever
  diretamente em `st.session_state["cnpj_input"]` ANTES de instanciar o
  widget, que e o padrao canonico do Streamlit para preenchimento
  programatico.

### Adicionado
- **Campo "Parte Relevante" na correcao de classificacao em Resultados.**
  A v1.1.0 criava entradas em Regras Sugeridas sem palavras-chave (e portanto
  nao-aprovaveis). Agora a correcao em Resultados exige colar a parte
  relevante do texto (igual a pagina Revisao), extrai palavras-chave usando
  a mesma funcao `_extrair_keywords`, e gera uma regra sugerida aprovavel.
  O botao "Corrigir" bloqueia envio se o campo de parte relevante estiver
  vazio.

---

## [1.1.0] — 2026-04-23

Primeira rodada de melhorias de UX apos deploy. Todas as mudancas nesta versao
sao na interface (ui/app.py). Nenhum arquivo de codigo do pipeline, configuracao
ou modelos foi alterado.

### Adicionado
- **Lista de CNPJs com documentos baixados na pagina "Nova Consulta"**.
  Abaixo do campo de CNPJ, a pagina agora mostra uma lista dos 8 CNPJs mais
  recentemente baixados, incluindo nome da empresa e quantidade de documentos.
  Um botao "Usar" ao lado de cada entrada preenche o campo automaticamente.
- **Botao de correcao de classificacao na pagina "Resultados"**.
  Dentro de cada expander em "Servicos Identificados", ha agora um bloco
  "Corrigir classificacao" com dropdown da lista mestra de servicos e botao
  "Corrigir". Ao corrigir, a classificacao do item e atualizada imediatamente
  (refletido no relatorio Excel) e uma entrada informativa e enviada para
  "Regras Sugeridas" na pagina Revisao.
- **Propagacao de classificacao no nivel do processo na pagina "Revisao"**.
  Quando um documento e classificado, todos os outros documentos do mesmo
  numero de processo herdam a mesma classificacao e sao automaticamente
  removidos da fila de revisao. Um toast indica quantos documentos foram
  afetados quando mais de um. Aprovacao de regra sugerida continua se
  aplicando apenas ao documento que o operador classificou (apenas uma
  regra e gerada).

### Corrigido
- **Texto "fantasma" na pagina "Revisao"**. Apos confirmar um item e avancar
  para o proximo, o bloco "Texto Extraido" as vezes mostrava o texto do item
  anterior ate outra interacao. Causa: chave de widget Streamlit usava o
  indice posicional da fila, que desloca quando itens sao removidos, fazendo
  o Streamlit reutilizar estado cacheado. Correcao: chave baseada em hash do
  conteudo do item, estavel atraves de pops da fila.

### Removido
- **Expander "Manutencao do sistema" da pagina "Nova Consulta"**. O botao
  "Limpar duplicatas" nao e mais necessario, ja que a deduplicacao acontece
  automaticamente no pipeline. A funcao `_limpar_registro_csv()` foi mantida
  no codigo caso seja util no futuro.

### Notas
- Arquivo `instalar.bat` nao foi modificado nesta versao (usuarios existentes
  que rodarem `atualizar.bat` receberao apenas o novo codigo Python).
- Problema conhecido: ao clicar "Gerar Consulta" na janela aberta automaticamente
  pelo instalador logo apos a instalacao, o pipeline pode nao avancar alem de
  "Extraindo Texto". Workaround: feche a janela e inicie manualmente pelo atalho
  "Consulta TRF1" no Desktop, ou pelo arquivo `iniciar_servidor.bat`. Investigacao
  planejada para uma proxima versao.

---

## [1.0.0] — 2026-04-22

Primeira versao estavel com deploy em producao. Estabelecida estrutura de repositorio
com separacao entre codigo (versionado) e dados do escritorio (locais).

### Adicionado
- Log detalhado do download da automacao. Arquivo `data/saida/download_log_{cnpj}.txt`
  captura toda a execucao do downloader em tempo real, com timestamps e niveis de log.
- Auto-refresh da tela "Download PDFs" enquanto o processo esta em andamento.
  Tela atualiza automaticamente a cada 3 segundos; nao e mais necessario clicar
  para ver o status.
- Botao "Cancelar Download" na tela de download.
- Funcao "Limpar duplicatas" na tela "Nova Consulta" para higiene manual do
  registro de downloads.
- Deteccao automatica de duplicatas no registro ao carregar resultados.
- Aviso explicativo antes do inicio do download sobre o Chrome de automacao.
- Reconstrucao de caminhos de PDFs quando o CSV foi gerado em outro sistema
  operacional (compatibilidade Mac/Windows).

### Corrigido
- Crash do servidor Streamlit durante downloads longos no Windows. Causado pelo
  preenchimento do buffer de pipe do subprocess (64KB no Windows). Correcao:
  redirecionamento de stdout/stderr do subprocess para arquivo de log em vez
  de PIPE.
- UI nao detectava fim do download quando Chrome fechava. Correcao: runner agora
  remove flag file no bloco `finally`; UI inspeciona log de runtime para
  distinguir sucesso vs erro.
- `EXTRACT_CHARS_PETICAO` default era 2000 em vez de 6000, causando extracao
  truncada em peticoes longas.
- Deteccao de versao do Chrome no Windows usando registro do sistema em vez
  de `chrome.exe --version` (que abria janela em vez de imprimir versao).
- Limpeza automatica de lock files do Chrome (SingletonLock, SingletonSocket,
  SingletonCookie) antes de cada execucao.

### Removido
- Camada de classificacao por embeddings (abandonada em favor de regras
  deterministicas + GPT-4o-mini).
- Scripts de desenvolvimento e arquivos de descoberta de DOM.
- `pyproject.toml` quebrado (dependencias stale, scripts inexistentes).
  Fonte unica de verdade de dependencias: `requirements.txt`.

### Infraestrutura
- Estabelecida estrutura `_default.csv` para `mapeamento_tipo_servico` e
  `lista_servicos`. Versoes `_default` sao commitadas no Git; versoes sem
  sufixo sao locais do operador e nao sao afetadas por atualizacoes.
- Arquivo `.gitignore` abrangente cobrindo segredos, ambiente Python,
  dados de cliente, saidas de runtime e metadados de sistema.
- Este arquivo CHANGELOG.md.
- Arquivo VERSION para rastrear versao em execucao na UI.
