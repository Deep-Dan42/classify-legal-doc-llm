@echo off
REM ============================================================
REM  Consulta TRF1 - Instalador
REM  automacao-juridica-trf1 v1.0.0
REM ============================================================
REM  Este script instala o sistema do zero no PC. Requer Python 3.13
REM  ja instalado. Git e instalado automaticamente se nao existir.
REM
REM  Execucao: duplo-clique neste arquivo.
REM  Local instalacao: %USERPROFILE%\Documents\classify-legal-doc-llm
REM ============================================================

setlocal enabledelayedexpansion
chcp 65001 > nul
title Consulta TRF1 - Instalador

set "REPO_URL=https://github.com/Deep-Dan42/classify-legal-doc-llm.git"
set "INSTALL_DIR=%USERPROFILE%\Documents\classify-legal-doc-llm"
set "SHORTCUT_NAME=Consulta TRF1"

REM ============================================================
REM  TOKEN DE ACESSO — COLE SUA PAT ENTRE AS ASPAS ABAIXO
REM  Token fine-grained, read-only, expira em 1 ano.
REM  Gere em: https://github.com/settings/personal-access-tokens
REM ============================================================
set "GH_TOKEN=COLE_SEU_TOKEN_AQUI"

REM URL autenticada para clone (monta a partir de REPO_URL + token)
set "REPO_URL_AUTH=https://%GH_TOKEN%@github.com/Deep-Dan42/classify-legal-doc-llm.git"

echo.
echo ============================================================
echo   CONSULTA TRF1 - INSTALADOR
echo ============================================================
echo.
echo   Este instalador vai:
echo     1. Verificar Python 3.13
echo     2. Instalar Git (se necessario)
echo     3. Baixar o sistema de %REPO_URL%
echo     4. Criar ambiente Python e instalar dependencias
echo     5. Configurar chave da OpenAI
echo     6. Criar atalho no Desktop
echo     7. Iniciar o sistema
echo.
echo   Local da instalacao: %INSTALL_DIR%
echo.
pause

REM ============================================================
REM  VALIDACAO DO TOKEN
REM ============================================================
if "%GH_TOKEN%"=="COLE_SEU_TOKEN_AQUI" (
    echo.
    echo ERRO: Token de acesso nao foi configurado neste instalador.
    echo.
    echo O desenvolvedor precisa preencher o GH_TOKEN antes de distribuir
    echo este arquivo. Entre em contato com o desenvolvedor.
    echo.
    pause
    exit /b 1
)

REM ============================================================
REM  DETECCAO DE REINSTALACAO
REM ============================================================
if exist "%INSTALL_DIR%" (
    echo.
    echo ------------------------------------------------------------
    echo   A pasta do sistema ja existe.
    echo ------------------------------------------------------------
    echo.
    echo   [R] Reparar    Reinstala dependencias Python, preserva dados
    echo   [A] Atualizar  Baixa ultima versao e atualiza dependencias
    echo   [C] Cancelar
    echo.
    choice /c RAC /n /m "  Escolha uma opcao (R/A/C): "
    if errorlevel 3 (
        echo.
        echo Instalacao cancelada.
        pause
        exit /b 0
    )
    if errorlevel 2 (
        set "MODE=update"
        echo.
        echo Modo: ATUALIZAR
    ) else (
        set "MODE=repair"
        echo.
        echo Modo: REPARAR
    )
) else (
    set "MODE=fresh"
)

REM ============================================================
REM  ETAPA 1 - VERIFICAR PYTHON
REM ============================================================
echo.
echo [1/7] Verificando Python...

python --version > nul 2>&1
if errorlevel 1 (
    echo.
    echo ERRO: Python nao foi encontrado neste PC.
    echo.
    echo Solucao:
    echo   1. Baixe Python 3.13 em: https://www.python.org/downloads/
    echo   2. Durante a instalacao, MARQUE a opcao "Add Python to PATH"
    echo   3. Rode este instalador novamente apos instalar o Python
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo   Python %PYVER% encontrado. OK.

REM ============================================================
REM  ETAPA 2 - VERIFICAR / INSTALAR GIT
REM ============================================================
echo.
echo [2/7] Verificando Git...

git --version > nul 2>&1
if errorlevel 1 (
    echo   Git nao encontrado. Baixando instalador...

    set "GIT_INSTALLER=%TEMP%\Git-Installer.exe"
    set "GIT_URL=https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe"

    REM Usar curl.exe (nativo no Windows 10+) em vez de PowerShell
    REM para evitar problemas com politicas de execucao e perfis do PowerShell.
    curl.exe -L --silent --show-error --fail --output "!GIT_INSTALLER!" "!GIT_URL!"
    if errorlevel 1 (
        call :GIT_INSTALL_FAILED
        exit /b 1
    )

    echo   Instalando Git silenciosamente (pode levar 1-2 minutos)...
    REM Flags silenciosas completas para o instalador do Git for Windows.
    REM /VERYSILENT suprime todas as janelas; /SUPPRESSMSGBOXES suprime diálogos de erro.
    "!GIT_INSTALLER!" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /NOCANCEL /SP- /COMPONENTS="icons,ext\reg\shellhere,assoc,assoc_sh"
    if errorlevel 1 (
        call :GIT_INSTALL_FAILED
        exit /b 1
    )

    REM Atualizar PATH nesta sessao para ver o Git recem-instalado
    set "PATH=%PATH%;%ProgramFiles%\Git\bin;%ProgramFiles%\Git\cmd"

    REM Segunda verificacao
    git --version > nul 2>&1
    if errorlevel 1 (
        call :GIT_INSTALL_FAILED
        exit /b 1
    )
    echo   Git instalado com sucesso. OK.
) else (
    echo   Git ja instalado. OK.
)

REM ============================================================
REM  ETAPA 3 - CLONAR OU ATUALIZAR REPOSITORIO
REM ============================================================
echo.
echo [3/7] Baixando sistema...

if "%MODE%"=="fresh" (
    REM Clone inicial com token embutido na URL (bypassa Credential Manager).
    REM credential.helper= vazio desabilita qualquer helper global para este clone.
    if not exist "%USERPROFILE%\Documents" mkdir "%USERPROFILE%\Documents"
    cd /d "%USERPROFILE%\Documents"
    git -c credential.helper= clone "%REPO_URL_AUTH%" "classify-legal-doc-llm"
    if errorlevel 1 (
        echo.
        echo ERRO: Falha ao clonar repositorio.
        echo.
        echo Possiveis causas:
        echo   - Sem conexao com a internet
        echo   - Token de acesso invalido ou expirado
        echo   - Token sem permissao de leitura no repositorio
        echo.
        pause
        exit /b 1
    )

    REM Configurar o repositorio clonado para usar o token em pulls futuros.
    cd /d "%INSTALL_DIR%"
    git remote set-url origin "%REPO_URL_AUTH%"

    echo   Repositorio clonado. OK.
) else (
    REM Atualizar (tanto repair quanto update fazem pull)
    cd /d "%INSTALL_DIR%"
    REM Garantir que a URL esta com o token atualizado
    git remote set-url origin "%REPO_URL_AUTH%"
    git pull
    if errorlevel 1 (
        echo.
        echo AVISO: git pull falhou. Continuando com codigo local.
        echo.
    ) else (
        echo   Codigo atualizado. OK.
    )
)

cd /d "%INSTALL_DIR%"

REM ============================================================
REM  ETAPA 4 - AMBIENTE PYTHON
REM ============================================================
echo.
echo [4/7] Configurando ambiente Python...

if not exist ".venv" (
    echo   Criando ambiente virtual...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo ERRO: Falha ao criar ambiente virtual Python.
        echo.
        pause
        exit /b 1
    )
)

echo   Ativando ambiente...
call .venv\Scripts\activate.bat

echo   Instalando dependencias (pode levar varios minutos)...
python -m pip install --upgrade pip --quiet
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ERRO: Falha ao instalar dependencias Python.
    echo Verifique sua conexao com a internet e tente novamente.
    echo.
    pause
    exit /b 1
)
echo   Dependencias instaladas. OK.

REM ============================================================
REM  ETAPA 5 - CONFIGURAR .env
REM ============================================================
echo.
echo [5/7] Configurando chave da OpenAI...

if exist ".env" (
    echo   Arquivo .env ja existe. Mantendo configuracao atual.
) else (
    if not exist ".env.example" (
        echo.
        echo ERRO: .env.example nao encontrado no repositorio.
        echo.
        pause
        exit /b 1
    )

    copy ".env.example" ".env" > nul

    echo.
    echo   Cole a chave da API OpenAI abaixo e pressione Enter.
    echo   A chave comeca com "sk-" e tem cerca de 50 caracteres.
    echo.
    set /p "OPENAI_KEY=  Chave OpenAI: "

    if "!OPENAI_KEY!"=="" (
        echo.
        echo AVISO: Chave nao informada. Voce podera adicionar depois editando .env
    ) else (
        REM Passa a chave via variavel de ambiente para evitar problemas de escape.
        REM -NoProfile evita carregar profile.ps1 (pode estar bloqueado por policy).
        REM -ExecutionPolicy Bypass ignora a politica de execucao de scripts deste PC.
        set "OPENAI_KEY_TEMP=!OPENAI_KEY!"
        powershell -NoProfile -ExecutionPolicy Bypass -Command "$k = $env:OPENAI_KEY_TEMP; (Get-Content '.env') -replace '^OPENAI_API_KEY=.*', ('OPENAI_API_KEY=' + $k) | Set-Content '.env' -Encoding UTF8"
        set "OPENAI_KEY_TEMP="
        echo   Chave salva em .env. OK.
    )
)

REM ============================================================
REM  ETAPA 6 - COPIAR CSVs DEFAULT (primeiro uso apenas)
REM ============================================================
echo.
echo [6/7] Preparando arquivos de dados...

if not exist "data\entrada\mapeamento_tipo_servico.csv" (
    if exist "data\entrada\mapeamento_tipo_servico_default.csv" (
        copy "data\entrada\mapeamento_tipo_servico_default.csv" "data\entrada\mapeamento_tipo_servico.csv" > nul
        echo   mapeamento_tipo_servico.csv criado a partir do default.
    )
)

if not exist "data\entrada\lista_servicos.csv" (
    if exist "data\entrada\lista_servicos_default.csv" (
        copy "data\entrada\lista_servicos_default.csv" "data\entrada\lista_servicos.csv" > nul
        echo   lista_servicos.csv criado a partir do default.
    )
)

if not exist "data\entrada\cnpjs.csv" (
    if exist "data\entrada\cnpjs.csv.example" (
        copy "data\entrada\cnpjs.csv.example" "data\entrada\cnpjs.csv" > nul
        echo   cnpjs.csv criado a partir do template.
    )
)

REM Criar pastas de trabalho se nao existirem
if not exist "data\saida" mkdir "data\saida"
if not exist "data\documentos" mkdir "data\documentos"
if not exist "data\embeddings" mkdir "data\embeddings"
if not exist "data\navegador" mkdir "data\navegador"

echo   Arquivos de dados OK.

REM ============================================================
REM  ETAPA 7 - ATALHOS NO DESKTOP
REM ============================================================
echo.
echo [7/7] Criando atalhos no Desktop...

set "DESKTOP=%USERPROFILE%\Desktop"

REM Atalho principal: Consulta TRF1 (roda iniciar_servidor.bat)
powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP%\%SHORTCUT_NAME%.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\iniciar_servidor.bat'; $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; $Shortcut.IconLocation = '%SystemRoot%\System32\shell32.dll,13'; $Shortcut.Description = 'Iniciar Consulta TRF1'; $Shortcut.Save()"

REM Atalho de atualizacao: Atualizar Consulta TRF1
powershell -NoProfile -ExecutionPolicy Bypass -Command "$WshShell = New-Object -ComObject WScript.Shell; $Shortcut = $WshShell.CreateShortcut('%DESKTOP%\Atualizar Consulta TRF1.lnk'); $Shortcut.TargetPath = '%INSTALL_DIR%\atualizar.bat'; $Shortcut.WorkingDirectory = '%INSTALL_DIR%'; $Shortcut.IconLocation = '%SystemRoot%\System32\shell32.dll,238'; $Shortcut.Description = 'Atualizar Consulta TRF1'; $Shortcut.Save()"

echo   Atalhos criados no Desktop. OK.

REM ============================================================
REM  CONCLUSAO
REM ============================================================
echo.
echo ============================================================
echo   INSTALACAO CONCLUIDA
echo ============================================================
echo.
echo   Sistema instalado em: %INSTALL_DIR%
echo   Atalho no Desktop   : %SHORTCUT_NAME%
echo.
echo   Iniciando o sistema...
echo.
timeout /t 3 /nobreak > nul

REM Lanca o servidor em nova janela
start "" "%INSTALL_DIR%\iniciar_servidor.bat"

REM Aguarda alguns segundos e abre o navegador
timeout /t 8 /nobreak > nul
start "" "http://localhost:8501"

echo.
echo   Feche esta janela quando o navegador abrir.
echo.
pause
exit /b 0

REM ============================================================
REM  SUBROTINA - MENSAGEM DE FALHA NA INSTALACAO DO GIT
REM ============================================================
:GIT_INSTALL_FAILED
echo.
echo ------------------------------------------------------------
echo   ERRO: Nao foi possivel instalar o Git automaticamente.
echo ------------------------------------------------------------
echo.
echo   Isso pode acontecer se o PC tiver restricoes de seguranca
echo   corporativa (antivirus ou politicas de grupo).
echo.
echo   Solucoes (em ordem de preferencia):
echo.
echo     1. Baixe e instale manualmente de:
echo        https://git-scm.com/download/win
echo        (aceite todas as opcoes default)
echo.
echo     2. Depois de instalar o Git, rode este instalador novamente.
echo.
echo     3. Se o erro persistir, entre em contato com o desenvolvedor.
echo.
pause
exit /b 1
