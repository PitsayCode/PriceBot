@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"
title PriceBot - Robo de Precos

set "PY_VENV=.venv\Scripts\python.exe"

if exist "%PY_VENV%" goto verificar_dependencias

echo.
echo  ==========================================================
echo    PriceBot - primeira execucao: preparando o ambiente
echo  ==========================================================
echo.
echo  [1/3] Criando o ambiente virtual .venv ...
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 -m venv .venv
) else (
    python -m venv .venv
)
if not exist "%PY_VENV%" goto erro_python

:verificar_dependencias
fc /b requirements.txt .venv\requirements.lock >nul 2>nul
if %errorlevel%==0 goto abrir

echo.
echo  [2/3] Instalando dependencias - acontece so uma vez ...
"%PY_VENV%" -m pip install --upgrade pip --disable-pip-version-check -q
"%PY_VENV%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto erro_instalacao

echo.
echo  [3/3] Baixando o navegador Chromium do Playwright ...
"%PY_VENV%" -m playwright install chromium
if errorlevel 1 goto erro_instalacao

copy /y requirements.txt .venv\requirements.lock >nul
echo.
echo  Tudo pronto! Abrindo o PriceBot...

:abrir
start "" ".venv\Scripts\pythonw.exe" app.py
exit /b 0

:erro_python
echo.
echo  [ERRO] Python nao encontrado.
echo         Instale o Python 3.10 ou superior: https://www.python.org/downloads/
echo         Marque a opcao "Add python.exe to PATH" e rode este arquivo de novo.
echo.
pause
exit /b 1

:erro_instalacao
echo.
echo  [ERRO] Falha ao instalar as dependencias. Verifique a internet e tente de novo.
echo.
pause
exit /b 1
