@echo off
chcp 65001 >nul
title 云舒 - 开发环境

echo ==========================================
echo   云舒 · 启动中
echo   后端  http://localhost:1236   (接口文档 /docs)
echo   前端  http://localhost:5173
echo ==========================================
echo.

rem 托管 node 的版本目录会变（22.22.2-3 已经变成 22.22.2-5），
rem 写死路径会导致前端起不来，这里自动取目录下的 node.exe
set "NODE_EXE="
for /d %%d in ("C:\Users\23540\.workbuddy\binaries\node\versions\*") do set "NODE_EXE=%%d\node.exe"

if not defined NODE_EXE (
    echo [错误] 未找到 node.exe，请检查 C:\Users\23540\.workbuddy\binaries\node\versions\
    pause
    exit /b 1
)
echo 使用 node: %NODE_EXE%
echo.

start "云舒-后端" cmd /c "cd /d %~dp0apps\api && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 1236"

timeout /t 3 /nobreak >nul

start "云舒-前端" cmd /c "cd /d %~dp0apps\web && "%NODE_EXE%" node_modules\vite\bin\vite.js"

echo 已在两个新窗口中启动后端与前端。
echo 关闭请运行 停止云舒.cmd
echo.
pause
