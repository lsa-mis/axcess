$ErrorActionPreference = "Stop"

$desktopDirectory = Split-Path -Parent $PSScriptRoot
$destination = Join-Path $desktopDirectory "ocr-runtime"
$candidateRoots = @(
    $env:TESSERACT_ROOT,
    (Join-Path $env:ProgramFiles "Tesseract-OCR"),
    (Join-Path ${env:ProgramFiles(x86)} "Tesseract-OCR")
) | Where-Object { $_ }

$command = Get-Command tesseract.exe -ErrorAction SilentlyContinue
if ($command) {
    $candidateRoots = @((Split-Path -Parent $command.Source)) + $candidateRoots
}

$source = $candidateRoots |
    Where-Object { Test-Path (Join-Path $_ "tesseract.exe") } |
    Select-Object -First 1

if (-not $source) {
    throw "Tesseract is required to build the Windows desktop app (choco install tesseract)."
}

$sourceTessdata = Join-Path $source "tessdata"
if (-not (Test-Path (Join-Path $sourceTessdata "eng.traineddata"))) {
    throw "Tesseract English language data is missing from $sourceTessdata."
}

if (Test-Path $destination) {
    Remove-Item $destination -Recurse -Force
}

$binaryDestination = Join-Path $destination "bin"
$shareDestination = Join-Path $destination "share"
New-Item $binaryDestination -ItemType Directory -Force | Out-Null
New-Item $shareDestination -ItemType Directory -Force | Out-Null

Copy-Item (Join-Path $source "tesseract.exe") $binaryDestination
Get-ChildItem $source -Filter "*.dll" -File | Copy-Item -Destination $binaryDestination
Copy-Item $sourceTessdata $shareDestination -Recurse

$bundledTesseract = Join-Path $binaryDestination "tesseract.exe"
$env:TESSDATA_PREFIX = Join-Path $shareDestination "tessdata"
$env:PATH = "$binaryDestination;$env:PATH"
& $bundledTesseract --version
if ($LASTEXITCODE -ne 0) {
    throw "The bundled Tesseract executable failed its relocation check."
}

Write-Host "Bundled Windows Tesseract runtime at $destination"
