@echo off
set NSSM=C:\Users\marti\AppData\Local\Microsoft\WinGet\Packages\NSSM.NSSM_Microsoft.Winget.Source_8wekyb3d8bbwe\nssm-2.24-101-g897c7ad\win64\nssm.exe
set PYTHON=C:\Users\marti\AppData\Local\Python\pythoncore-3.14-64\python.exe
set SCRIPT=C:\Users\marti\OneDrive\Documentos\Otros\Infocus\Axion\_ChatData\api.py
set WORKDIR=C:\Users\marti\OneDrive\Documentos\Otros\Infocus\Axion\_ChatData

%NSSM% install AxionChatAPI %PYTHON% %SCRIPT%
%NSSM% set AxionChatAPI AppDirectory %WORKDIR%
%NSSM% set AxionChatAPI DisplayName "Axion Chat with your Data API"
%NSSM% set AxionChatAPI Description "Backend Flask para Chat with your Data - Axion Energy"
%NSSM% set AxionChatAPI Start SERVICE_AUTO_START
%NSSM% start AxionChatAPI

echo.
echo Servicio instalado e iniciado correctamente.
echo Para administrarlo: services.msc
pause
