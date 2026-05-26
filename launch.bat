@echo off
chcp 936 > /dev/null
title A股资金博弈分析系统
cd /d "%~dp0"
echo ========================================
echo   A股资金博弈分析系统
echo ========================================
echo.
call venv\Scriptsctivate.bat
echo [1/2] 启动后端服务...
start "" cmd /c "call venv\Scriptsctivate.bat ^&^& python run.py"
timeout /t 2 /nobreak > /dev/null
echo [2/2] 启动前端界面...
start "" cmd /c "call venv\Scriptsctivate.bat ^&^& streamlit run frontend.py"
timeout /t 5 /nobreak > /dev/null
start http://localhost:8501
echo.
echo 系统已启动，请勿关闭本窗口
echo 前端地址: http://localhost:8501
echo 后端地址: http://localhost:8000
echo.
echo 按任意键关闭所有服务...
pause > /dev/null
taskkill /f /im python.exe > /dev/null 2>&1
