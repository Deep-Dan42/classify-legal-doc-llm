@echo off
echo ============================================
echo   Classificador de Documentacao Juridica
echo   Iniciando servidor...
echo ============================================
echo.

cd /d "%~dp0"

REM Ativar virtual environment
call .venv\Scripts\activate.bat

REM Mostrar IP local
echo.
echo  Encontrando IP da rede local...
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do (
    set IP=%%a
    goto :found
)
:found
set IP=%IP: =%

echo.
echo  ========================================
echo   SISTEMA ATIVO
echo  ========================================
echo.
echo   Acesse no navegador:
echo.
echo   Neste computador:  http://localhost:8501
echo   Outros na rede:    http://%IP%:8501
echo.
echo  ========================================
echo.
echo   Para encerrar: feche esta janela
echo.

streamlit run ui/app.py --server.address 0.0.0.0 --server.port 8501 --browser.gatherUsageStats false

pause