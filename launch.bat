@echo off
chcp 936 > nul
title A股资金博弈分析系统

cd /d "%~dp0"

echo ========================================
echo   A股资金博弈分析系统
echo ========================================
echo.

call venv\Scriptsctivate.bat

echo [1/2] 启动后端服务...
start "A股后端" cmd /c "call venv\Scriptsctivate.bat ^&^& python run.py"

timeout /t 2 /nobreak > nul

echo [2/2] 启动前端界面...
start "A股前端" cmd /c "call venv\Scriptsctivate.bat ^&^& streamlit run frontend.py"

timeout /t 5 /nobreak > nul

echo 正在打开寞览器...
start http://localhost:8501

echo.
echo 系统已启动，请勿关闭此窗口
echo 前端地址: http://localhost:8501
echo 后端地址: http://localhost:8000
echo.
echo 按任意键停止所有服务...
pause

echo 正在关闭服务...
taskkill /f /im python.exe > /dev/null 2>&1
echo 已停止
