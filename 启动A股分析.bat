@echo off
chcp 65001 > nul
title A股资金博弈分析系统

cd /d "%~dp0"

echo ========================================
echo   A股资金博弈分析系统
echo ========================================
echo.

:: 激活虚拟环境
call venv\Scripts\activate.bat

:: 启动后端 (FastAPI)
echo [1/2] 启动后端服务...
start "A股后端" cmd /c "call venv\Scripts\activate.bat && python run.py"

:: 等2秒让后端先起来
timeout /t 2 /nobreak > nul

:: 启动前端 (Streamlit)
echo [2/2] 启动前端界面...
start "A股前端" cmd /c "call venv\Scripts\activate.bat && streamlit run frontend.py --server.headless true"

timeout /t 5 /nobreak > nul

:: 打开浏览器
echo 正在打开浏览器...
start http://localhost:8501

echo.
echo 系统已启动！
echo 前端地址: http://localhost:8501
echo 后端地址: http://localhost:8000
echo.
echo 关闭本窗口不会影响运行，请在前后端命令行窗口中按 Ctrl+C 停止。
echo.
pause
