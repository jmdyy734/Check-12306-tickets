@echo off
rem ==== x12306 查票工具启动器 ====
cd /d "%~dp0"

rem ---- 检查 Python 3.9 ----
py -3.9 --version >nul 2>&1
if errorlevel 1 goto nopython

rem ---- 检查依赖，首次运行自动安装 ----
py -3.9 -c "import requests, click, tkinter" >nul 2>&1
if errorlevel 1 py -3.9 -m pip install -r requirements.txt

rem ---- 启动图形界面 ----
start "" pyw -3.9 gui.py
exit /b 0

:nopython
echo [提示] 本机未检测到 Python 3.9！
echo.
echo 方案一（推荐）：直接双击本目录下的 查票工具.exe
echo 单文件免安装，任何电脑都能直接运行，无需 Python 环境。
echo.
echo 方案二：安装 Python 3.9 后再运行本文件，正在打开下载页面...
start https://www.python.org/downloads/release/python-3913/
echo 下载 Windows installer 64位版，安装时务必勾选 Add Python to PATH
echo 装完后重新双击本文件即可。
echo.
pause
exit /b 1
