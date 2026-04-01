@echo off
chcp 65001 >nul 2>&1
title 古汉语考据系统

:: ============================================================
::  古汉语考据系统 · 公网访问
::  双击即可：启动本地服务 + 生成公网链接
:: ============================================================

setlocal enabledelayedexpansion

:: ── 清理旧进程 ───────────────────────────────────────────
echo [清理] 检查旧服务...
for %%p in (3001 5000) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p " ^| findstr "LISTENING"') do (
        echo   关闭旧进程 %%a （端口 %%p）...
        taskkill /F /PID %%a >nul 2>&1
    )
)
timeout /t 1 /nobreak >nul

:: ── 启动 Flask 服务 ───────────────────────────────────────
echo.
echo [1/2] 启动 Flask Web 服务（端口 3001）...
start "Flask服务" cmd /k "title 古汉语考据系统 && python -X utf8 app2.py"

:: ── 等待服务就绪 ─────────────────────────────────────────
echo [等待] 服务启动中...
set "READY=0"
for /L %%i in (1,1,20) do (
    timeout /t 1 /nobreak >nul
    curl -s "http://127.0.0.1:3001/api/stats" >nul 2>&1
    if !errorlevel!==0 (
        set "READY=1"
        goto :service_ready
    )
)
:service_ready

if "!READY!"=="0" (
    echo.
    echo [错误] 服务启动超时，请检查上方「Flask服务」终端窗口。
    echo.
    pause
    exit /b 1
)

:: ── 启动 cloudflared 隧道 ─────────────────────────────────
echo [2/2] 启动公网隧道...
echo.
echo 请查看上方新打开的「cloudflared」终端窗口，
echo 等待显示类似以下内容后即可访问：
echo   https://xxxx.trycloudflare.com
echo.
echo 关闭下方窗口或按 Ctrl+C 可停止服务。
echo.
cloudflared.exe tunnel --url http://localhost:3001
