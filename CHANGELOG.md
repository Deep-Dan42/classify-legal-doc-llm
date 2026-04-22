# Changelog

Todas as mudancas relevantes deste projeto serao documentadas aqui.

Formato: [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/)
Versionamento: [Semantic Versioning](https://semver.org/lang/pt-BR/)

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