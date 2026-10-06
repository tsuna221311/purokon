@echo off
setlocal
cd /d "%~dp0"
set "FORMA_URL=http://127.0.0.1:5000"

if exist ".venv\Scripts\python.exe" goto run_venv
where py.exe >nul 2>&1 && goto run_py
where python.exe >nul 2>&1 && goto run_python

echo.
echo [Forma] Python が見つかりません。
echo 展示用PCに Python 3 をインストールし、事前セットアップを完了してください。
echo.
pause
exit /b 1

:open_browser
start "" powershell.exe -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 3; Start-Process '%FORMA_URL%'"
echo [Forma] サーバーを起動しています。
echo [Forma] ブラウザーが開かない場合は %FORMA_URL% を開いてください。
echo [Forma] 終了するには、この画面で Ctrl+C を押してください。
echo.
exit /b 0

:run_venv
call :open_browser
".venv\Scripts\python.exe" app.py
goto finished

:run_py
call :open_browser
py -3 app.py
goto finished

:run_python
call :open_browser
python app.py

:finished
echo.
echo [Forma] サーバーを終了しました。
pause
endlocal
