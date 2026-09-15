@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "PY=.venv\Scripts\python.exe"
if not exist "%PY%" set "PY=python"
"%PY%" -c "from robo_precos.gui.icone import garantir_icone; garantir_icone()" >nul 2>nul

set "PASTA_PRICEBOT=%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$pasta = $env:PASTA_PRICEBOT;" ^
  "$desktop = [Environment]::GetFolderPath('Desktop');" ^
  "$atalho = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop 'PriceBot.lnk'));" ^
  "$atalho.TargetPath = Join-Path $pasta 'Iniciar.bat';" ^
  "$atalho.WorkingDirectory = $pasta;" ^
  "$atalho.WindowStyle = 7;" ^
  "$icone = Join-Path $pasta 'assets\icone.ico'; if (Test-Path -LiteralPath $icone) { $atalho.IconLocation = $icone };" ^
  "$atalho.Description = 'PriceBot - Robo de analise de precos';" ^
  "$atalho.Save()"

if errorlevel 1 (
    echo  [ERRO] Nao foi possivel criar o atalho.
) else (
    echo  Atalho "PriceBot" criado na Area de Trabalho.
)
echo.
pause
