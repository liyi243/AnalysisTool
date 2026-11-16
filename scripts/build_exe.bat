@echo off
rem ============================================================
rem  376.2 协议解析工具 - Windows 打包脚本
rem  产物：dist\376.2协议解析工具\  （onedir，免安装运行）
rem  说明：本文件为 GBK 编码（兼容 cmd.exe 默认代码页）
rem ============================================================
setlocal
set PY=D:\workspace\devEnvironment\python\python.exe
cd /d "%~dp0.."

echo [1/3] 运行内置自测...
%PY% src\main.py --selftest || (echo 自测失败，终止打包 & exit /b 1)

echo [2/3] PyInstaller 打包（onedir，按 spec）...
%PY% -m PyInstaller --noconfirm --clean 3762tool.spec || (echo 打包失败 & exit /b 1)

echo [3/3] 完成。
echo 产物位置: %cd%\dist\376.2协议解析工具\376.2协议解析工具.exe
echo 验证命令: dist\376.2协议解析工具\376.2协议解析工具.exe --selftest
endlocal
