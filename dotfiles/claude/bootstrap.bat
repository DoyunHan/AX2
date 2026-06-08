@echo off
REM Bootstrap Claude Code user config on a new laptop.
REM ASCII only - Korean Windows cmd is CP949 and rejects UTF-8 Korean .bat.
REM Usage: double-click, or run from cmd in this folder.

setlocal

set "SRC=%~dp0"
set "DST=%USERPROFILE%\.claude"

echo.
echo === Claude Code config bootstrap ===
echo Source: %SRC%
echo Target: %DST%
echo.

if not exist "%DST%" (
  echo Creating %DST%
  mkdir "%DST%"
)

REM Back up existing single files if present.
for %%F in (settings.json statusline.sh) do (
  if exist "%DST%\%%F" (
    echo Backing up existing %%F to %%F.bak
    copy /Y "%DST%\%%F" "%DST%\%%F.bak" >nul
  )
)

REM Back up existing skills folder by renaming to skills.bak.
if exist "%DST%\skills" (
  echo Backing up existing skills folder to skills.bak
  if exist "%DST%\skills.bak" rmdir /S /Q "%DST%\skills.bak"
  move "%DST%\skills" "%DST%\skills.bak" >nul
)

REM Copy the source files into the user's Claude config dir.
copy /Y "%SRC%settings.json" "%DST%\settings.json"
copy /Y "%SRC%statusline.sh" "%DST%\statusline.sh"
xcopy /E /I /Y "%SRC%skills" "%DST%\skills" >nul

echo.
echo Done. Restart Claude Code to pick up the new statusline.
echo If bash cannot find statusline.sh, ensure Git Bash (or WSL bash) is on PATH.
echo.
endlocal
pause
