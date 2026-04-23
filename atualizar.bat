@echo off
REM ============================================================
REM  Consulta TRF1 - Atualizador
REM  automacao-juridica-trf1
REM ============================================================
REM  Baixa a versao mais recente do sistema e atualiza as
REM  dependencias Python. Dados do operador sao preservados
REM  (mapeamento_tipo_servico.csv, lista_servicos.csv, .env,
REM  downloads, relatorios, perfil Chrome).
REM
REM  Execucao: duplo-clique neste arquivo.
REM ============================================================

setlocal enabledelayedexpansion
chcp 65001 > nul
title Consulta TRF1 - Atualizador

set "INSTALL_DIR=%USERPROFILE%\Documents\classify-legal-doc-llm"

echo.
echo ============================================================
echo   CONSULTA TRF1 - ATUALIZADOR
echo ============================================================
echo.

REM ============================================================
REM  VALIDACAO
REM ============================================================
if not exist "%INSTALL_DIR%" (
    echo ERRO: Sistema nao instalado em %INSTALL_DIR%
    echo.
    echo Execute instalar.bat primeiro para fazer a instalacao inicial.
    echo.
    pause
    exit /b 1
)

cd /d "%INSTALL_DIR%"

if not exist ".git" (
    echo ERRO: Pasta de instalacao nao e um repositorio Git.
    echo.
    echo Reinstale o sistema usando instalar.bat.
    echo.
    pause
    exit /b 1
)

REM ============================================================
REM  VERIFICAR SE HA PROCESSO DO STREAMLIT RODANDO
REM ============================================================
REM  Se o servidor estiver rodando, aviso o usuario.
REM  Atualizar com servidor ativo funciona mas pode causar confusao.
tasklist /FI "IMAGENAME eq streamlit.exe" 2>nul | find /i "streamlit.exe" > nul
if not errorlevel 1 (
    echo AVISO: O servidor do sistema parece estar rodando.
    echo.
    echo Recomendado: feche a janela "iniciar_servidor" antes de atualizar.
    echo Continuar mesmo assim?
    echo.
    choice /c SN /n /m "  [S] Sim / [N] Nao: "
    if errorlevel 2 exit /b 0
)

REM ============================================================
REM  ETAPA 1 - BAIXAR ATUALIZACAO VIA GIT
REM ============================================================
echo [1/3] Baixando atualizacao...

git fetch origin main
if errorlevel 1 (
    echo.
    echo ERRO: Falha ao conectar ao repositorio.
    echo Verifique sua conexao com a internet.
    echo.
    pause
    exit /b 1
)

REM Verificar se ha atualizacoes pendentes
for /f %%i in ('git rev-list HEAD...origin/main --count') do set "BEHIND=%%i"

if "%BEHIND%"=="0" (
    echo   Sistema ja esta na versao mais recente.
    echo.
    echo Nenhuma atualizacao necessaria.
    pause
    exit /b 0
)

echo   %BEHIND% atualizacoes disponiveis. Aplicando...

git pull origin main
if errorlevel 1 (
    echo.
    echo ERRO: Falha ao aplicar atualizacao.
    echo.
    echo Possiveis causas:
    echo   - Arquivos do sistema foram modificados manualmente
    echo   - Conflito entre versao local e remota
    echo.
    echo Entre em contato com o desenvolvedor.
    echo.
    pause
    exit /b 1
)
echo   Codigo atualizado. OK.

REM ============================================================
REM  ETAPA 2 - ATUALIZAR DEPENDENCIAS PYTHON
REM ============================================================
echo.
echo [2/3] Atualizando dependencias Python...

if not exist ".venv" (
    echo ERRO: Ambiente Python nao encontrado.
    echo Execute instalar.bat para reinstalar.
    echo.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo.
    echo AVISO: Algumas dependencias podem nao ter sido atualizadas.
    echo O sistema deve continuar funcionando.
    echo.
) else (
    echo   Dependencias atualizadas. OK.
)

REM ============================================================
REM  ETAPA 3 - MOSTRAR VERSAO E CHANGELOG
REM ============================================================
echo.
echo [3/3] Verificando versao...

if exist "VERSION" (
    set /p "NEW_VERSION=" < VERSION
    echo   Versao atual: v!NEW_VERSION!
)

echo.
echo ============================================================
echo   ATUALIZACAO CONCLUIDA
echo ============================================================
echo.
echo   O sistema esta pronto para uso.
echo.
echo   Para ver o que mudou, abra CHANGELOG.md em:
echo   %INSTALL_DIR%
echo.
echo   Para iniciar o sistema, use o atalho "Consulta TRF1" no Desktop.
echo.
pause
exit /b 0
