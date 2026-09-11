@echo off
rem Export camera settings with the Camera Configuration Tool and zip the result, with a per-camera
rem report of what logged in and what did not.
rem
rem CCT-Batch stops waiting for an address walk after about two minutes and exports whatever has
rem logged in by then (ARCHITECTURE.md section 5), so a site is never handed to it in one go. The script
rem ping-sweeps the range itself, probes the web ports on whatever answered, and runs CCT once per
rem subnet that holds a candidate. One /24 fits inside CCT's budget with room to spare; the
rem per-subnet CSVs are merged into settings.csv afterwards.
rem
rem Flags verified against CCT-Batch 2.16.0.0 by running the tool; run live against 2.6.0 on site.
rem Design rules and the defect history live in ARCHITECTURE.md; tests/check_bat.py enforces the
rem mechanical ones. The input form, the sweep and the report writer are PowerShell, embedded after
rem the final exit /b so exactly one file travels to site; the script reads them out of itself at
rem runtime. Free text never appears inside a parenthesised line and never rides a PowerShell
rem command line - it goes through the environment. No delayed expansion, ever: it mangles
rem passwords containing !.

setlocal
rem One number in three places - here, in "2 import settings.bat" and in camerasettings_main.py -
rem and tests/check_bat.py refuses a mismatch. Bumped on every edit, with its CHANGELOG entry.
set "VERSION=1.0.0"
title Camera Configuration Tool - Settings Export %VERSION%
color 07

rem The window is taken as it comes and everything is built to fit it. Windows Terminal ignores a
rem "mode con" resize but then reports the size that was asked for, so resizing first poisons the
rem probe and the rules wrap - measured on a real machine. Rule capped at 122 dashes to
rem match CCT's banner; the call trick substrings by a variable without enabling delayed expansion.
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
rem The ESC character, for coloured headings. TTL/RST stay empty until the form reports that
rem virtual terminal processing is actually on in this console - without it the codes print as
rem garbage, so plain text is the default and colour is the upgrade.
for /f "delims=" %%E in ('cmd /c "echo prompt $E| cmd"') do set "ESC=%%E"
set "TTL="
set "RST="
set "CCT=C:\Program Files (x86)\Motorola Solutions\Camera Configuration Tool\CCT-Batch.exe"
set "PSSELF=%~f0"

set "PSPW=%PW%"
set "PSRW=%RW%"

rem The window shows a small starting note within milliseconds, and the banner's FIRST appearance
rem is already yellow - painted a moment later by PowerShell through the console colour API, which
rem needs no VT. cmd never paints a white banner at all.
cls
echo.
echo   starting ...

if not exist "%CCT%" goto no_cct

rem CCT before 2.10.0 needs administrator rights and crashes rather than saying so. Relaunch
rem elevated via the standard Windows prompt; the --elevated marker stops a relaunch loop when
rem elevation is granted but a policy makes it ineffective.
net session >nul 2>&1
if not errorlevel 1 goto elevated
if /i "%~1"=="--elevated" goto no_admin
call :paint_banner
echo.
echo   Windows will now ask for administrator permission - answer Yes.
echo   This window closes and the export continues in a new one.
powershell -NoProfile -Command "try{Start-Process -FilePath $env:PSSELF -ArgumentList '--elevated' -Verb RunAs -ErrorAction Stop; exit 0}catch{exit 1}"
if errorlevel 1 goto uac_declined
endlocal
exit /b 0

:elevated
cls
echo.
echo   starting ...
set "CCTANS=%TEMP%\camera-export-answers.txt"
rem The form paints its fields under the banner already on screen - it never clears it. It
rem validates IPs on the spot and hands the answers back through a temp file, because a child
rem process cannot set this shell's variables. The scrollback restore rides in the same PowerShell
rem start: mode resets the buffer to the window height, which is what made the per-camera lines
rem impossible to review after a run.
powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'FORM###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'FORM###');Invoke-Expression $t.Substring($i,$j-$i)"
set "FRC=%ERRORLEVEL%"
if "%FRC%"=="0" goto form_ok
goto no_input

:form_ok
if not exist "%CCTANS%" goto no_input
for /f "usebackq tokens=1,* delims==" %%A in ("%CCTANS%") do set "%%A=%%B"
del "%CCTANS%" >nul 2>&1
if "%VT%"=="1" set "TTL=%ESC%[93m"
if "%VT%"=="1" set "RST=%ESC%[0m"

rem A wide range costs time, not correctness: 512 pings in flight behind CCT's own 5 s timeout
rem is about 6,000 addresses a minute. Say so, and let the technician decide.
if %ADDRCOUNT% LEQ 4096 goto range_ok
set /a SWEEPMIN=(ADDRCOUNT+6143)/6144
echo.
echo %TTL%%RULE%%RST%
echo %TTL%  That range is %ADDRCOUNT% addresses. The ping sweep alone takes roughly %SWEEPMIN% min, then%RST%
echo %TTL%  CCT reads each subnet that answers. A big range is fine - it just takes a while.%RST%
echo %TTL%%RULE%%RST%
rem choice strips leading spaces from its message exactly like set /p does; the armed reset code
rem is an invisible first character that carries the indent through on any VT console. One
rem keypress, no Enter. On a console without VT the prompt sits at column 0, plain - cosmetic.
if not "%VT%"=="1" goto confirm_plain
choice /c YN /n /m "%RST%  Type Y to go ahead, N to stop : "
goto confirm_done
:confirm_plain
choice /c YN /n /m "Type Y to go ahead, N to stop : "
:confirm_done
if errorlevel 2 goto cancelled

:range_ok
set "BASENAME=%SITE%_ACC_Camera_Settings_%STAMP%"
set "NAME=%BASENAME%"

rem The name carries a date but no time. A subnet that needs a re-run is re-run on its own, so
rem several runs on one day is the normal case - count up, never overwrite.
set "N=0"
:name_check
if %N% GEQ 50 goto too_many
if not exist "%~dp0%NAME%.zip" goto name_ok
set /a N+=1
set "NAME=%BASENAME%_%N%"
goto name_check

:name_ok
rem Files are staged in TEMP and the staging folder is deleted once the zip is proven to exist, so
rem the only thing left beside the script is the zip. Leftover staging from a crashed run is
rem cleared rather than mixed into this run's zip.
set "STAGE=%TEMP%\%NAME%"
set "CSV=%STAGE%\settings.csv"
set "LOG=%STAGE%\import.log"
set "RPT=%STAGE%\camera.log"
set "ZIP=%~dp0%NAME%.zip"

rmdir /s /q "%STAGE%" 2>nul
mkdir "%STAGE%" 2>nul
mkdir "%STAGE%\subnets" 2>nul

rem CCT-Batch assumes its own AppData log folder exists and crashes in Welcome() when it does not
rem (seen live on 2.6.0). Created here, in the same user context CCT runs in. That log is also
rem where the per-camera LoggedIn lines go, which the report is built from.
mkdir "%LOCALAPPDATA%\Motorola Solutions\Camera Configuration Tool" 2>nul

echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%Sweeping %IPRANGE%  -  %ADDRCOUNT% addresses%RST%
echo %TTL%%RULE%%RST%
echo.

rem The sweep pings every address with CCT's own 5 s timeout, then tries the HTTP and HTTPS ports
rem on whatever answered. CCT refuses an address that fails ping and cannot log in without a web
rem port, so a subnet with no candidate is one CCT would have spent 100 s on for nothing. It
rem writes runlist.txt - one subnet per line - and returns "answered|candidates|subnets".
set "PSOUT=%STAGE%"
set "ANSWERED=0"
set "CANDS=0"
set "RUNCOUNT=0"
for /f "usebackq tokens=1,2,3 delims=|" %%A in (`powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'SWEEP###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'SWEEP###');Invoke-Expression $t.Substring($i,$j-$i)"`) do set "ANSWERED=%%A" & set "CANDS=%%B" & set "RUNCOUNT=%%C"
echo.
echo   Answered ping    : %ANSWERED% addresses
echo   Web port open    : %CANDS% of them, in %RUNCOUNT% subnets
if "%RUNCOUNT%"=="0" goto runs_done

rem One CCT run per subnet, in address order. The loop body lives in a subroutine so no free text
rem is ever expanded inside the for block; pushd keeps the file name bare for the same reason.
set "RUNNO=0"
pushd "%STAGE%"
for /f "usebackq tokens=1,2" %%A in ("runlist.txt") do call :scan_subnet %%A %%B
popd

:runs_done
set "CAMPASS="

rem Merge the per-subnet CSVs into settings.csv, copy CCT's console log lines for this run into the
rem folder and build camera.log from all of it: every subnet's outcome, every camera line that is
rem not LoggedIn flagged. Returns "attention|exported|ok|empty|problem" counts.
set "PSCSV=%CSV%"
set "PSRPT=%RPT%"
set "ATTN=0"
set "CAMERAS=0"
set "OKRUNS=0"
set "EMPTYRUNS=0"
set "PROBLEMRUNS=0"
for /f "usebackq tokens=1-5 delims=|" %%A in (`powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'RPT###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'RPT###');Invoke-Expression $t.Substring($i,$j-$i)"`) do set "ATTN=%%A" & set "CAMERAS=%%B" & set "OKRUNS=%%C" & set "EMPTYRUNS=%%D" & set "PROBLEMRUNS=%%E"

rem The readable copies. CCT's own file keeps travelling, untouched, as the backup file -
rem "backup", no date and no extension so a double-click cannot hand it to Excel; settings.csv
rem becomes the same cameras as one comma-separated row each, and analytics.csv one row per head.
rem Those two open in Excel, get edited, and go to the import, which reads either shape.
set "RCAMERAS=0"
set "RHEADS=0"
if not exist "%CSV%" goto readable_done
ren "%CSV%" "%BACKUP%"
set "PSCSV=%STAGE%\%BACKUP%"
set "PSREADABLE=%STAGE%\settings.csv"
set "PSANALYTICS=%STAGE%\analytics.csv"
for /f "usebackq tokens=1,2 delims=|" %%A in (`powershell -NoProfile -Command "$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'READABLE###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'READABLE###');Invoke-Expression $t.Substring($i,$j-$i)"`) do set "RCAMERAS=%%A" & set "RHEADS=%%B"
:readable_done

rem The verdict is for the whole site. A subnet's own CCT exit code is in camera.log; a subnet
rem that failed, crashed, or ran past CCT's two-minute budget counts as a problem and is named
rem there for a re-run on its own.
set "RC=11"
set "VERDICT=PARTIAL - %PROBLEMRUNS% of %RUNCOUNT% subnets need a re-run. camera.log names them"
if not "%PROBLEMRUNS%"=="0" goto verdict_done
set "RC=2"
set "VERDICT=FAILED - nothing in that range answered ping with a web port open. Check the range and the ports"
if "%RUNCOUNT%"=="0" goto verdict_done
set "VERDICT=FAILED - addresses answered, but no camera logged in. Check the username and password"
if "%CAMERAS%"=="0" goto verdict_done
set "RC=0"
set "VERDICT=SUCCESS - %CAMERAS% cameras exported from %OKRUNS% subnets"
:verdict_done

rem The password is never written here. This log travels back inside the zip.
>  "%LOG%" echo Camera settings export
>> "%LOG%" echo -------------------------------------
>> "%LOG%" echo Site        : %SITE%
>> "%LOG%" echo File        : %NAME%.zip
>> "%LOG%" echo Range       : %IPRANGE% - %ADDRCOUNT% addresses
>> "%LOG%" echo Username    : %CAMUSER%
>> "%LOG%" echo Ports       : HTTP %HTTPPORT%, HTTPS %HTTPSPORT%
>> "%LOG%" echo Run at      : %RUNSTART%
>> "%LOG%" echo Sweep       : %ANSWERED% answered ping, %CANDS% with a web port open, in %RUNCOUNT% subnets
>> "%LOG%" echo Subnets     : %OKRUNS% exported, %EMPTYRUNS% had no camera, %PROBLEMRUNS% need a re-run
>> "%LOG%" echo Script exit : %RC%
>> "%LOG%" echo Result      : %VERDICT%
>> "%LOG%" echo Exported    : %CAMERAS% cameras
>> "%LOG%" echo Readable    : settings.csv holds %RCAMERAS% cameras, analytics.csv %RHEADS% heads; %BACKUP% is CCT's own file
>> "%LOG%" echo Attention   : %ATTN% cameras answered but did not log in

set "PSSRC=%STAGE%\*"
set "PSZIP=%ZIP%"
powershell -NoProfile -Command "Compress-Archive -Path $env:PSSRC -DestinationPath $env:PSZIP -Force"
if exist "%ZIP%" rmdir /s /q "%STAGE%" 2>nul

echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%%VERDICT%%RST%
echo %TTL%%RULE%%RST%
echo.
echo   Addresses swept  : %ADDRCOUNT%  -  %ANSWERED% answered ping, %CANDS% had a web port open
echo   Subnets run      : %RUNCOUNT%  -  %OKRUNS% exported, %EMPTYRUNS% had no camera, %PROBLEMRUNS% need a re-run
echo   Cameras exported : %CAMERAS%
if not "%ATTN%"=="0" echo   NEEDS ATTENTION  : %ATTN% cameras answered but did not log in - camera.log in the zip lists them
if exist "%ZIP%" echo   Send back        : %ZIP%
if not exist "%ZIP%" echo   ZIP FAILED - send this folder instead : %STAGE%
echo.
echo   Scroll up to review each camera line. Inside the zip: settings.csv - one row per camera,
echo   open it in Excel to edit; analytics.csv - one row per camera head; %BACKUP% - the
echo   file as CCT wrote it, the rollback point; camera.log, console.log, import.log, and one
echo   CSV per subnet under subnets.
if "%RC%"=="0" goto report_end
echo.
if "%RC%"=="11" goto advice_partial
echo   What to do       : check the username, password and ports, then run it again. If the
echo                      cameras sit on a network this machine cannot reach, run it from one
echo                      that can. Send the zip anyway - the logs inside say what answered.
goto report_end

:advice_partial
echo   What to do       : camera.log names each subnet that needs a re-run. Run this again with
echo                      that subnet's first and last address as the Start and End IP. A one-off
echo                      glitch is common; if it fails the same way twice, send the zip anyway.

:report_end
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
rem endlocal on the same line: on its own it would discard RC before exit /b read it.
endlocal & exit /b %RC%

rem Every stop reports the same three things: what happened, that nothing was changed, and what
rem to do next. A technician in a comms room acts on the last line.

:scan_subnet
rem One CCT run. -f is required: most addresses in a subnet hold no camera, and without it the job
rem stops at the first address that does not answer. The exit code and the wall-clock times go to
rem runs.txt for the report; the CSV is named after the subnet's first address.
set /a RUNNO+=1
set "SUBSTART=%~1"
set "SUBEND=%~2"
set "SUBRANGE=%SUBSTART%-%SUBEND%"
set "SUBCSV=%STAGE%\subnets\%SUBSTART%.csv"
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%Subnet %RUNNO% of %RUNCOUNT%  -  %SUBRANGE%%RST%
echo %TTL%%RULE%%RST%
set "T0=%TIME%"
"%CCT%" -a %SUBRANGE% -u "%CAMUSER%" -p "%CAMPASS%" -t %HTTPPORT% -s %HTTPSPORT% -f -e "%SUBCSV%"
set "SUBRC=%ERRORLEVEL%"
>> "%STAGE%\runs.txt" echo %SUBRANGE%^|%SUBRC%^|%T0%^|%TIME%
goto :eof

:paint_banner
rem Paints the banner yellow through the console colour API - no VT needed for that - and arms VT
rem for the cmd-echoed headings that follow. Runs once; later callers fall straight through.
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
echo                   "1 export settings.bat" again. If it is installed somewhere unusual, the
echo                   CCT= line near the top of this file holds the path to change.
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
echo   What to do      Run "1 export settings.bat" again and answer Yes. The Camera
echo                   Configuration Tool needs administrator rights on this machine, and
echo                   without them it crashes rather than reporting properly.
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
echo   What to do      Right-click "1 export settings.bat" yourself and choose "Run as
echo                   administrator". If that fails too, this machine's policy blocks it -
echo                   run the export from a different machine on the camera network.
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
echo   What to do      Run "1 export settings.bat" again, type each answer into the form
echo                   and press Enter after it.
echo.
echo %TTL%%RULE%%RST%
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 1

:cancelled
echo.
echo   Cancelled. Nothing was changed, no camera was touched.
echo.
echo   Press any key to close this window . . .
pause >nul
endlocal
exit /b 0

:too_many
cls
echo.
echo %TTL%%RULE%%RST%
echo %PAD%  %TTL%STOPPED - too many exports here for one day%RST%
echo %TTL%%RULE%%RST%
echo.
echo   What happened   There are already 50 exports for this site, today, in this folder.
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
    [Console]::SetCursorPosition(0, 2); Write-Host ($bpad + 'Camera Configuration Tool - Settings Export') -ForegroundColor Yellow -NoNewline
    [Console]::SetCursorPosition(0, 3); Write-Host ($bpad + 'v' + $env:VERSION + ' - reads camera settings, changes nothing') -ForegroundColor Yellow -NoNewline
    [Console]::SetCursorPosition(0, 4); Write-Host $ry -ForegroundColor Yellow -NoNewline
    [Console]::SetCursorPosition(0, 6)
} catch {}
$vtOn
###ENDVT###

###PSFORM###
$ErrorActionPreference = 'Stop'
function Test-Ip([string]$v) { return ($v -match '^\d{1,3}(\.\d{1,3}){3}$') -and ($null -ne ($v -as [ipaddress])) }
function Ip-Long([string]$v) { $o = $v -split '\.'; return [long]$o[0]*16777216 + [long]$o[1]*65536 + [long]$o[2]*256 + [long]$o[3] }

$labels = @('Site name','Start IP','End IP','Camera username','Camera password','HTTP port','HTTPS port')
$vals   = @('','','','','','80','443')
$plain = $true
$vt = $false
try { $plain = ([Console]::IsInputRedirected -or [Console]::IsOutputRedirected) } catch {}

$firstRow = 6
$fw = 80
if (-not $plain) {
    try { $r = $Host.UI.RawUI; $b = $r.BufferSize; if ($b.Height -lt 9000) { $b.Height = 9000; $r.BufferSize = $b } } catch {}
    $firstRow = 6
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
        [Console]::SetCursorPosition(0, [Math]::Max(0, $firstRow - 4)); Write-Host ($bpad + 'Camera Configuration Tool - Settings Export') -ForegroundColor Yellow -NoNewline
        [Console]::SetCursorPosition(0, [Math]::Max(0, $firstRow - 3)); Write-Host ($bpad + 'v' + $env:VERSION + ' - reads camera settings, changes nothing') -ForegroundColor Yellow -NoNewline
        [Console]::SetCursorPosition(0, [Math]::Max(0, $firstRow - 2)); Write-Host $ry -ForegroundColor Yellow -NoNewline
    } catch {}
    for ($i = 0; $i -lt $labels.Count; $i++) {
        [Console]::SetCursorPosition(0, $firstRow + $i)
        [Console]::Write('  ' + $labels[$i].PadRight(26) + ': ' + $vals[$i].PadRight($fw))
    }
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
    if ($script:plain) { [Console]::Error.Write($script:labels[$i].PadRight(26) + ': '); return [Console]::ReadLine() }
    # Edit-in-place: the shown value is the buffer, cursor at its end. Enter accepts it as it
    # stands, Backspace eats it - so a prefilled port is kept with one keypress and never blanks.
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
            if ($in -eq '') { $err = 'The site name is needed - it names the file you send back.' } }
        1 { if (-not (Test-Ip $in)) { $err = 'That is not an IP address. Four numbers 0-255 with dots, like 10.30.200.1' } }
        2 { if (-not (Test-Ip $in)) { $err = 'The end of the range is needed - the last camera address, like 10.30.200.254' }
            elseif ((Ip-Long $in) -lt (Ip-Long $vals[1])) { $err = 'The end IP is before the start IP.' }
            elseif ((Ip-Long $in) - (Ip-Long $vals[1]) -ge 65536) { $err = 'That is more than 65,536 addresses - wider than a whole /16. Check the End IP.' } }
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

$count = (Ip-Long $vals[2]) - (Ip-Long $vals[1]) + 1
$range = if ($vals[1] -eq $vals[2]) { $vals[1] } else { $vals[1] + '-' + $vals[2] }
$lines = @(
    ('SITE=' + $vals[0]), ('STARTIP=' + $vals[1]), ('ENDIP=' + $vals[2]),
    ('CAMUSER=' + $vals[3]), ('CAMPASS=' + $vals[4]),
    ('HTTPPORT=' + $vals[5]), ('HTTPSPORT=' + $vals[6]),
    ('ADDRCOUNT=' + $count), ('IPRANGE=' + $range),
    ('STAMP=' + (Get-Date -Format 'dd_MM_yy')), ('RUNSTART=' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')),
    ('BACKUP=backup'),
    ('VT=' + $(if ($vt) { '1' } else { '0' }))
)
Set-Content -Path $env:CCTANS -Value $lines -Encoding Default
exit 0
###ENDFORM###

###PSSWEEP###
$ErrorActionPreference = 'SilentlyContinue'
function Ip-Long([string]$v) { $o = $v -split '\.'; return [long]$o[0]*16777216 + [long]$o[1]*65536 + [long]$o[2]*256 + [long]$o[3] }
function Long-Ip([long]$n) { return ('{0}.{1}.{2}.{3}' -f (($n -shr 24) -band 255), (($n -shr 16) -band 255), (($n -shr 8) -band 255), ($n -band 255)) }

$first = Ip-Long $env:STARTIP
$last  = Ip-Long $env:ENDIP
$total = $last - $first + 1
$ports = @([int]$env:HTTPPORT, [int]$env:HTTPSPORT) | Select-Object -Unique
# 5000 ms is CCT's own ping timeout: an address the sweep gives up on is one CCT would give up on
# too, so nothing CCT could have read is skipped. 512 in flight is five times CCT's own rate.
$pingWait = 5000
$portWait = 3000
$batch = 512

# Where CCT's console log for today ends right now. The report reads only what comes after, so
# an earlier run today - another subnet, another site - is never counted as this one.
$cctDir = Join-Path $env:LOCALAPPDATA 'Motorola Solutions\Camera Configuration Tool'
$marks = @()
foreach ($f in @(Get-ChildItem -Path $cctDir -Filter '*batchconsole*.log' -File -Recurse)) { $marks += ('' + $f.Length + '|' + $f.FullName) }
Set-Content -Path (Join-Path $env:PSOUT 'logmark.txt') -Value $marks -Encoding Default

# 1. Ping everything.
$live = New-Object System.Collections.Generic.List[long]
$done = 0
for ($b = $first; $b -le $last; $b += $batch) {
    $top = [Math]::Min($last, $b + $batch - 1)
    $pingers = New-Object System.Collections.Generic.List[object]
    $tasks = New-Object System.Collections.Generic.List[System.Threading.Tasks.Task]
    for ($n = $b; $n -le $top; $n++) {
        $p = New-Object System.Net.NetworkInformation.Ping
        $pingers.Add($p)
        $tasks.Add($p.SendPingAsync((Long-Ip $n), $pingWait))
    }
    try { [System.Threading.Tasks.Task]::WaitAll($tasks.ToArray(), $pingWait + 2000) | Out-Null } catch {}
    for ($k = 0; $k -lt $tasks.Count; $k++) {
        $t = $tasks[$k]
        if ($t.Status -eq 'RanToCompletion' -and $t.Result.Status -eq 'Success') { $live.Add($b + $k) }
        $pingers[$k].Dispose()
    }
    $done += ($top - $b + 1)
    [Console]::Error.Write(("`r  Ping     {0,7} of {1} addresses checked, {2} answered" -f $done, $total, $live.Count))
}
[Console]::Error.WriteLine()

# 2. Try the web ports on what answered. A camera CCT can read accepts a connection on the HTTP
#    or HTTPS port it was given; a PC, a phone or a printer with neither open cannot be one.
$cand = New-Object System.Collections.Generic.List[long]
$liveArr = $live.ToArray()
for ($b = 0; $b -lt $liveArr.Count; $b += 256) {
    $top = [Math]::Min($liveArr.Count - 1, $b + 255)
    $clients = New-Object System.Collections.Generic.List[object]
    $owners = New-Object System.Collections.Generic.List[long]
    $tasks = New-Object System.Collections.Generic.List[System.Threading.Tasks.Task]
    for ($k = $b; $k -le $top; $k++) {
        foreach ($port in $ports) {
            $c = New-Object System.Net.Sockets.TcpClient
            $clients.Add($c)
            $owners.Add($liveArr[$k])
            $tasks.Add($c.ConnectAsync([System.Net.IPAddress]::Parse((Long-Ip $liveArr[$k])), $port))
        }
    }
    try { [System.Threading.Tasks.Task]::WaitAll($tasks.ToArray(), $portWait) | Out-Null } catch {}
    $open = @{}
    for ($k = 0; $k -lt $tasks.Count; $k++) {
        if ($tasks[$k].Status -eq 'RanToCompletion') { $open[$owners[$k]] = $true }
        $clients[$k].Dispose()
    }
    foreach ($n in ($open.Keys | Sort-Object)) { $cand.Add([long]$n) }
    [Console]::Error.Write(("`r  Web port {0,7} of {1} answering addresses checked, {2} open" -f ($top + 1), $liveArr.Count, $cand.Count))
}
if ($liveArr.Count -gt 0) { [Console]::Error.WriteLine() }

# 3. One /24 per line. sweep.txt is every subnet that answered ping, for the report; runlist.txt
#    is the subset with a candidate, which is what CCT gets.
$pingCount = @{}
$candCount = @{}
foreach ($n in $live) { $bs = $n - ($n % 256); $pingCount[$bs] = 1 + [int]$pingCount[$bs] }
foreach ($n in $cand) { $bs = $n - ($n % 256); $candCount[$bs] = 1 + [int]$candCount[$bs] }
$sweep = @()
$runlist = @()
foreach ($bs in ($pingCount.Keys | Sort-Object)) {
    $from = [Math]::Max([long]$bs, $first)
    $to = [Math]::Min([long]$bs + 255, $last)
    $sweep += ('{0} {1} {2} {3}' -f (Long-Ip $from), (Long-Ip $to), $pingCount[$bs], [int]$candCount[$bs])
    if ([int]$candCount[$bs] -gt 0) { $runlist += ('{0} {1}' -f (Long-Ip $from), (Long-Ip $to)) }
}
Set-Content -Path (Join-Path $env:PSOUT 'sweep.txt') -Value $sweep -Encoding Default
Set-Content -Path (Join-Path $env:PSOUT 'runlist.txt') -Value $runlist -Encoding Default
Set-Content -Path (Join-Path $env:PSOUT 'candidates.txt') -Value @($cand | ForEach-Object { Long-Ip $_ }) -Encoding Default
Write-Output ('' + $live.Count + '|' + $cand.Count + '|' + $runlist.Count)
###ENDSWEEP###

###PSRPT###
$ErrorActionPreference = 'SilentlyContinue'
function Ip-Long([string]$v) { $o = $v -split '\.'; return [long]$o[0]*16777216 + [long]$o[1]*65536 + [long]$o[2]*256 + [long]$o[3] }
function Long-Ip([long]$n) { return ('{0}.{1}.{2}.{3}' -f (($n -shr 24) -band 255), (($n -shr 16) -band 255), (($n -shr 8) -band 255), ($n -band 255)) }
function Read-Lines([string]$name) { $p = Join-Path $env:PSOUT $name; if (Test-Path $p) { return @([IO.File]::ReadAllLines($p) | Where-Object { $_ -ne '' }) }; return @() }
$out = $env:PSOUT
$since = (Get-Date).AddHours(-6)
try { $since = [datetime]::ParseExact($env:RUNSTART, 'yyyy-MM-dd HH:mm:ss', $null) } catch {}

# 1. Merge the per-subnet CSVs into settings.csv. CCT writes UTF-16 with a byte-order mark and a
#    fixed header block - the lines whose first field ends in "Header" - identical for every run
#    of the same CCT build. The header comes from the first file, the rows from all of them, in
#    subnet order, and the file is written back exactly as CCT would have: UTF-16 with the mark.
$subnetDir = Join-Path $out 'subnets'
$parts = @(Get-ChildItem -Path $subnetDir -Filter '*.csv' -File | Sort-Object { [version]$_.BaseName })
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
if ($merged.Count -gt 0) { [IO.File]::WriteAllLines($env:PSCSV, $merged, [Text.Encoding]::Unicode) }
if ($parts.Count -eq 0) { Remove-Item -Path $subnetDir -Force -Recurse }

# 2. CCT-Batch appends its console output - the per-camera LoggedIn lines included - to a dated
#    log in its own AppData folder. Only what was written after the mark taken before the first
#    run is this run's; that part travels in the zip as console.log.
$marks = @{}
foreach ($ln in (Read-Lines 'logmark.txt')) { $i = $ln.IndexOf('|'); if ($i -gt 0) { $marks[$ln.Substring($i + 1)] = [long]$ln.Substring(0, $i) } }
$cctDir = Join-Path $env:LOCALAPPDATA 'Motorola Solutions\Camera Configuration Tool'
$logLines = @()
$logFiles = @(Get-ChildItem -Path $cctDir -Filter '*batchconsole*.log' -File -Recurse | Where-Object { $_.LastWriteTime -ge $since } | Sort-Object LastWriteTime)
foreach ($f in $logFiles) {
    $bytes = [IO.File]::ReadAllBytes($f.FullName)
    $skip = 0
    if ($marks.ContainsKey($f.FullName) -and $marks[$f.FullName] -lt $bytes.Length) { $skip = [int]$marks[$f.FullName] }
    $logLines += ([Text.Encoding]::UTF8.GetString($bytes, $skip, $bytes.Length - $skip) -split "`r?`n")
}
if ($logLines.Count -gt 0) { Set-Content -Path (Join-Path $out 'console.log') -Value $logLines -Encoding Default }

# 3. Any per-camera line whose status word is not LoggedIn needs eyes on it. The vocabulary of
#    failure words is CCT's own and not assumed here - not-LoggedIn is the test. Last line per
#    address wins.
$status = @{}
foreach ($ln in $logLines) {
    $clean = $ln -replace '\x1b\[[0-9;]*m', ''
    if ($clean -match '^\s*(\d{1,3}(?:\.\d{1,3}){3})\s+(\S+)\s*(.*)$') {
        $status[$matches[1]] = @($matches[2], $matches[3].Trim())
    }
}

# 4. What reached the CSV.
$exported = @()
if (Test-Path $env:PSCSV) {
    foreach ($row in [IO.File]::ReadAllLines($env:PSCSV)) {
        $c = $row -split "`t"
        if ($c[0] -eq 'Device' -and $c.Count -gt 11) {
            $exported += [pscustomobject]@{ Ip = $c[11]; Mac = $c[1]; Name = ($c[2] -replace '^"|"$', '') }
        }
    }
}
$attention = @($status.Keys | Where-Object { $status[$_][0] -ne 'LoggedIn' } | Sort-Object { [version]$_ })
$loggedIn = @($status.Keys | Where-Object { $status[$_][0] -eq 'LoggedIn' }).Count

# 5. Every subnet: what the sweep saw, what CCT made of it. A run is late when it lasted 115 s
#    or more: an empty result ends by CCT's 100th poll and a cut-off walk by its 121st, so the
#    two never overlap (ARCHITECTURE.md section 5). Late means addresses went unchecked - re-run in halves.
$cutOff = 115
$rcText = @{
    '0' = 'SUCCESS'; '1' = 'FAILED - a parameter was wrong'; '2' = 'no camera logged in'
    '3' = 'FAILED - devices answered but none could be read; their status is below'
    '4' = 'FAILED - a camera does not support export'; '5' = 'FAILED - unexpected error'
    '6' = 'PARTIAL - at least one camera failed'; '7' = 'FAILED - output file extension not supported'
    '9' = 'FAILED - could not write the output file'; '10' = 'FAILED - the account does not have permission'
    '11' = 'PARTIAL - only some cameras were exported'; '12' = 'FAILED - the CCT install is missing a component'
    '17' = 'FAILED - the data read back did not validate'; '20' = 'FAILED'
    '-532462766' = 'CRASHED - CCT hit an unhandled error and stopped. Not a camera fault'
}
function Secs([string]$t) { if ($t -match '(\d+)\D+(\d+)\D+(\d+)') { return [int]$matches[1] * 3600 + [int]$matches[2] * 60 + [int]$matches[3] }; return -1 }
$runs = @{}
foreach ($ln in (Read-Lines 'runs.txt')) {
    $p = $ln -split '\|'
    if ($p.Count -lt 4) { continue }
    $t0 = Secs $p[2]; $t1 = Secs $p[3]
    $el = -1
    if ($t0 -ge 0 -and $t1 -ge 0) { $el = $t1 - $t0; if ($el -lt 0) { $el += 86400 } }
    $runs[$p[0]] = @{ Rc = $p[1].Trim(); Elapsed = $el }
}
$okRuns = 0; $emptyRuns = 0; $problemRuns = 0
$table = @()
$rerun = @()
foreach ($ln in (Read-Lines 'sweep.txt')) {
    $p = $ln -split ' '
    if ($p.Count -lt 4) { continue }
    $from = Ip-Long $p[0]; $to = Ip-Long $p[1]
    $range = $p[0] + '-' + $p[1]
    $cams = @($exported | Where-Object { $l = Ip-Long $_.Ip; $l -ge $from -and $l -le $to }).Count
    $result = 'skipped - no web port open'
    $camsText = '-'
    if ([int]$p[3] -gt 0) {
        $camsText = '' + $cams
        if (-not $runs.ContainsKey($range)) { $result = 'not run'; $problemRuns++ }
        else {
            $r = $runs[$range]
            $text = $rcText[$r.Rc]
            if ($null -eq $text) { $text = 'UNKNOWN - exit code ' + $r.Rc + ' is not one this script recognises' }
            if ($r.Elapsed -ge 0) { $text += '  (' + $r.Elapsed + ' s)' }
            if ($r.Elapsed -ge $cutOff) {
                $mid = $from + [Math]::Floor(($to - $from) / 2)
                $halves = (Long-Ip $from) + '-' + (Long-Ip $mid) + ' and ' + (Long-Ip ($mid + 1)) + '-' + (Long-Ip $to)
                $text = 'INCOMPLETE - CCT ran out of time at ' + $r.Elapsed + ' s and left addresses unchecked. Re-run as ' + $halves
                $rerun += $range; $problemRuns++
            }
            elseif ($r.Rc -eq '0') { $okRuns++ }
            elseif ($r.Rc -eq '2') { $emptyRuns++ }
            else { $rerun += $range; $problemRuns++ }
            $result = $text
        }
    }
    $table += ('  ' + $range.PadRight(32) + $p[2].PadLeft(5) + $p[3].PadLeft(6) + $camsText.PadLeft(9) + '   ' + $result)
}

# 6. Addresses the sweep put forward that CCT never mentioned: switches, NVRs and printers with a
#    web page land here - and so would a camera CCT cannot talk to, which is why they are listed.
$unrecognized = @((Read-Lines 'candidates.txt') | Where-Object { -not $status.ContainsKey($_) } | Sort-Object { [version]$_ })

$r = @()
$r += 'Camera report - ' + $env:SITE + ' - ' + $env:RUNSTART
$r += 'Range swept        : ' + $env:IPRANGE + '  (' + $env:ADDRCOUNT + ' addresses)'
$r += 'Answered ping      : ' + $env:ANSWERED
$r += 'Web port open      : ' + $env:CANDS + '  (in ' + $env:RUNCOUNT + ' subnets)'
$r += 'Subnets run        : ' + $env:RUNCOUNT + '  -  ' + $okRuns + ' exported, ' + $emptyRuns + ' had no camera, ' + $problemRuns + ' need a re-run'
$r += 'Logged in          : ' + $loggedIn
$r += 'Exported to CSV    : ' + $exported.Count
$r += 'Needs attention    : ' + $attention.Count
$r += ''
if ($rerun.Count -gt 0) {
    $r += 'RE-RUN THESE SUBNETS on their own - Start IP and End IP as shown:'
    foreach ($x in $rerun) { $r += ('  ' + $x) }
    $r += ''
}
$r += 'Subnets that answered ping:'
$r += '  ' + 'range'.PadRight(32) + ' ping   web  cameras   CCT result'
$r += $table
$r += ''
if ($attention.Count -gt 0) {
    $r += 'NEEDS ATTENTION - these addresses answered but did not log in:'
    foreach ($ip in $attention) { $r += ('  ' + $ip.PadRight(16) + $status[$ip][0].PadRight(20) + $status[$ip][1]) }
    $r += ''
}
if ($loggedIn -ne $exported.Count) {
    $r += ('NOTE: ' + $loggedIn + ' cameras logged in but ' + $exported.Count + ' reached the CSV - compare the lists below.')
    $r += ''
}
$r += 'Exported cameras, by address:'
foreach ($cam in ($exported | Sort-Object { [version]$_.Ip })) { $r += ('  ' + $cam.Ip.PadRight(16) + $cam.Mac.PadRight(19) + $cam.Name) }
$r += ''
if ($unrecognized.Count -gt 0) {
    $r += 'Answered ping with a web port open, but CCT reported no camera there - switches, NVRs and'
    $r += 'printers land here, and so would a camera CCT cannot talk to:'
    foreach ($ip in $unrecognized) { $r += ('  ' + $ip) }
    $r += ''
}
$r += 'A subnet with no line above had nothing answering ping in it. The full CCT output, address'
$r += 'by address, is in console.log in this zip.'
Set-Content -Path $env:PSRPT -Value $r -Encoding Default

foreach ($name in @('logmark.txt', 'sweep.txt', 'runlist.txt', 'runs.txt', 'candidates.txt')) { Remove-Item -Path (Join-Path $out $name) -Force }
Write-Output ('' + $attention.Count + '|' + $exported.Count + '|' + $okRuns + '|' + $emptyRuns + '|' + $problemRuns)
###ENDRPT###

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

###PSREADABLE###
# CCT's own file has just become the backup file. This writes the two files a person opens: settings.csv,
# one comma-separated row per camera in CCT's column order without CCT's quoting, and
# analytics.csv, one row per camera head with the coded values as words. Both are UTF-8 with a
# byte-order mark, which is what makes Excel open them as they are. Returns "cameras|heads".
$ErrorActionPreference = 'SilentlyContinue'
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'CSV###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'CSV###');Invoke-Expression $t.Substring($i,$j-$i)
$t=[IO.File]::ReadAllText($env:PSSELF);$a='###PS'+'COLS###';$i=$t.IndexOf($a)+$a.Length;$j=$t.IndexOf('###END'+'COLS###');Invoke-Expression $t.Substring($i,$j-$i)
$file = Read-Settings $env:PSCSV
if ($null -eq $file) { Write-Output '0|0'; exit 0 }
function Csv([string]$v) {
    if ($v -match '[",\r\n]') { return '"' + $v.Replace('"', '""') + '"' }
    return $v
}
function Word([string]$column, [string]$v) {
    if ($colWords.ContainsKey($column) -and $colWords[$column].ContainsKey($v)) { return $colWords[$column][$v] }
    return $v
}
$utf8 = New-Object System.Text.UTF8Encoding($true)
$macAt = [array]::IndexOf($file.DeviceColumns, 'MacAddress')
$nameAt = [array]::IndexOf($file.DeviceColumns, 'Name')
$ipAt = [array]::IndexOf($file.DeviceColumns, 'IpAddress')

$rows = New-Object System.Collections.Generic.List[string]
$rows.Add((@($file.DeviceColumns | Select-Object -Skip 1 | ForEach-Object { Csv $_ }) -join ','))
foreach ($mac in $file.Order) {
    $camera = $file.Cameras[$mac]
    $cells = @()
    for ($c = 1; $c -lt $file.DeviceColumns.Count; $c++) { $cells += (Csv (Bare $camera.Device[$c])) }
    $rows.Add(($cells -join ','))
}
[IO.File]::WriteAllLines($env:PSREADABLE, $rows, $utf8)

# The markers, the head number and a MacAddress column some CCT builds carry are all replaced by
# the four columns at the front, so a head is found again by MAC and position.
$skip = @('AnalyticsHeader', 'Head', 'MacAddress', '')
$acols = @()
for ($c = 0; $c -lt $file.AnalyticsColumns.Count; $c++) { if ($skip -notcontains $file.AnalyticsColumns[$c]) { $acols += $c } }
$heads = New-Object System.Collections.Generic.List[string]
$heads.Add((@(@('MacAddress', 'Name', 'IpAddress', 'Head') + @($acols | ForEach-Object { $file.AnalyticsColumns[$_] }) | ForEach-Object { Csv $_ }) -join ','))
$headCount = 0
foreach ($mac in $file.Order) {
    $camera = $file.Cameras[$mac]
    for ($h = 0; $h -lt $camera.Analytics.Count; $h++) {
        $headCount++
        $cells = @((Csv $camera.Device[$macAt]), (Csv (Bare $camera.Device[$nameAt])), (Csv (Bare $camera.Device[$ipAt])), ('' + ($h + 1)))
        foreach ($c in $acols) { $cells += (Csv (Word $file.AnalyticsColumns[$c] $camera.Analytics[$h][$c])) }
        $heads.Add(($cells -join ','))
    }
}
[IO.File]::WriteAllLines($env:PSANALYTICS, $heads, $utf8)
Write-Output ('' + $file.Order.Count + '|' + $headCount)
###ENDREADABLE###
