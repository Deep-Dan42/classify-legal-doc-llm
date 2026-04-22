# automacao-juridica-trf1

Automacao juridico-tributaria para consulta de processos no TRF1 (PJe),
classificacao de servicos por LLM e analise de oportunidades para escritorios
de advocacia tributaria.

## O que o sistema faz

1. **Consulta automatizada** — busca processos no TRF1 PJe por CNPJ usando
   o certificado digital do escritorio (via extensao whom.doc9).
2. **Download de documentos** — baixa PDFs de decisoes e peticoes iniciais
   relevantes.
3. **Classificacao inteligente** — identifica o tipo de servico juridico
   associado a cada documento usando:
   - **Camada 1**: regras deterministicas por palavra-chave (alta confianca).
   - **Camada 2**: classificacao por LLM (GPT-4o-mini).
   - **Camada 3**: revisao manual pelo operador para casos ambiguos.
4. **Aprendizado continuo** — novas palavras-chave aprovadas pelo operador
   sao incorporadas automaticamente nas regras deterministicas, aumentando
   a precisao com o uso.
5. **Analise de oportunidades** — compara servicos encontrados com a lista
   mestra do escritorio e identifica servicos disponiveis ainda nao prestados
   ao cliente.
6. **Relatorio Excel** — exporta resultado consolidado pronto para uso
   comercial.

## Requisitos

- Windows 10 ou 11 (ambiente de producao oficial)
- Python 3.13 ou superior
- Google Chrome instalado
- Extensao whom.doc9 instalada no Chrome (feita uma vez por PC)
- Certificado digital do escritorio (A1 ou A3)
- Chave de API OpenAI

## Instalacao

**Primeira instalacao no PC do escritorio** (quando o instalador estiver
disponivel):

1. Baixe o projeto do repositorio.
2. Execute `instalar.bat` com duplo-clique.
3. Quando solicitado, cole sua chave da OpenAI.
4. Aguarde a instalacao concluir. O sistema abrira automaticamente no
   navegador em `http://localhost:8501`.

**Execucao do dia a dia**: use o atalho "Classificador Juridico" criado
pelo instalador, ou execute `iniciar_servidor.bat`.

## Atualizacao

Para receber atualizacoes do sistema sem reinstalar:

1. Execute `atualizar.bat` com duplo-clique.
2. O sistema baixa a versao mais recente e reinstala as dependencias.
3. Suas regras aprendidas e configuracoes nao sao afetadas.

## Estrutura do projeto

```
automacao-juridica-trf1/
  core/                    # Logica principal (downloader, extrator, config, modelos)
  classificacao/           # Motor de classificacao (regras + LLM)
  ui/                      # Interface Streamlit
  scripts/                 # Scripts auxiliares (gerar_relatorio)
  data/
    entrada/               # CSVs de entrada (CNPJs, listas de servicos)
    saida/                 # Logs, registros, relatorios gerados
    documentos/            # PDFs baixados (uma pasta por CNPJ)
    navegador/             # Perfil Chrome dedicado a automacao
  .streamlit/              # Tema da UI
  docs/internal/           # Documentacao de desenvolvimento
  requirements.txt         # Dependencias Python
  iniciar_servidor.bat     # Inicia o servidor Streamlit
  VERSION                  # Versao atual
  CHANGELOG.md             # Historico de mudancas
```

## Suporte

Para questoes tecnicas ou sugestoes de melhoria, entre em contato com o
desenvolvedor.

## Licenca

Uso interno do escritorio. Distribuicao nao autorizada.