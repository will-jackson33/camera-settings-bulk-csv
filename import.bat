@echo off
rem Import camera settings with the Camera Configuration Tool: the only script in this folder that
rem changes a camera. Drop the settings file to import onto it, or run it and type the path.
rem
rem Six gates, in order, and it stops at any of them with nothing changed: a fresh export of the
rem same subnets first (the rollback); that export compared with the file, on screen; the site
rem name typed back; a second typed word if the file sets passwords; then one CCT-Batch -i run per
rem subnet, each inside CCT's two-minute budget (ARCHITECTURE.md section 5); then a fresh export compared
rem with the file again - the proof of what actually changed. Everything travels back in one zip.
rem
rem Same rules as the export: flags verified against CCT-Batch 2.16.0.0; free text never inside a
rem parenthesised line and never on a PowerShell command line; no delayed expansion, ever. The
rem PowerShell blocks live after the final exit /b and are read out of this file at runtime.

setlocal
rem One number in three places - here, in "export.bat" and in camerasettings_main.py -
rem and tests/check_bat.py refuses a mismatch. Bumped on every edit, with its CHANGELOG entry.
set "VERSION=1.0.2"
title Camera Configuration Tool - Settings Import %VERSION%
color 07

set "MASTER=--------------------------------------------------------------------------------------------------------------------------"
set "SPACES=                                                            "
set "COLS=120"
rem mode con reads standard input when it is not a console, and a probe run from a script whose
rem input is redirected swallows the answers behind it - measured, with the answers in a file. The
rem <nul keeps the probe's hands off the real input; it still reports the console's own size.
for /f "tokens=1,2" %%W in ('mode con ^<nul') do if /i "%%W"=="Columns:" set "COLS=%%X"
set /a RW=COLS-2
if %RW% GTR 122 set "RW=122"
if %RW% LSS 60 set "RW=60"
call set "RULE= %%MASTER:~0,%RW%%%"
set /a PW=(RW-50)/2
if %PW% GTR 60 set "PW=60"
if %PW% LSS 0 set "PW=0"
call set "PAD=%%SPACES:~0,%PW%%%"
for /f "delims=" %%E in ('cmd /c "echo prompt $E| cmd"') do set "ESC=%%E"
set "TTL="
set "RST="
set "CCT=C:\Program Files (x86)\Motorola Solutions\Camera Configuration Tool\CCT-Batch.exe"
set "PSSELF=%~f0"
set "PSPW=%PW%"
set "PSRW=%RW%"
set "DROPFILE=%TEMP%\camera-import-drop.txt"
set "DROPPATH="

cls
echo.
echo   starting ...

if not exist "%CCT%" goto no_cct

rem A dropped file arrives as %1 and has to survive the elevation relaunch, so it travels twice:
rem as %2 on the relaunch itself, and through a temp file. A Windows path can never contain a
rem quote, so wrapping it in one is always safe, and the path is built inside PowerShell from the
rem environment rather than typed into the command text. The temp file alone was not enough - it
rem is written before elevation and read after, and the two do not always share a %TEMP%.
if "%~1"=="" goto elevation_check
if /i "%~1"=="--elevated" goto relaunched
set "DROPPATH=%~1"
> "%DROPFILE%" echo %~1
goto elevation_check

:relaunched
if not "%~2"=="" set "DROPPATH=%~2"

:elevation_check
net session >nul 2>&1
if not errorlevel 1 goto elevated
if /i "%~1"=="--elevated" goto no_admin
call :paint_banner
echo.
echo   Windows will now ask for administrator permission - answer Yes.
echo   This window closes and the import continues in a new one.
powershell -NoProfile -Command "$q=[char]34;$a='--elevated';if($env:DROPPATH){$a=$a+' '+$q+$env:DROPPATH+$q};try{Start-Process -FilePath $env:PSSELF -ArgumentList $a -Verb RunAs -ErrorAction Stop; exit 0}catch{exit 1}"
if errorlevel 1 goto uac_declined
endlocal
exit /b 0

:elevated
cls
echo.
echo   starting ...
set "CCTANS=%TEMP%\camera-import-answers.txt"
powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'FORM###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'FORM###');Invoke-Expression $t.Substring($i,$j-$i)"
set "FRC=%ERRORLEVEL%"
del "%DROPFILE%" >nul 2>&1
if "%FRC%"=="0" goto form_ok
goto no_input

:form_ok
if not exist "%CCTANS%" goto no_input
for /f "usebackq tokens=1,* delims==" %%A in ("%CCTANS%") do set "%%A=%%B"
del "%CCTANS%" >nul 2>&1
if "%VT%"=="1" set "TTL=%ESC%[93m"
if "%VT%"=="1" set "RST=%ESC%[0m"

set "BASENAME=%SITE%_ACC_Camera_Import_%STAMP%"
set "NAME=%BASENAME%"
set "N=0"
:name_check
if %N% GEQ 50 goto too_many
if not exist "%~dp0%NAME%.zip" goto name_ok
set /a N+=1
set "NAME=%BASENAME%_%N%"
goto name_check

:name_ok
rem Staged in TEMP like the export. The file to import is read in either shape and written into
rem the staging folder as settings.csv in CCT's own shape, so CCT reads a plain path; the file as
rem it was dropped travels in the zip as edited.csv.
set "STAGE=%TEMP%\%NAME%"
set "ZIP=%~dp0%NAME%.zip"
set "LOG=%STAGE%\import.log"
set "RPT=%STAGE%\camera.log"
rmdir /s /q "%STAGE%" 2>nul
mkdir "%STAGE%" 2>nul
mkdir "%STAGE%\rollback-parts" 2>nul
mkdir "%STAGE%\after-parts" 2>nul
mkdir "%LOCALAPPDATA%\Motorola Solutions\Camera Configuration Tool" 2>nul

rem The subnets come from the file itself - the /24 of every camera's address - so there is no
rem sweep; CCT gets one subnet at a time as the export does. Returns "cameras|subnets|passwords|format".
set "PSOUT=%STAGE%"
set "CAMERAS=0"
set "RUNCOUNT=0"
set "PASSWORDS=0"
set "FORMAT=none"
set "MISSING=0"
set "CHANGES=0"
set "CHANGED=0"
set "BAD=0"
set "RUNS=0"
set "AFTERRUNS=0"
set "REMAINING=0"
set "FAILEDRUNS=0"
set "NOTREACHED=0"
for /f "usebackq tokens=1,2,3,4 delims=|" %%A in (`powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'PLAN###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'PLAN###');Invoke-Expression $t.Substring($i,$j-$i)"`) do set "CAMERAS=%%A" & set "RUNCOUNT=%%B" & set "PASSWORDS=%%C" & set "FORMAT=%%D"
if "%CAMERAS%"=="0" goto bad_file

echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%Importing from a file of %CAMERAS% cameras in %RUNCOUNT% subnets%RST%
echo %TTL%%RULE%%RST%
echo.
echo   File             : %IMPORTCSV%
if "%FORMAT%"=="cct" echo   Format           : the file as CCT wrote it
if "%FORMAT%"=="readable" echo   Format           : readable settings.csv, one row per camera
if defined ROLLBACK echo   Rollback         : %ROLLBACK%
if not defined ROLLBACK echo   Rollback         : exported now - every camera in the file is read first, one CCT run per subnet
echo   Nothing changes until the plan has been read and the site name typed back.
if not "%PASSWORDS%"=="0" echo   PASSWORDS        : this file sets %PASSWORDS% camera passwords.

rem Gate 1 - the rollback: the export the file came from, or a fresh export of every subnet the
rem file names, before anything is written. rollback in the zip is the way back either way.
if defined ROLLBACK goto rollback_given
set "PHASE=rollback"
set "PHASETOTAL=%RUNCOUNT%"
set "RUNNO=0"
pushd "%STAGE%"
for /f "usebackq tokens=1,2" %%A in ("runlist-rollback.txt") do call :export_range %%A %%B
popd
:rollback_given

rem Gate 2 - the rollback against the file. A camera in the file that is not in the rollback is a
rem stop: importing around it would leave one camera unproven. A cell the column cannot read is
rem left as it is on the camera and named in the plan; the rest goes ahead. Returns
rem "missing|changes|cameras|skipped|runs|afterruns".
set "PSMODE=rollback"
for /f "usebackq tokens=1,2,3,4,5,6 delims=|" %%A in (`powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'CHECK###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'CHECK###');Invoke-Expression $t.Substring($i,$j-$i)"`) do set "MISSING=%%A" & set "CHANGES=%%B" & set "CHANGED=%%C" & set "BAD=%%D" & set "RUNS=%%E" & set "AFTERRUNS=%%F"
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%What this import will change%RST%
echo %TTL%%RULE%%RST%
type "%STAGE%\plan.txt"
if not "%MISSING%"=="0" goto missing_cameras
if "%CHANGES%"=="0" goto nothing_to_do

rem The change list, offered as a file. It is already in the staging folder and so already in the
rem zip; this only puts a copy beside the script so it can be opened before deciding. Bounded like
rem every prompt here, and Enter takes the safe default of not writing.
set "TRIES=0"
:ask_changes
set /a TRIES+=1
if %TRIES% GEQ 4 goto changes_done
set "TYPED="
set /p "TYPED=  Write this change list to a CSV beside the script? [y/N] : "
if "%TYPED%"=="" goto changes_done
if /i "%TYPED%"=="n" goto changes_done
if /i "%TYPED%"=="y" goto changes_write
echo   Answer y or n.
goto ask_changes

:changes_write
copy /y "%STAGE%\changes.csv" "%~dp0%NAME%-changes.csv" >nul 2>nul
if not exist "%~dp0%NAME%-changes.csv" goto changes_failed
echo   Written: %NAME%-changes.csv
goto changes_done

:changes_failed
echo   WARNING  could not write it - it is in the zip either way.

:changes_done
echo.

rem Gate 3 - the site name, typed back. Three tries; set /p returns at once with no console, and
rem the answer is free text, so the comparison sets a flag rather than jumping: a value holding a
rem quote breaks the if line, and then the flag is still "no" and the script asks again.
set "TRIES=0"
:confirm_site
set /a TRIES+=1
if %TRIES% GEQ 4 goto not_confirmed
set "TYPED="
set "MATCHED=no"
set /p "TYPED=  Type the site name exactly as above to go ahead, or press Enter to stop : "
if "%TYPED%"=="" goto cancelled
if "%TYPED%"=="%SITE%" set "MATCHED=yes"
if "%MATCHED%"=="yes" goto site_ok
echo   That is not the site name.
goto confirm_site

:site_ok
rem Gate 4 - passwords need a second word.
if "%PASSWORDS%"=="0" goto import_now
echo.
echo   This file sets camera passwords. Cameras ACC holds with the old password will drop until
echo   ACC is given the new one.
set "TRIES=0"
:confirm_rotate
set /a TRIES+=1
if %TRIES% GEQ 4 goto not_confirmed
set "TYPED="
set "MATCHED=no"
set /p "TYPED=  Type ROTATE to change passwords, or press Enter to stop : "
if "%TYPED%"=="" goto cancelled
if "%TYPED%"=="ROTATE" set "MATCHED=yes"
if "%MATCHED%"=="yes" goto import_now
goto confirm_rotate

:import_now
rem Gate 5 - the import, one run per group of neighbouring changed cameras. The file CCT reads
rem holds only the cameras that change, and the range never includes one that does not.
set "PHASE=import"
set "PHASETOTAL=%RUNS%"
set "RUNNO=0"
pushd "%STAGE%"
for /f "usebackq tokens=1,2" %%A in ("runlist.txt") do call :import_range %%A %%B
popd

rem Gate 6 - the proof: the same cameras read back and held against what CCT was given.
set "PHASE=after"
set "PHASETOTAL=%AFTERRUNS%"
set "RUNNO=0"
pushd "%STAGE%"
for /f "usebackq tokens=1,2" %%A in ("runlist-after.txt") do call :export_range %%A %%B
popd

set "PSRPT=%RPT%"
set "PSMODE=after"
for /f "usebackq tokens=1,2,3 delims=|" %%A in (`powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'CHECK###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'CHECK###');Invoke-Expression $t.Substring($i,$j-$i)"`) do set "NOTREACHED=%%A" & set "REMAINING=%%B" & set "FAILEDRUNS=%%C"

rem A cell the column could not read was left as it is on the camera and said so in the plan;
rem the verdict carries the count so the zip's reader knows to look.
set "RC=11"
set "VERDICT=PARTIAL - %REMAINING% settings did not take and %FAILEDRUNS% CCT runs failed. camera.log has each one"
if not "%FAILEDRUNS%"=="0" goto verdict_done
if not "%REMAINING%"=="0" goto verdict_done
if not "%NOTREACHED%"=="0" goto verdict_done
set "RC=0"
set "VERDICT=SUCCESS - every change in the file is now on the cameras: %CHANGES% settings on %CHANGED% cameras"
if not "%BAD%"=="0" set "VERDICT=SUCCESS - every readable change is on the cameras: %CHANGES% settings on %CHANGED% cameras"
:verdict_done
goto write_log

:missing_cameras
set "RC=3"
set "VERDICT=STOPPED - %MISSING% cameras in the file did not answer. Nothing was changed"
if defined ROLLBACK set "VERDICT=STOPPED - %MISSING% cameras in the file are not in the rollback file. Nothing was changed"
goto write_log

:nothing_to_do
set "RC=2"
set "VERDICT=NOTHING TO DO - the cameras already hold every setting in the file. Nothing was changed"
if not "%BAD%"=="0" set "VERDICT=NOTHING TO DO - only unreadable cells differ, left as they are. Nothing was changed"
goto write_log

:not_confirmed
set "RC=3"
set "VERDICT=STOPPED - the confirmation was not typed. Nothing was changed"
goto write_log

:cancelled
set "RC=3"
set "VERDICT=STOPPED at the confirmation. Nothing was changed"

:write_log
set "CAMPASS="
rem A stop leaves the per-subnet folders and the scratch files behind; the merged rollback is
rem the one worth keeping. On the full path the report writer has already cleared them.
del /q "%STAGE%\runlist.txt" "%STAGE%\runlist-rollback.txt" "%STAGE%\runlist-after.txt" "%STAGE%\runs-rollback.txt" "%STAGE%\runs-import.txt" "%STAGE%\runs-after.txt" "%STAGE%\plan.txt" "%STAGE%\plan-detail.txt" "%STAGE%\plan-skipped.txt" 2>nul
rmdir /s /q "%STAGE%\rollback-parts" 2>nul
rmdir /s /q "%STAGE%\after-parts" 2>nul

>  "%LOG%" echo Camera settings import
>> "%LOG%" echo -------------------------------------
>> "%LOG%" echo Site        : %SITE%
>> "%LOG%" echo File        : %NAME%.zip
>> "%LOG%" echo Imported    : %IMPORTCSV%
>> "%LOG%" echo Cameras     : %CAMERAS% in the file, in %RUNCOUNT% subnets
>> "%LOG%" echo Username    : %CAMUSER%
>> "%LOG%" echo Ports       : HTTP %HTTPPORT%, HTTPS %HTTPSPORT%
>> "%LOG%" echo Run at      : %RUNSTART%
if defined ROLLBACK >> "%LOG%" echo Rollback    : from the file %ROLLBACK%
if not defined ROLLBACK >> "%LOG%" echo Rollback    : exported now, one CCT run per subnet
>> "%LOG%" echo Compared    : %MISSING% cameras in the file not in the rollback; %CHANGES% settings on %CHANGED% cameras to change; %BAD% cells left as they were
>> "%LOG%" echo Written to  : %CHANGED% cameras in %RUNS% CCT runs, %AFTERRUNS% runs to prove it - no other camera logged into
>> "%LOG%" echo Passwords   : %PASSWORDS% set by the file
>> "%LOG%" echo After       : %REMAINING% settings did not take, %NOTREACHED% cameras not reached, %FAILEDRUNS% CCT runs failed
>> "%LOG%" echo Script exit : %RC%
>> "%LOG%" echo Result      : %VERDICT%

set "PSSRC=%STAGE%\*"
set "PSZIP=%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path $env:PSSRC -DestinationPath $env:PSZIP -Force"
if exist "%ZIP%" rmdir /s /q "%STAGE%" 2>nul

echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%%VERDICT%%RST%
echo %TTL%%RULE%%RST%
echo.
if not "%BAD%"=="0" echo   Left as they were: %BAD% cells the columns could not read - nothing was written for them. camera.log names each
if exist "%ZIP%" echo   Send back        : %ZIP%
if not exist "%ZIP%" echo   ZIP FAILED - send this folder instead : %STAGE%
echo.
echo   Inside the zip: rollback - every camera as it was, the file to restore from;
echo   settings.csv - what CCT was given; edited.csv - the file exactly as it was dropped here;
echo   after.csv - every camera as it is now; changes.csv - the change list, one row per
echo   setting; camera.log; console.log; import.log.
if "%RC%"=="0" goto report_end
echo.
if "%RC%"=="3" goto advice_stopped
if "%RC%"=="2" goto report_end
echo   What to do       : camera.log names each subnet that failed and each setting that did not
echo                      take. Run this again with the same file - it changes only what still
echo                      differs. If it fails the same way twice, send the zip.
goto report_end

:advice_stopped
echo   What to do       : nothing was changed. If cameras did not answer, the list above names
echo                      them - check they are online, then run this again with the same file.

:report_end
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
rem endlocal on the same line: on its own it would discard RC before exit /b read it.
endlocal & exit /b %RC%

:export_range
rem One CCT export of one range - a subnet for the rollback, a group of changed cameras for the
rem proof - into the rollback-parts or the after-parts folder. A range of one address is passed as that
rem address: -a takes an address or a start-end pair, verified against CCT-Batch 2.16.0.0.
set /a RUNNO+=1
set "SUBSTART=%~1"
set "SUBEND=%~2"
set "SUBRANGE=%SUBSTART%-%SUBEND%"
if "%SUBSTART%"=="%SUBEND%" set "SUBRANGE=%SUBSTART%"
set "SUBCSV=%STAGE%\%PHASE%-parts\%SUBSTART%.csv"
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%%PHASE% export  -  run %RUNNO% of %PHASETOTAL%  -  %SUBRANGE%%RST%
echo %TTL%%RULE%%RST%
set "T0=%TIME%"
"%CCT%" -a %SUBRANGE% -u "%CAMUSER%" -p "%CAMPASS%" -t %HTTPPORT% -s %HTTPSPORT% -f -e "%SUBCSV%"
set "SUBRC=%ERRORLEVEL%"
>> "%STAGE%\runs-%PHASE%.txt" echo %SUBRANGE%^|%SUBRC%^|%T0%^|%TIME%
goto :eof

:import_range
rem One CCT import for one group of neighbouring changed cameras. The file holds only the cameras
rem that change; CCT applies it to the ones it finds in the range and lists the rest as not found.
set /a RUNNO+=1
set "SUBSTART=%~1"
set "SUBEND=%~2"
set "SUBRANGE=%SUBSTART%-%SUBEND%"
if "%SUBSTART%"=="%SUBEND%" set "SUBRANGE=%SUBSTART%"
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%IMPORT  -  run %RUNNO% of %PHASETOTAL%  -  %SUBRANGE%%RST%
echo %TTL%%RULE%%RST%
set "T0=%TIME%"
"%CCT%" -a %SUBRANGE% -u "%CAMUSER%" -p "%CAMPASS%" -t %HTTPPORT% -s %HTTPSPORT% -f -i "%STAGE%\settings.csv"
set "SUBRC=%ERRORLEVEL%"
>> "%STAGE%\runs-import.txt" echo %SUBRANGE%^|%SUBRC%^|%T0%^|%TIME%
goto :eof

:paint_banner
if defined BANNERDONE goto :eof
set "BANNERDONE=1"
set "VTPRE=0"
for /f "usebackq delims=" %%V in (`powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'VT###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'VT###');Invoke-Expression $t.Substring($i,$j-$i)"`) do set "VTPRE=%%V"
if "%VTPRE%"=="1" set "TTL=%ESC%[93m"
if "%VTPRE%"=="1" set "RST=%ESC%[0m"
goto :eof

:no_cct
call :paint_banner
cls
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%COULD NOT START - Camera Configuration Tool not found%RST%
echo %TTL%%RULE%%RST%
echo.
echo   What happened   This machine does not have the Camera Configuration Tool installed
echo                   at the expected location:
echo                   %CCT%
echo.
echo   Changed         Nothing. No camera was touched.
echo.
echo   What to do      Install the Camera Configuration Tool (version 2.16 or newer), then run
echo                   "import.bat" again.
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 1

:uac_declined
call :paint_banner
cls
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%COULD NOT START - permission was declined%RST%
echo %TTL%%RULE%%RST%
echo.
echo   What happened   Windows asked for administrator permission and the answer was No,
echo                   or the prompt was closed.
echo.
echo   Changed         Nothing. No camera was touched.
echo.
echo   What to do      Run "import.bat" again and answer Yes.
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 10

:no_admin
call :paint_banner
cls
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%COULD NOT START - administrator rights did not take effect%RST%
echo %TTL%%RULE%%RST%
echo.
echo   What happened   Permission was granted, but Windows still refused administrator
echo                   rights. That is usually a company policy on this machine.
echo.
echo   Changed         Nothing. No camera was touched.
echo.
echo   What to do      Right-click "import.bat" yourself and choose "Run as
echo                   administrator". If that fails too, run it from a different machine
echo                   on the camera network.
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 10

:no_input
cls
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%STOPPED - the questions went unanswered%RST%
echo %TTL%%RULE%%RST%
echo.
echo   What happened   A question went unanswered, or was answered five times in a way
echo                   that could not be understood.
echo.
echo   Changed         Nothing. No camera was touched.
echo.
echo   What to do      Run "import.bat" again, type each answer and press Enter.
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 1

:bad_file
rmdir /s /q "%STAGE%" 2>nul
cls
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%STOPPED - that is not a settings file this script can import%RST%
echo %TTL%%RULE%%RST%
echo.
echo   What happened   The file has no cameras in it, or is not a settings file. It must be
echo                   the settings.csv from an export - edited in Excel, saved as CSV - or
echo                   the backup file from the export zip:
echo                   %IMPORTCSV%
echo.
echo   Changed         Nothing. No camera was touched.
echo.
echo   What to do      Check the file opens in Excel with MacAddress and Name in its first row,
echo                   then run "import.bat" again with it.
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 1

:too_many
cls
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%STOPPED - too many imports here for one day%RST%
echo %TTL%%RULE%%RST%
echo.
echo   What happened   There are already 50 import zips for this site, today, in this folder.
echo.
echo   Changed         Nothing. No camera was touched.
echo.
echo   What to do      Move or delete the older zips in this folder, then run it again.
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 1

goto :eof

Everything below this line is PowerShell, read out of this file at runtime. CMD never executes it.

###PSVT###
$vtOn = '0'
try {
    Add-Type -Namespace W2 -Name K -MemberDefinition '[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int h); [DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m); [DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);'
    $h = [W2.K]::GetStdHandle(-11); $m = [uint32]0
    if ([W2.K]::GetConsoleMode($h, [ref]$m) -and [W2.K]::SetConsoleMode($h, $m -bor 4)) { $vtOn = '1' }
} catch {}
try {
    $ry = ' ' + ('-' * [int]$env:PSRW)
    $bpad = ' ' * ([int]$env:PSPW + 2)
    [Console]::SetCursorPosition(0, 1); Write-Host $ry -ForegroundColor Yellow -NoNewline
    [Console]::SetCursorPosition(0, 2); Write-Host ($bpad + 'Camera Configuration Tool - Settings Import') -ForegroundColor Yellow -NoNewline
    [Console]::SetCursorPosition(0, 3); Write-Host ($bpad + 'v' + $env:VERSION + ' - writes settings to cameras. Read it.') -ForegroundColor Yellow -NoNewline
    [Console]::SetCursorPosition(0, 4); Write-Host $ry -ForegroundColor Yellow -NoNewline
    [Console]::SetCursorPosition(0, 6)
} catch {}
$vtOn
###ENDVT###

###PSFORM###
$ErrorActionPreference = 'Stop'
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'COLS###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'COLS###');Invoke-Expression $t.Substring($i,$j-$i)
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'CSV###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'CSV###');Invoke-Expression $t.Substring($i,$j-$i)
# The dropped path, from the relaunch argument first and the temp file second.
$dropped = '' + $env:DROPPATH
if ($dropped.Trim() -eq '') {
    try { if (Test-Path -LiteralPath $env:DROPFILE) { $dropped = ([IO.File]::ReadAllLines($env:DROPFILE) | Where-Object { $_ -ne '' } | Select-Object -First 1) } } catch {}
}
if ($null -eq $dropped) { $dropped = '' }
function Test-SettingsFile([string]$path) { try { return ($null -ne (Read-Any $path)) } catch { return $false } }

# The rollback is the export the file came from: the backup file from the export zip, or any
# settings file that has not been edited. Blank means export one now. When a backup file sits
# beside the dropped file the newest is offered, because that is the export this file came from.
$labels = @('Site name','Settings file to import','Rollback (blank = export)','Camera username','Camera password','HTTP port','HTTPS port')
$vals   = @('', [string]$dropped, '', '', '', '80', '443')
$plain = $true
$vt = $false
try { $plain = ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) } catch {}

$firstRow = 6
$fw = 80
if (-not $plain) {
    try { $r = $Host.UI.RawUI; $b = $r.BufferSize; if ($b.Height -lt 9000) { $b.Height = 9000; $r.BufferSize = $b } } catch {}
    $fw = [Math]::Max(40, [Console]::WindowWidth - 32)
    try { [Console]::CursorVisible = $false } catch {}
    try {
        Add-Type -Namespace W -Name K -MemberDefinition '[DllImport("kernel32.dll")] public static extern IntPtr GetStdHandle(int h); [DllImport("kernel32.dll")] public static extern bool GetConsoleMode(IntPtr h, out uint m); [DllImport("kernel32.dll")] public static extern bool SetConsoleMode(IntPtr h, uint m);'
        $h = [W.K]::GetStdHandle(-11); $m = [uint32]0
        if ([W.K]::GetConsoleMode($h, [ref]$m)) { $script:vt = [W.K]::SetConsoleMode($h, $m -bor 4) }
    } catch { $script:vt = $false }
    try {
        $ry = ' ' + ('-' * [int]$env:PSRW)
        $bpad = ' ' * ([int]$env:PSPW + 2)
        [Console]::SetCursorPosition(0, [Math]::Max(0, $firstRow - 5)); Write-Host $ry -ForegroundColor Yellow -NoNewline
        [Console]::SetCursorPosition(0, [Math]::Max(0, $firstRow - 4)); Write-Host ($bpad + 'Camera Configuration Tool - Settings Import') -ForegroundColor Yellow -NoNewline
        [Console]::SetCursorPosition(0, [Math]::Max(0, $firstRow - 3)); Write-Host ($bpad + 'v' + $env:VERSION + ' - writes settings to cameras. Read it.') -ForegroundColor Yellow -NoNewline
        [Console]::SetCursorPosition(0, [Math]::Max(0, $firstRow - 2)); Write-Host $ry -ForegroundColor Yellow -NoNewline
    } catch {}
    for ($i = 0; $i -lt $labels.Count; $i++) {
        [Console]::SetCursorPosition(0, $firstRow + $i)
        [Console]::Write('  ' + $labels[$i].PadRight(26) + ': ' + $vals[$i].PadRight($fw))
    }
}

# Unlike the export, this script keeps asking after the form closes - the site name, and ROTATE.
# [Console]::ReadLine() on a redirected stdin fills a 4 KB buffer and swallows everything piped
# behind the answer, so the confirmations would never see their input; OpenStandardInput() with no
# argument buffers 4 KB and does the same. The 1 asks for an unbuffered stream, which takes exactly
# the line it was given and leaves the rest for CMD. Measured, both ways.
$script:stdin = $null
function Read-RawLine() {
    if ($null -eq $script:stdin) { $script:stdin = [Console]::OpenStandardInput(1) }
    $sb = New-Object System.Text.StringBuilder
    while ($true) {
        $b = $script:stdin.ReadByte()
        if ($b -lt 0) { if ($sb.Length -eq 0) { return $null }; break }
        if ($b -eq 10) { break }
        if ($b -ne 13) { [void]$sb.Append([char]$b) }
    }
    return $sb.ToString()
}

function Show-Status([string]$msg) {
    if ($script:plain) { if ($msg) { [Console]::Error.WriteLine($msg) }; return }
    [Console]::SetCursorPosition(0, $script:firstRow + $script:labels.Count + 1)
    [Console]::Write($msg.PadRight([Math]::Max(60, [Console]::WindowWidth - 2)))
}
function Set-Field([int]$i, [string]$v) {
    $script:vals[$i] = $v
    if ($script:plain) { return }
    [Console]::SetCursorPosition(30, $script:firstRow + $i)
    [Console]::Write($v.PadRight($script:fw))
}
function Read-Field([int]$i) {
    if ($script:plain) { [Console]::Error.Write($script:labels[$i].PadRight(26) + ': '); return Read-RawLine }
    $buf = [string]$script:vals[$i]
    [Console]::SetCursorPosition(30, $script:firstRow + $i)
    [Console]::Write($buf.PadRight($script:fw))
    [Console]::SetCursorPosition(30 + $buf.Length, $script:firstRow + $i)
    try { [Console]::CursorVisible = $true } catch {}
    while ($true) {
        $k = [Console]::ReadKey($true)
        if ($k.Key -eq 'Enter') { return $buf }
        if ($k.Key -eq 'Backspace') {
            if ($buf.Length -gt 0) { $buf = $buf.Substring(0, $buf.Length - 1); [Console]::Write("`b `b") }
            continue
        }
        if (-not [char]::IsControl($k.KeyChar) -and $buf.Length -lt ($script:fw - 2)) { $buf += $k.KeyChar; [Console]::Write($k.KeyChar) }
    }
}

$i = 0
$strikes = 0
while ($i -lt $labels.Count) {
    $in = Read-Field $i
    if (-not $plain) { try { [Console]::CursorVisible = $false } catch {} }
    if ($null -eq $in) { try { [Console]::CursorVisible = $true } catch {}; exit 2 }
    $in = $in.Trim()
    if ($in -eq '') { $in = $vals[$i] }
    $err = ''
    switch ($i) {
        0 { $in = $in -replace '[\\/:|?<>&*"]', '-'
            if ($in -eq '') { $err = 'The site name is needed - it names the zip you send back, and you type it again before the import.' } }
        1 { $in = $in.Trim('"')
            if ($in -eq '' -or -not (Test-Path -LiteralPath $in -PathType Leaf)) { $err = 'That file does not exist. Drop the settings.csv onto this script, or type its full path.' }
            elseif ($in -match '[()&|<>^%!]') { $err = 'Copy the file to a folder whose path has no brackets and no & | < > ^ % ! in it, then try again.' }
            elseif (-not (Test-SettingsFile $in)) { $err = 'That is not a settings file. It needs MacAddress and Name in its first row, as the export wrote it.' }
            else { try { $c = @(Get-ChildItem -LiteralPath (Split-Path -Parent $in) -Filter 'backup*' -File | Sort-Object LastWriteTime -Descending); if ($vals[2] -eq '' -and $c.Count -gt 0) { Set-Field 2 $c[0].FullName } } catch {} } }
        2 { $in = $in.Trim('"')
            if ($in -eq '') { }
            elseif (-not (Test-Path -LiteralPath $in -PathType Leaf)) { $err = 'That rollback file does not exist. Type its full path, or leave it blank to export one now.' }
            elseif ($in -match '[()&|<>^%!]') { $err = 'Copy the rollback file to a folder whose path has no brackets and no & | < > ^ % ! in it, then try again.' }
            elseif (-not (Test-SettingsFile $in)) { $err = 'That is not a settings file. The rollback is the backup file from the export zip, or a settings.csv nobody has edited.' } }
        3 { if ($in -eq '') { $err = 'The camera username is needed.' } }
        4 { }
        default { if ($in -notmatch '^\d{1,5}$' -or [int]$in -lt 1 -or [int]$in -gt 65535) { $err = 'Ports are a number between 1 and 65535. Press Enter to accept the one shown.' } }
    }
    if ($err -ne '') {
        $strikes++
        if ($strikes -ge 5) { try { [Console]::CursorVisible = $true } catch {}; exit 3 }
        Show-Status ('  ' + $err)
        Set-Field $i $vals[$i]
        continue
    }
    Show-Status ''
    Set-Field $i $in
    $i++
}
if (-not $plain) { [Console]::SetCursorPosition(0, $firstRow + $labels.Count + 1); try { [Console]::CursorVisible = $true } catch {} }

$lines = @(
    ('SITE=' + $vals[0]), ('IMPORTCSV=' + $vals[1]), ('ROLLBACK=' + $vals[2]),
    ('CAMUSER=' + $vals[3]), ('CAMPASS=' + $vals[4]),
    ('HTTPPORT=' + $vals[5]), ('HTTPSPORT=' + $vals[6]),
    ('STAMP=' + (Get-Date -Format 'dd_MM_yy')), ('RUNSTART=' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
    ('VT=' + $(if ($vt) { '1' } else { '0' }))
)
Set-Content -Path $env:CCTANS -Value $lines -Encoding Default
exit 0
###ENDFORM###

###PSCSV###
# Shared by PLAN, CHECK and the export's READABLE block: a settings file in either shape read into
# one structure - DeviceColumns and AnalyticsColumns as CCT names them, cameras keyed by MAC in
# file order, every row native-shaped (the marker first, CCT's quotes on) - and written back as
# CCT's own file. Read-Any tells the two shapes apart from the bytes, never from the name.
# Anything that is not a settings file returns $null, which the callers treat as "not a settings
# file" rather than as an empty one. The COLS block must be loaded first.
function Read-Settings([string]$path) {
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $bytes = [IO.File]::ReadAllBytes($path)
    if ($bytes.Length -lt 2 -or $bytes[0] -ne 0xFF -or $bytes[1] -ne 0xFE) { return $null }
    $text = [Text.Encoding]::Unicode.GetString($bytes, 2, $bytes.Length - 2)
    $file = @{ DeviceColumns = @(); AnalyticsColumns = @(); Cameras = @{}; Order = @(); Format = 'cct' }
    $current = $null
    foreach ($line in ($text -split "`r?`n")) {
        if ($line -eq '') { continue }
        $f = $line -split "`t"
        if ($f[0] -eq 'DeviceHeader') { $file.DeviceColumns = $f; continue }
        if ($f[0] -eq 'AnalyticsHeader') { $file.AnalyticsColumns = $f; continue }
        if ($f[0] -eq 'Device') {
            if ($file.DeviceColumns.Count -eq 0) { return $null }
            $mac = $f[[array]::IndexOf($file.DeviceColumns, 'MacAddress')].ToUpper()
            $current = @{ Device = $f; Analytics = @() }
            $file.Cameras[$mac] = $current
            $file.Order += $mac
            continue
        }
        if ($f[0] -eq 'Analytics' -and $null -ne $current) { $current.Analytics += ,$f; continue }
        return $null
    }
    if ($file.DeviceColumns.Count -eq 0 -or $file.Order.Count -eq 0) { return $null }
    return $file
}
function Read-Csv([string]$path) {
    # A comma, tab or semicolon file with the quoting Excel writes and reads. The encoding comes
    # from the byte-order mark when there is one; without one UTF-8 is tried before the ANSI code
    # page, because Excel's plain "CSV" is ANSI and its "CSV UTF-8" carries the mark. Rows come
    # back as a list of string arrays, the header first.
    $bytes = [IO.File]::ReadAllBytes($path)
    $enc = New-Object System.Text.UTF8Encoding($false, $true)
    try { [void]$enc.GetString($bytes) } catch { $enc = [Text.Encoding]::Default }
    $sr = New-Object IO.StreamReader($path, $enc, $true)
    $first = $sr.ReadLine()
    $sr.Close()
    if ($null -eq $first) { return $null }
    $delim = ','
    $best = @($first.ToCharArray() | Where-Object { $_ -eq ',' }).Count
    foreach ($d in @("`t", ';')) {
        $n = @($first.ToCharArray() | Where-Object { $_ -eq $d }).Count
        if ($n -gt $best) { $best = $n; $delim = $d }
    }
    Add-Type -AssemblyName Microsoft.VisualBasic
    $reader = New-Object Microsoft.VisualBasic.FileIO.TextFieldParser($path, $enc, $true)
    $reader.TextFieldType = 'Delimited'
    $reader.SetDelimiters($delim)
    $reader.HasFieldsEnclosedInQuotes = $true
    $reader.TrimWhiteSpace = $false
    $rows = New-Object System.Collections.Generic.List[object]
    try { while (-not $reader.EndOfData) { $rows.Add($reader.ReadFields()) } }
    catch { $reader.Close(); return $null }
    $reader.Close()
    return ,$rows
}
function Quote([string]$column, [string]$value) {
    # The value as CCT writes that column, unless it already carries the quotes.
    if (-not $colQuote.ContainsKey($column)) { return $value }
    $q = $colQuote[$column]
    if ($value.Length -ge 2 -and $value[0] -eq $q -and $value[-1] -eq $q) { return $value }
    return $q + $value + $q
}
function Code([string]$column, [string]$value) {
    # The code behind a word the readable file shows - Outdoor is 0 - or the value as it stands.
    if (-not $colWords.ContainsKey($column)) { return $value }
    foreach ($pair in $colWords[$column].GetEnumerator()) { if ($pair.Value -eq $value.Trim()) { return $pair.Key } }
    return $value
}
function Pad-Row($cells, [int]$width) {
    $row = @($cells)
    while ($row.Count -lt $width) { $row += '' }
    return ,$row
}
function Read-Readable([string]$path) {
    $rows = Read-Csv $path
    if ($null -eq $rows -or $rows.Count -lt 2) { return $null }
    $header = @($rows[0] | ForEach-Object { ([string]$_).Trim() })
    if ($header -notcontains 'MacAddress' -or $header -notcontains 'Name') { return $null }
    $file = @{ DeviceColumns = @('DeviceHeader') + $header; AnalyticsColumns = @('AnalyticsHeader', 'Head', ''); Cameras = @{}; Order = @(); Format = 'readable' }
    $macAt = [array]::IndexOf($header, 'MacAddress')
    for ($r = 1; $r -lt $rows.Count; $r++) {
        $cells = Pad-Row $rows[$r] $header.Count
        $mac = $cells[$macAt].Trim().ToUpper()
        if ($mac -eq '') { continue }
        $device = @('Device')
        for ($c = 0; $c -lt $header.Count; $c++) { $device += (Quote $header[$c] $cells[$c]) }
        $file.Cameras[$mac] = @{ Device = $device; Analytics = @() }
        $file.Order += $mac
    }
    if ($file.Order.Count -eq 0) { return $null }
    # analytics.csv beside it, when it came back: one row per head, found again by MAC and Head.
    # Its Name and IpAddress columns are for reading and are dropped here.
    $apath = Join-Path (Split-Path -Parent $path) 'analytics.csv'
    if (-not (Test-Path -LiteralPath $apath)) { return $file }
    $arows = Read-Csv $apath
    if ($null -eq $arows -or $arows.Count -lt 1) { return $file }
    $aheader = @($arows[0] | ForEach-Object { ([string]$_).Trim() })
    $amacAt = [array]::IndexOf($aheader, 'MacAddress')
    $aheadAt = [array]::IndexOf($aheader, 'Head')
    if ($amacAt -lt 0 -or $aheadAt -lt 0) { return $file }
    $valueAt = @()
    for ($c = 0; $c -lt $aheader.Count; $c++) { if (@('MacAddress', 'Name', 'IpAddress', 'Head') -notcontains $aheader[$c]) { $valueAt += $c } }
    $file.AnalyticsColumns = @('AnalyticsHeader', 'Head') + @($valueAt | ForEach-Object { $aheader[$_] }) + @('')
    $byMac = @{}
    for ($r = 1; $r -lt $arows.Count; $r++) {
        $cells = Pad-Row $arows[$r] $aheader.Count
        $mac = $cells[$amacAt].Trim().ToUpper()
        if ($mac -eq '') { continue }
        $row = @('Analytics', $cells[$aheadAt].Trim())
        foreach ($c in $valueAt) { $row += (Code $aheader[$c] $cells[$c]) }
        $row += ''
        if (-not $byMac.ContainsKey($mac)) { $byMac[$mac] = @() }
        $byMac[$mac] += ,$row
    }
    foreach ($mac in $file.Order) {
        if ($byMac.ContainsKey($mac)) { $file.Cameras[$mac].Analytics = @($byMac[$mac] | Sort-Object { [int]$_[1] }) }
    }
    return $file
}
function Read-Any([string]$path) {
    # CCT's own file starts with the UTF-16 mark and the word DeviceHeader. Everything else is
    # read as the readable shape.
    if (-not (Test-Path -LiteralPath $path)) { return $null }
    $bytes = [IO.File]::ReadAllBytes($path)
    if ($bytes.Length -ge 28 -and $bytes[0] -eq 0xFF -and $bytes[1] -eq 0xFE) {
        if ([Text.Encoding]::Unicode.GetString($bytes, 2, 24) -eq 'DeviceHeader') { return (Read-Settings $path) }
    }
    return (Read-Readable $path)
}
function Write-Native($file, [string]$path) {
    # As CCT writes it: the two header lines, then each camera's rows, UTF-16 with the mark, CRLF.
    $lines = New-Object System.Collections.Generic.List[string]
    $lines.Add(($file.DeviceColumns -join "`t"))
    $lines.Add(($file.AnalyticsColumns -join "`t"))
    foreach ($mac in $file.Order) {
        $camera = $file.Cameras[$mac]
        $lines.Add(($camera.Device -join "`t"))
        foreach ($row in $camera.Analytics) { $lines.Add(($row -join "`t")) }
    }
    [IO.File]::WriteAllLines($path, $lines, [Text.Encoding]::Unicode)
}
function Bare([string]$v) { if ($v.Length -ge 2 -and $v[0] -eq $v[-1] -and @('"', "'") -contains $v[0]) { return $v.Substring(1, $v.Length - 2) }; return $v }
function Field($file, $camera, [string]$column) { $i = [array]::IndexOf($file.DeviceColumns, $column); if ($i -lt 0) { return '' }; return (Bare $camera.Device[$i]) }
function Who($file, $camera) {
    $name = Field $file $camera 'Name'
    $short = $name
    if ($short.ToLower().StartsWith('acc/')) { $short = $short.Substring(4) }
    $numbers = [regex]::Matches(($short -split ' - ', 2)[0], '\b[Cc]\d+\b') | ForEach-Object { $_.Value.ToUpper() }
    if ($numbers) { return ($numbers -join ', ') }
    return $name
}
function Label($file, $camera) {
    return (Who $file $camera) + ' (' + (Field $file $camera 'IpAddress') + ')'
}
function Normalize([string]$column, [string]$value) {
    # A value as a person typed it, in the form the column holds - True not TRUE, 1920 x 1080 not
    # 1920x1080, H264 not h264, a code for a word - or the reason it cannot be. The same rules as
    # camerasettings_columns.py; blank is always allowed, because blank means leave it alone.
    $v = $value.Trim()
    $kind = $colKind[$column]
    if ($v -eq '') { return @{ Ok = $true; Value = '' } }
    if ($null -eq $kind) {
        if ($v -match "`t|`r|`n") { return @{ Ok = $false; Reason = $column + ' cannot contain a tab or a line break' } }
        if ($colQuote.ContainsKey($column) -and $v.Contains($colQuote[$column])) { return @{ Ok = $false; Reason = $column + ' cannot contain the ' + $colQuote[$column] + ' character - CCT uses it to wrap the value' } }
        return @{ Ok = $true; Value = $v }
    }
    $parts = $kind -split '\|'
    switch ($parts[0]) {
        'bool' {
            if ($v -match '^(?i)true$') { return @{ Ok = $true; Value = 'True' } }
            if ($v -match '^(?i)false$') { return @{ Ok = $true; Value = 'False' } }
            return @{ Ok = $false; Reason = $column + " takes True or False, not '" + $v + "'" }
        }
        'int' {
            if ($v -notmatch '^-?\d+$') { return @{ Ok = $false; Reason = $column + " takes a whole number, not '" + $v + "'" } }
            $n = [long]$v
            if ($parts[1] -ne '' -and $n -lt [long]$parts[1]) { return @{ Ok = $false; Reason = $column + ' must be at least ' + $parts[1] + ', not ' + $n } }
            if ($parts[2] -ne '' -and $n -gt [long]$parts[2]) { return @{ Ok = $false; Reason = $column + ' must be at most ' + $parts[2] + ', not ' + $n } }
            return @{ Ok = $true; Value = ('' + $n) }
        }
        'float' {
            $d = 0.0
            if ([double]::TryParse($v, [Globalization.NumberStyles]::Float, [Globalization.CultureInfo]::InvariantCulture, [ref]$d)) { return @{ Ok = $true; Value = $v } }
            return @{ Ok = $false; Reason = $column + " takes a number, not '" + $v + "'" }
        }
        'ip' {
            if ($v -match '^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$') {
                $octets = @([int]$matches[1], [int]$matches[2], [int]$matches[3], [int]$matches[4])
                if (@($octets | Where-Object { $_ -gt 255 }).Count -eq 0) { return @{ Ok = $true; Value = ($octets -join '.') } }
            }
            return @{ Ok = $false; Reason = $column + " takes an address like 10.20.3.128, not '" + $v + "'" }
        }
        'resolution' {
            if ($v -match '^\s*(\d+)\s*[xX]\s*(\d+)\s*$') { return @{ Ok = $true; Value = ('' + [int]$matches[1] + ' x ' + [int]$matches[2]) } }
            return @{ Ok = $false; Reason = $column + " takes width x height like 1920 x 1080, not '" + $v + "'" }
        }
        'choice' {
            $code = Code $column $v
            for ($k = 1; $k -lt $parts.Count; $k++) { if ($parts[$k] -eq $code) { return @{ Ok = $true; Value = $parts[$k] } } }
            $shown = @()
            for ($k = 1; $k -lt $parts.Count; $k++) { $shown += $parts[$k] }
            if ($colWords.ContainsKey($column)) { $shown = @($colWords[$column].GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Value + ' (' + $_.Name + ')' }) }
            return @{ Ok = $false; Reason = $column + ' takes one of ' + ($shown -join ', ') + ", not '" + $v + "'" }
        }
    }
    return @{ Ok = $true; Value = $v }
}
# Columns import ignores or refuses, so a difference in them is noise rather than a change. The two
# password columns are applied but never come back from a camera, so an export can never prove them.
$ignored = @('DeviceHeader', 'MacAddress', 'SerialNumber', 'FirmwareVersion', 'Model', 'Manufacturer', 'Date',
             'NumberOfCameraHeads', 'CertificateSubjectCommonName', 'LegacyAnalyticsConfiguration', 'AdminUserName',
             'AdminPassword', 'SecondaryAdminPassword', 'AnalyticsHeader', 'Head', '')
###ENDCSV###

###PSPLAN###
# The file to import, in either shape, becomes settings.csv in the staging folder as CCT's own
# file - the one CCT is handed - and travels in the zip as edited.csv exactly as it was dropped,
# with analytics.csv beside it as edited-analytics.csv when there is one. The subnets for the
# rollback export come from the addresses in the file itself, one /24 per line. Returns
# "cameras|subnets|passwords|format".
$ErrorActionPreference = 'SilentlyContinue'
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'COLS###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'COLS###');Invoke-Expression $t.Substring($i,$j-$i)
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'CSV###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'CSV###');Invoke-Expression $t.Substring($i,$j-$i)
$file = Read-Any $env:IMPORTCSV
if ($null -eq $file) { Write-Output '0|0|0|none'; exit 0 }
Write-Native $file (Join-Path $env:PSOUT 'settings.csv')
Copy-Item -LiteralPath $env:IMPORTCSV -Destination (Join-Path $env:PSOUT 'edited.csv') -Force
$beside = Join-Path (Split-Path -Parent $env:IMPORTCSV) 'analytics.csv'
if ($file.Format -eq 'readable' -and (Test-Path -LiteralPath $beside)) { Copy-Item -LiteralPath $beside -Destination (Join-Path $env:PSOUT 'edited-analytics.csv') -Force }
$blocks = @{}
$passwords = 0
foreach ($mac in $file.Order) {
    $camera = $file.Cameras[$mac]
    $ip = Field $file $camera 'IpAddress'
    if ($ip -match '^(\d+)\.(\d+)\.(\d+)\.\d+$') { $blocks[('{0}.{1}.{2}' -f $matches[1], $matches[2], $matches[3])] = $true }
    if ((Field $file $camera 'AdminPassword') -ne '') { $passwords++ }
    if ((Field $file $camera 'SecondaryAdminPassword') -ne '') { $passwords++ }
}
$sorted = @($blocks.Keys | Sort-Object { [version]($_ + '.0') })
Set-Content -Path (Join-Path $env:PSOUT 'runlist-rollback.txt') -Value @($sorted | ForEach-Object { $_ + '.0 ' + $_ + '.255' }) -Encoding Default
Write-Output ('' + $file.Order.Count + '|' + $sorted.Count + '|' + $passwords + '|' + $file.Format)
###ENDPLAN###

###PSCHECK###
# PSMODE=rollback: the rollback - the file named in ROLLBACK, or the fresh export merged from
# rollback-parts\*.csv - held against the file to import. Writes plan.txt for the screen, changes.csv,
# settings.csv holding only the cameras that change with only their changed cells applied over
# the rollback's own rows, and the CCT run lists; returns "missing|changes|cameras|bad|runs|afterruns".
# PSMODE=after: merge after-parts\*.csv, hold it against what CCT was given, write camera.log, and
# return "notreached|remaining|failedruns".
$ErrorActionPreference = 'SilentlyContinue'
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'COLS###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'COLS###');Invoke-Expression $t.Substring($i,$j-$i)
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'CSV###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'CSV###');Invoke-Expression $t.Substring($i,$j-$i)
$out = $env:PSOUT
$mode = $env:PSMODE
$given = ('' + $env:ROLLBACK).Trim()
function Ip-Long([string]$v) { $o = $v -split '\.'; return [long]$o[0]*16777216 + [long]$o[1]*65536 + [long]$o[2]*256 + [long]$o[3] }
function Long-Ip([long]$n) { return ('{0}.{1}.{2}.{3}' -f (($n -shr 24) -band 255), (($n -shr 16) -band 255), (($n -shr 8) -band 255), ($n -band 255)) }
function Read-Lines([string]$name) { $p = Join-Path $out $name; if (Test-Path $p) { return @([IO.File]::ReadAllLines($p) | Where-Object { $_ -ne '' }) }; return @() }

# The rollback carries no extension, like the export's backup file: a double-click asks what to
# open it with rather than handing the one file that puts a site back to Excel.
$mergedPath = Join-Path $out $(if ($mode -eq 'rollback') { 'rollback' } else { 'after.csv' })
if ($mode -eq 'rollback' -and $given -ne '') {
    # The rollback came as a file. Whatever shape it arrived in, rollback in the zip is CCT's
    # own shape, so importing it still puts the site back.
    $actual = Read-Any $given
    if ($null -ne $actual) { Write-Native $actual $mergedPath }
} else {
    $parts = @(Get-ChildItem -Path (Join-Path $out ($mode + '-parts')) -Filter '*.csv' -File | Sort-Object { [version]$_.BaseName })
    $merged = New-Object System.Collections.Generic.List[string]
    $headerDone = $false
    foreach ($f in $parts) {
        foreach ($ln in [IO.File]::ReadAllLines($f.FullName, [Text.Encoding]::Unicode)) {
            if ($ln -eq '') { continue }
            if (($ln -split "`t")[0].EndsWith('Header')) { if (-not $headerDone) { $merged.Add($ln) } }
            else { $merged.Add($ln) }
        }
        if ($merged.Count -gt 0) { $headerDone = $true }
    }
    if ($merged.Count -gt 0) { [IO.File]::WriteAllLines($mergedPath, $merged, [Text.Encoding]::Unicode) }
    $actual = Read-Settings $mergedPath
}

$wanted = Read-Settings (Join-Path $out 'settings.csv')
$missing = @()
$diffs = @{}
$changedCameras = @{}
$applied = @{}
$detail = @()
# A cell the column cannot read - Quality 21, a bool that is neither True nor False - is left
# as it is on the camera: nothing is written for it, the plan says so, and the rest of the file
# goes ahead. Only the cells that differ are checked,
# and each is normalised first, so Excel's TRUE against the camera's True is not a change at all.
$bad = @()
$badCount = 0
# One row per change, kept beside the printed lines so changes.csv and the screen can never
# disagree - they are built from the same comparison in the same pass.
$rows = @()
function Change([string]$label, [string]$column, [string]$head, [string]$old, [string]$new) {
    # Three short lines rather than one long one: a camera name plus both values runs past any
    # console width and wraps mid-quote, which is unreadable exactly when it matters most.
    $line = '  ' + $label
    if ($head -ne '') { $line += '   head ' + $head }
    $out = @($line + '   ' + $column)
    $out += "      from  '" + $old + "'"
    $out += "      to    '" + $new + "'"
    return $out
}
foreach ($mac in $wanted.Order) {
    $camera = $wanted.Cameras[$mac]
    if ($null -eq $actual -or -not $actual.Cameras.ContainsKey($mac)) { $missing += (Label $wanted $camera); continue }
    $other = $actual.Cameras[$mac]
    $label = Label $wanted $camera
    $who = Who $wanted $camera
    $ip = Field $wanted $camera 'IpAddress'
    $applied[$mac] = @()
    for ($c = 0; $c -lt $wanted.DeviceColumns.Count; $c++) {
        $column = $wanted.DeviceColumns[$c]
        if ($ignored -contains $column) { continue }
        $k = [array]::IndexOf($actual.DeviceColumns, $column)
        if ($k -lt 0) { continue }
        $new = Bare $camera.Device[$c]
        $old = Bare $other.Device[$k]
        if ($new -ne $old) {
            $norm = Normalize $column $new
            if (-not $norm.Ok) { $badCount++; $bad += ('  ' + $label + '   ' + $column + "   '" + $new + "'"); $bad += ('      ' + $norm.Reason); continue }
            $new = $norm.Value
            if ($new -eq $old) { continue }
            $diffs[$column] = 1 + [int]$diffs[$column]
            $changedCameras[$mac] = $true
            $applied[$mac] += ,@($column, -1, $new)
            $detail += Change $label $column '' $old $new
            $rows += [PSCustomObject]@{ Camera = $who; IpAddress = $ip; Head = ''; Column = $column; From = $old; To = $new }
        }
    }
    if ($mode -eq 'rollback') {
        foreach ($column in @('AdminPassword', 'SecondaryAdminPassword')) {
            if ((Field $wanted $camera $column) -ne '') {
                $diffs[$column] = 1 + [int]$diffs[$column]
                $changedCameras[$mac] = $true
                $applied[$mac] += ,@($column, -1, (Field $wanted $camera $column))
                $detail += Change $label $column '' '' '(set)'
                # The value itself is never written to the CSV - a password does
                # not go into a log, a zip or a report.
                $rows += [PSCustomObject]@{ Camera = $who; IpAddress = $ip; Head = ''; Column = $column; From = ''; To = '(set)' }
            }
        }
    }
    $heads = [Math]::Min($camera.Analytics.Count, $other.Analytics.Count)
    for ($h = 0; $h -lt $heads; $h++) {
        for ($c = 0; $c -lt $wanted.AnalyticsColumns.Count; $c++) {
            $column = $wanted.AnalyticsColumns[$c]
            if ($ignored -contains $column) { continue }
            $k = [array]::IndexOf($actual.AnalyticsColumns, $column)
            if ($k -lt 0) { continue }
            $new = $camera.Analytics[$h][$c]
            $old = $other.Analytics[$h][$k]
            if ($new -ne $old) {
                $norm = Normalize $column $new
                if (-not $norm.Ok) { $badCount++; $bad += ('  ' + $label + '   head ' + ($h + 1) + '   ' + $column + "   '" + $new + "'"); $bad += ('      ' + $norm.Reason); continue }
                $new = $norm.Value
                if ($new -eq $old) { continue }
                $diffs[$column] = 1 + [int]$diffs[$column]
                $changedCameras[$mac] = $true
                $applied[$mac] += ,@($column, $h, $new)
                $detail += Change $label $column ($h + 1) $old $new
                $rows += [PSCustomObject]@{ Camera = $who; IpAddress = $ip; Head = ($h + 1); Column = $column; From = $old; To = $new }
            }
        }
    }
}
$total = 0
foreach ($v in $diffs.Values) { $total += $v }
$perColumn = ($diffs.GetEnumerator() | Sort-Object Name | ForEach-Object { $_.Name + ' ' + $_.Value }) -join ', '

if ($mode -eq 'rollback') {
    # What CCT is handed: the rollback's own rows for the cameras that change, with only the
    # changed cells applied. Every other camera is left out of the file, and out of the ranges.
    $narrow = @{ DeviceColumns = @(); AnalyticsColumns = @(); Cameras = @{}; Order = @(); Format = 'cct' }
    if ($null -ne $actual) { $narrow.DeviceColumns = $actual.DeviceColumns; $narrow.AnalyticsColumns = $actual.AnalyticsColumns }
    foreach ($mac in $wanted.Order) {
        if (-not $changedCameras.ContainsKey($mac)) { continue }
        $other = $actual.Cameras[$mac]
        $device = @() + $other.Device
        $analytics = @()
        foreach ($row in $other.Analytics) { $analytics += ,(@() + $row) }
        foreach ($a in $applied[$mac]) {
            if ($a[1] -lt 0) {
                $k = [array]::IndexOf($actual.DeviceColumns, $a[0])
                if ($k -ge 0) { $device[$k] = Quote $a[0] $a[2] }
            } else {
                $k = [array]::IndexOf($actual.AnalyticsColumns, $a[0])
                if ($k -ge 0 -and $a[1] -lt $analytics.Count) { $analytics[$a[1]][$k] = $a[2] }
            }
        }
        $narrow.Cameras[$mac] = @{ Device = $device; Analytics = $analytics }
        $narrow.Order += $mac
    }
    if ($narrow.Order.Count -gt 0) { Write-Native $narrow (Join-Path $out 'settings.csv') }

    # The CCT runs. Neighbouring changed cameras share one run; a run breaks at a /24 edge and
    # wherever a camera that is not changing sits between two that are, so no camera outside the
    # change is ever logged into. The proof export also walks the address a camera is moving to.
    function Ranges($addresses, $avoid) {
        $runs = @()
        $start = [long]-1
        $prev = [long]-1
        foreach ($n in @($addresses | Sort-Object -Unique)) {
            $n = [long]$n
            $join = $false
            if ($start -ge 0 -and [Math]::Floor($n / 256) -eq [Math]::Floor($prev / 256)) {
                $join = $true
                for ($x = $prev + 1; $x -lt $n; $x++) { if ($avoid.ContainsKey([long]$x)) { $join = $false; break } }
            }
            if (-not $join) {
                if ($start -ge 0) { $runs += ((Long-Ip $start) + ' ' + (Long-Ip $prev)) }
                $start = $n
            }
            $prev = $n
        }
        if ($start -ge 0) { $runs += ((Long-Ip $start) + ' ' + (Long-Ip $prev)) }
        return ,$runs
    }
    $avoid = @{}
    $now = @()
    $later = @()
    if ($null -ne $actual) {
        foreach ($m in $actual.Order) {
            $ipx = Field $actual $actual.Cameras[$m] 'IpAddress'
            if ($ipx -notmatch '^\d{1,3}(\.\d{1,3}){3}$') { continue }
            if ($changedCameras.ContainsKey($m)) {
                $now += (Ip-Long $ipx)
                $ipw = Field $wanted $wanted.Cameras[$m] 'IpAddress'
                if ($ipw -match '^\d{1,3}(\.\d{1,3}){3}$' -and $ipw -ne $ipx) { $later += (Ip-Long $ipw) }
            } else { $avoid[(Ip-Long $ipx)] = $true }
        }
    }
    $importRuns = Ranges $now $avoid
    $afterRuns = Ranges ($now + $later) $avoid
    Set-Content -Path (Join-Path $out 'runlist.txt') -Value $importRuns -Encoding Default
    Set-Content -Path (Join-Path $out 'runlist-after.txt') -Value $afterRuns -Encoding Default

    $plan = @()
    if ($given -ne '') {
        if ($null -eq $actual) { $plan += '  Rollback             : NOT A SETTINGS FILE - ' + $given }
        else {
            $dated = Field $actual $actual.Cameras[$actual.Order[0]] 'Date'
            $plan += '  Rollback             : from the file, ' + $actual.Order.Count + ' cameras' + $(if ($dated -ne '') { ', exported ' + $dated } else { '' })
        }
        $plan += '  In the rollback      : ' + ($wanted.Order.Count - $missing.Count) + ' of the ' + $wanted.Order.Count + ' cameras in the file (not checked online - the import run reports any that do not answer)'
    } else {
        $plan += '  Rollback             : exported just now'
        $plan += '  Answered just now    : ' + ($wanted.Order.Count - $missing.Count) + ' of the ' + $wanted.Order.Count + ' cameras in the file'
    }
    $plan += '  Settings to change   : ' + $total + $(if ($total) { '   (' + $perColumn + ')' } else { '' })
    $plan += '  Cameras to change    : ' + $changedCameras.Count + '   (every other camera is left alone - not written to, not logged into)'
    # The runs are only worth reading when the import will go ahead.
    if ($importRuns.Count -gt 0 -and $missing.Count -eq 0) {
        $seconds = 15 * ($importRuns.Count + $afterRuns.Count)
        $plan += '  CCT runs             : ' + $importRuns.Count + ' to import, ' + $afterRuns.Count + ' to prove it - roughly ' + $(if ($seconds -lt 120) { '' + $seconds + ' s' } else { '' + [Math]::Ceiling($seconds / 60) + ' min' }) + ' in all'
        $shown = 0
        foreach ($r in $importRuns) {
            $shown++
            if ($shown -gt 12) { $plan += ('    ... and ' + ($importRuns.Count - 12) + ' more'); break }
            $p = $r -split ' '
            $plan += ('    ' + $(if ($p[0] -eq $p[1]) { $p[0] } else { $p[0] + '-' + $p[1] }))
        }
    }
    if ($missing.Count -gt 0) {
        $plan += ''
        if ($given -ne '') { $plan += '  NOT IN THE ROLLBACK FILE - the import stops here, nothing is changed:' }
        else { $plan += '  DID NOT ANSWER - the import stops here, nothing is changed:' }
        foreach ($m in $missing) { $plan += ('    ' + $m) }
    }
    if ($bad.Count -gt 0) {
        $plan += ''
        $plan += '  LEFT AS THEY ARE - ' + $badCount + ' cells could not be read, so nothing is written for them and the'
        $plan += '  camera keeps what it has. If one was meant, fix that cell and run again afterwards:'
        foreach ($b in $bad) { $plan += ('  ' + $b) }
    }
    Set-Content -Path (Join-Path $out 'plan-skipped.txt') -Value $bad -Encoding Default
    if ($detail.Count -gt 0 -and $detail.Count -le 40) {
        $plan += ''
        foreach ($d in $detail) { $plan += $d }
    }
    if ($detail.Count -gt 40) {
        $plan += ''
        $plan += '  Too many to list here - changes.csv and camera.log in the zip have every one.'
    }
    $plan += ''
    Set-Content -Path (Join-Path $out 'plan.txt') -Value $plan -Encoding Default
    Set-Content -Path (Join-Path $out 'plan-detail.txt') -Value $detail -Encoding Default
    # Always written, always in the zip: the change list is the record of what this run intended,
    # and it costs nothing here because the comparison has already been made. The prompt in the
    # script only decides whether a copy is put beside the script for reading now.
    if ($rows.Count -gt 0) {
        $rows | Export-Csv -Path (Join-Path $out 'changes.csv') -NoTypeInformation -Encoding UTF8
    }
    Write-Output ('' + $missing.Count + '|' + $total + '|' + $changedCameras.Count + '|' + $badCount + '|' + $importRuns.Count + '|' + $afterRuns.Count)
    exit 0
}

function Secs([string]$t) { if ($t -match '(\d+)\D+(\d+)\D+(\d+)') { return [int]$matches[1] * 3600 + [int]$matches[2] * 60 + [int]$matches[3] }; return -1 }
function Runs([string]$name) {
    $runs = @{}
    foreach ($ln in (Read-Lines $name)) {
        $f = $ln -split '\|'
        if ($f.Count -lt 4) { continue }
        $el = -1
        $t0 = Secs $f[2]
        $t1 = Secs $f[3]
        if ($t0 -ge 0 -and $t1 -ge 0) { $el = $t1 - $t0; if ($el -lt 0) { $el += 86400 } }
        $runs[$f[0]] = @{ Rc = $f[1].Trim(); Elapsed = $el }
    }
    return $runs
}
function Table([string]$listName, [string]$runsName) {
    # One line per range in the list: CCT's exit code and how long it took, or "not run".
    $runs = Runs $runsName
    $lines = @()
    foreach ($ln in (Read-Lines $listName)) {
        $p = $ln -split ' '
        $range = $(if ($p[0] -eq $p[1]) { $p[0] } else { $p[0] + '-' + $p[1] })
        $cell = 'not run'
        if ($runs.ContainsKey($range)) {
            $r = $runs[$range]
            $cell = 'exit ' + $r.Rc + $(if ($r.Elapsed -ge 0) { ' in ' + $r.Elapsed + ' s' } else { '' })
        }
        $lines += ('  ' + $range.PadRight(32) + $cell)
    }
    return ,$lines
}
$importRuns = Runs 'runs-import.txt'
$failed = 0
foreach ($ln in (Read-Lines 'runlist.txt')) {
    $p = $ln -split ' '
    $range = $(if ($p[0] -eq $p[1]) { $p[0] } else { $p[0] + '-' + $p[1] })
    if (-not $importRuns.ContainsKey($range)) { $failed++ }
    elseif ($importRuns[$range].Rc -ne '0') { $failed++ }
}

$before = @()
$beforePath = Join-Path $out 'plan-detail.txt'
if (Test-Path $beforePath) { $before = @([IO.File]::ReadAllLines($beforePath) | Where-Object { $_ -ne '' }) }
$skipped = Read-Lines 'plan-skipped.txt'

$r = @()
$r += 'Import report - ' + $env:SITE + ' - ' + $env:RUNSTART
$r += 'File imported      : ' + $env:IMPORTCSV
$r += 'Cameras in file    : ' + $env:CAMERAS
$r += 'Rollback           : ' + $(if ($given -ne '') { 'from the file ' + $given } else { 'exported now, ' + $env:RUNCOUNT + ' subnets' })
$r += 'Intended changes   : ' + $env:CHANGES + ' settings on ' + $env:CHANGED + ' cameras'
$r += 'Written to         : ' + $wanted.Order.Count + ' cameras in ' + (Read-Lines 'runlist.txt').Count + ' CCT runs - no other camera was logged into'
$r += 'Not reached after  : ' + $missing.Count
$r += 'Did not take       : ' + $total + $(if ($total) { '   (' + $perColumn + ')' } else { '' })
$r += 'Left as they were  : ' + $env:BAD + ' cells the file held a value the column cannot read'
$r += 'CCT runs failed    : ' + $failed
$r += ''
if ($given -eq '') {
    $r += 'Rollback export, one run per subnet in the file:'
    $r += Table 'runlist-rollback.txt' 'runs-rollback.txt'
    $r += ''
}
$r += 'Import, one run per group of neighbouring changed cameras:'
$r += Table 'runlist.txt' 'runs-import.txt'
$r += ''
$r += 'Proof export, the same cameras read back:'
$r += Table 'runlist-after.txt' 'runs-after.txt'
$r += ''
if ($missing.Count -gt 0) {
    $r += 'NOT REACHED in the proof export - their state is unknown:'
    foreach ($m in $missing) { $r += ('  ' + $m) }
    $r += ''
}
if ($detail.Count -gt 0) {
    $r += 'DID NOT TAKE - still different after the import:'
    $r += $detail
    $r += ''
}
if ($before.Count -gt 0) {
    $r += 'INTENDED - what the file changed against the rollback:'
    $r += $before
    $r += ''
}
if ($skipped.Count -gt 0) {
    $r += 'LEFT AS THEY WERE - cells the column could not read; nothing was written for them:'
    $r += $skipped
    $r += ''
}
$r += 'rollback is every camera in the rollback as it was before the import: import it to put things back.'
$r += 'settings.csv is what CCT was given - only the cameras that changed. after.csv is those cameras as they'
$r += 'are now. edited.csv is the file as it was dropped here. console.log is CCT''s own output for every run.'
Set-Content -Path $env:PSRPT -Value $r -Encoding Default

$since = (Get-Date).AddHours(-12)
try { $since = [datetime]::ParseExact($env:RUNSTART, 'yyyy-MM-dd HH:mm:ss', $null) } catch {}
$cctDir = Join-Path $env:LOCALAPPDATA 'Motorola Solutions\Camera Configuration Tool'
$logLines = @()
foreach ($f in @(Get-ChildItem -Path $cctDir -Filter '*batchconsole*.log' -File -Recurse | Where-Object { $_.LastWriteTime -ge $since })) { $logLines += [IO.File]::ReadAllLines($f.FullName) }
if ($logLines.Count -gt 0) { Set-Content -Path (Join-Path $out 'console.log') -Value $logLines -Encoding Default }
Write-Output ('' + $missing.Count + '|' + $total + '|' + $failed)
###ENDCHECK###

###PSCOLS###
# Generated from src\camerasettings\camerasettings_columns.py by scripts\dev\columns_block.py: the
# column table as data. Regenerate it with --write; never edit it here.
$colQuote = @{}
$colKind = @{}
$colRole = @{}
$colWords = @{}
$colRole['DeviceHeader'] = 'marker'
$colRole['MacAddress'] = 'key'
$colQuote['Name'] = '"'
$colQuote['Location'] = '"'
$colQuote['SerialNumber'] = ''''
$colRole['SerialNumber'] = 'identity'
$colQuote['FirmwareVersion'] = '"'
$colRole['FirmwareVersion'] = 'identity'
$colRole['Model'] = 'identity'
$colRole['Manufacturer'] = 'identity'
$colRole['Date'] = 'identity'
$colKind['CameraLedDisabled'] = 'bool'
$colKind['DHCPEnabled'] = 'bool'
$colKind['IpAddress'] = 'ip'
$colKind['SubnetMask'] = 'ip'
$colKind['DefaultGateway'] = 'ip'
$colRole['AdminUserName'] = 'adminUser'
$colRole['AdminPassword'] = 'password'
$colRole['SecondaryAdminPassword'] = 'password'
$colKind['Encoding'] = 'choice|JPEG|MPEG4|H264|H265'
$colKind['FlickerControl'] = 'choice|50Hz|60Hz'
$colKind['WDREnabled'] = 'bool'
$colKind['ImageRate'] = 'int|1|'
$colKind['Quality'] = 'int|1|20'
$colKind['MaxBitrate'] = 'int|1|'
$colKind['Resolution'] = 'resolution'
$colKind['KeyframeInterval'] = 'int|1|'
$colKind['NumberOfCameraHeads'] = 'int||'
$colRole['NumberOfCameraHeads'] = 'identity'
$colKind['CameraMode'] = 'choice|Full Feature|High Framerate|No Video Analytics|No Smart Analytics|Dynamic Privacy Masks|Dewarp Streaming 90 x 4|Dewarp Streaming 120 x 3|Dewarp Streaming 180 x 2|None'
$colKind['NtpServerModeDhcp'] = 'choice|DHCP|Manual|None'
$colRole['CertificateSubjectCommonName'] = 'identity'
$colKind['EnableHttp'] = 'bool'
$colKind['HttpPort'] = 'int|1|65535'
$colKind['HttpsPort'] = 'int|1|65535'
$colKind['EnableAnalyticsMetadata'] = 'bool'
$colKind['EnableImageStabilization'] = 'bool'
$colKind['LegacyAnalyticsConfiguration'] = 'bool'
$colRole['LegacyAnalyticsConfiguration'] = 'identity'
$colRole['AnalyticsHeader'] = 'marker'
$colKind['Head'] = 'int||'
$colRole['Head'] = 'marker'
$colKind['CameraType'] = 'choice|0|1|2|3'
$colKind['AnalyticsSceneMode'] = 'choice|0|1|2|3|4|8'
$colKind['EnableNoiseFilter'] = 'bool'
$colKind['TamperSensitivity'] = 'int|1|10'
$colKind['TamperTriggerDelay'] = 'int|0|'
$colKind['EnableSelfLearning'] = 'bool'
$colKind['VideoAnalyticsMode'] = 'choice|0|1|2|3|4|5'
$colKind['EnableTamper'] = 'bool'
$colKind['TamperThreshold'] = 'float'
$colWords['CameraType'] = @{ '0' = 'Colour'; '1' = 'Black and White'; '2' = 'Day and Night'; '3' = 'Thermal' }
$colWords['AnalyticsSceneMode'] = @{ '0' = 'Outdoor'; '1' = 'Large Indoor Area'; '2' = 'Indoor Overhead'; '3' = 'Outdoor High Sensitivity'; '4' = 'Outdoor Long Range Night'; '8' = 'Indoor Close-Up' }
$colWords['VideoAnalyticsMode'] = @{ '0' = 'VAL - video analytics'; '1' = 'UMD - unusual motion detection'; '2' = 'Tamper only'; '3' = 'PTZ'; '4' = 'Classified object detection'; '5' = 'MSI tampering' }
###ENDCOLS###
