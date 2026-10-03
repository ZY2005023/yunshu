@echo off
chcp 65001 >nul
echo 正在停止宁渡课堂...

taskkill /FI "WINDOWTITLE eq 宁渡-后端*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq 宁渡-前端*" /T /F >nul 2>&1

for /f "tokens=5" %%p in ('netstat -ano ^| findstr :1236 ^| findstr LISTENING') do taskkill /PID %%p /T /F >nul 2>&1
for /f "tokens=5" %%p in ('netstat -ano ^| findstr :5173 ^| findstr LISTENING') do taskkill /PID %%p /T /F >nul 2>&1

echo 已停止。
pause
