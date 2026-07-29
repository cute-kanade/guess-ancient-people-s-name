@echo off
chcp 65001 >nul
setlocal
echo [1/4] 验证 M5 Launcher 与数据...
python -m pytest -q tests\test_m5_launcher.py -p no:cacheprovider || exit /b 1
python scripts\validate_v4_data.py || exit /b 1
echo [2/4] 验证构建依赖...
python -c "import streamlit, requests, PyInstaller" || exit /b 1
echo [3/4] 构建单文件 EXE...
python -m PyInstaller --noconfirm --clean build_exe.spec || exit /b 1
echo [4/4] 检查产物...
if not exist dist\GuessHistory.exe exit /b 1
for %%I in (dist\GuessHistory.exe) do if %%~zI LEQ 0 exit /b 1
echo 构建完成：dist\GuessHistory.exe
endlocal
