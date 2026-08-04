@echo off
chcp 65001 >nul
cd /d "%~dp0"
title MetaForge 一键启动
echo.
echo 正在启动 MetaForge ...
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start_metaforge.ps1" %*
if errorlevel 1 (
  echo.
  echo 启动失败，请查看上方报错。
  pause
)
