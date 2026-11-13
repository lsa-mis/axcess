# Builds axcess-ai-launcher.exe, the Windows sandbox launcher for Axcess's
# private AI service (axcess_ai_launcher.c), with Microsoft's C compiler.
#
#   powershell -File desktop/ai-launcher/build.ps1 -Output desktop/llama-runtime/axcess-ai-launcher.exe
#
# Finds Visual Studio's C++ tools with vswhere when cl.exe is not already on
# PATH. Warnings are errors (/W4 /WX). The C runtime is linked statically
# (/MT), so the launcher needs no Visual C++ runtime DLL inside the sandbox.
param(
    [Parameter(Mandatory = $true)][string]$Output
)

$ErrorActionPreference = "Stop"

$source = Join-Path $PSScriptRoot "axcess_ai_launcher.c"
$outputPath = [System.IO.Path]::GetFullPath($Output)

if (-not (Get-Command cl.exe -ErrorAction SilentlyContinue)) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} "Microsoft Visual Studio\Installer\vswhere.exe"
    if (-not (Test-Path $vswhere)) { throw "Visual Studio is not installed (no vswhere.exe)." }
    $vs = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
    if (-not $vs) { throw "Visual Studio's C++ tools (x64) are not installed." }
    Import-Module (Join-Path $vs "Common7\Tools\Microsoft.VisualStudio.DevShell.dll")
    Enter-VsDevShell -VsInstallPath $vs -SkipAutomaticLocation -DevCmdArguments "-arch=x64 -host_arch=x64" | Out-Null
}

$objects = Join-Path ([System.IO.Path]::GetTempPath()) "axcess-ai-launcher-build-$PID"
New-Item -ItemType Directory -Force -Path $objects | Out-Null
New-Item -ItemType Directory -Force -Path (Split-Path -Parent $outputPath) | Out-Null

Push-Location $objects
try {
    & cl.exe /nologo /W4 /WX /O2 /MT /GS /guard:cf /DUNICODE /D_UNICODE $source "/Fe$outputPath" `
        /link /DYNAMICBASE /NXCOMPAT /GUARD:CF userenv.lib advapi32.lib ws2_32.lib iphlpapi.lib
    if ($LASTEXITCODE -ne 0) { throw "cl.exe failed with exit code $LASTEXITCODE." }
} finally {
    Pop-Location
    Remove-Item -Recurse -Force $objects -ErrorAction SilentlyContinue
}

Write-Host "Built $outputPath"
