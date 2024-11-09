@echo off
REM Get the directory of the current script
for %%I in ("%~dp0.") do set "RP=%%~fI"

REM Set PYTHONPATH environment variable
set "PYTHONPATH=%RP%\ashared;%RP%\engine;%RP%\dashboard"

REM To make PYTHONPATH available to subsequent commands in this session
echo PYTHONPATH is set to %PYTHONPATH%
