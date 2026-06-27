@echo off
chcp 65001 >nul
REM =========================================================
REM 猜历史人物 · 单 exe 打包脚本
REM 前置：pip install -r requirements_exe.txt
REM 产物：dist\GuessHistory.exe
REM =========================================================
echo [1/3] 校验依赖...
python -c "import streamlit, requests, PyInstaller" 2>nul || (echo 缺少依赖，请先执行 pip install -r requirements_exe.txt & pause & exit /b 1)

echo [2/3] 清理旧产物...
if exist dist\GuessHistory.exe del /q dist\GuessHistory.exe
if exist build\GuessHistory rmdir /s /q build\GuessHistory

echo [3/3] PyInstaller 打包（首次较慢，约 3-8 分钟）...
python -m PyInstaller --noconfirm --clean build_exe.spec
if errorlevel 1 (
    echo.  & echo 打包失败。
    pause & exit /b 1
)
echo. & echo 完成：dist\GuessHistory.exe