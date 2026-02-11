@echo off
chcp 65001 >nul
echo ========================================
echo   Shinki_bigpen - 打包脚本
echo ========================================
echo.

REM 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 并添加到 PATH。
    pause
    exit /b 1
)

REM 安装依赖
echo [1/3] 安装依赖...
pip install -r requirements.txt -q
pip install pyinstaller Pillow -q

REM 清理上次打包残留
if exist "dist" rd /s /q dist
if exist "build" rd /s /q build

REM 打包
echo [2/3] 正在打包（可能需要几分钟）...
pyinstaller --onefile ^
    --windowed ^
    --name "神奇大笔" ^
    --add-data "pen_icon.png;." ^
    --icon pen_icon.png ^
    --clean ^
    shinki_bigpen.py

if errorlevel 1 (
    echo [错误] 打包失败
    pause
    exit /b 1
)

REM 复制到发布目录（只复制本次生成的 exe）
echo [3/3] 整理输出...
if not exist "发布" mkdir 发布
if exist "dist\神奇大笔.exe" copy /Y "dist\神奇大笔.exe" "发布\神奇大笔.exe" >nul

echo.
echo [========================================]
echo   打包完成！
echo   可执行文件位置：dist\ 或 发布\
echo [========================================]
echo 可将 发布 文件夹中的 exe 复制给他人使用，无需安装 Python。
echo.
pause
