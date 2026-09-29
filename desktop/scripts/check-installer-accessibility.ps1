<#
Scan every screen of the Windows installer and uninstaller with
Axe.Windows, Microsoft's automated accessibility checker for Windows apps,
and fail when it finds an error.

axe-core only reads web pages; the installer is a Windows program, so its
screens are checked through UI Automation, the accessibility tree screen
readers use. The script installs Axcess for the current user and removes
it again, which is why it only runs on a throwaway CI machine:

  1. Setup: who can use Axcess (the install-for choice)
  2. Setup: the folder screen
  3. Setup: the last screen (install folder shown, "Open Axcess now")
  4. Uninstall: the first screen (reports stay)
  5. Uninstall: the last screen

It moves through the wizard by invoking buttons by name through UI
Automation, as assistive technology would, not by clicking positions.
Message boxes (Axcess is open, a file in use) are not reached.

Like axe-core, Axe.Windows finds only what can be detected automatically.
A pass does not mean the installer meets WCAG; the screen-reader check in
docs/internal/releases.md still applies.

  powershell -NoProfile -ExecutionPolicy Bypass -File check-installer-accessibility.ps1 `
    -Installer out\make\nsis\Axcess-0.61-Setup.exe -OutputDirectory out\installer-a11y
#>
param(
  [Parameter(Mandatory = $true)] [string] $Installer,
  [string] $OutputDirectory = "out\installer-a11y"
)

$ErrorActionPreference = "Stop"

# Pinned release and its SHA-256 (the .zip is self-contained: no .NET needed).
$AxeVersion = "2.4.2"
$AxeSha256 = "AECA43F41C89B3FFB1DB84011539E609ECD7CB3BADD6E78FADA2ADA327D10A64"
$AxeUrl = "https://github.com/microsoft/axe-windows/releases/download/v$AxeVersion/AxeWindowsCLI-$AxeVersion.zip"

Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
# The .NET UI Automation client sees NSIS's standard Win32 controls as
# generic panes, with no Invoke or Toggle pattern: it lacks the Win32
# proxies native UI Automation has (registering the managed ones failed on
# the runner). The names are right, so controls are found by name and
# clicked with Win32 messages. Screen readers and Axe.Windows use native UI
# Automation and see the real control types.
$Automation = [System.Windows.Automation.AutomationElement]
$Scope = [System.Windows.Automation.TreeScope]

Add-Type -Namespace Win32 -Name Native -MemberDefinition @"
[DllImport("user32.dll")] public static extern System.IntPtr SendMessage(System.IntPtr hWnd, uint msg, System.IntPtr wParam, System.IntPtr lParam);
"@
$BM_CLICK = 0x00F5
$BM_SETCHECK = 0x00F1

New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$OutputDirectory = (Resolve-Path $OutputDirectory).Path
$work = Join-Path ([System.IO.Path]::GetTempPath()) "axe-windows-$AxeVersion"
$zip = "$work.zip"
Invoke-WebRequest -Uri $AxeUrl -OutFile $zip -UseBasicParsing
$hash = (Get-FileHash -Path $zip -Algorithm SHA256).Hash
if ($hash -ne $AxeSha256) { throw "AxeWindowsCLI-$AxeVersion.zip has SHA-256 $hash, expected $AxeSha256." }
Expand-Archive -Path $zip -DestinationPath $work -Force
$axe = Join-Path $work "AxeWindowsCLI.exe"

function Wait-TopWindow([scriptblock] $Match, [string] $What, [int] $Seconds = 120) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    foreach ($window in $Automation::RootElement.FindAll($Scope::Children, [System.Windows.Automation.Condition]::TrueCondition)) {
      if (& $Match $window) { return $window }
    }
    Start-Sleep -Milliseconds 500
  }
  throw "No $What window after $Seconds seconds."
}

# Found by name alone: the script must not depend on which control type the
# client reports. Axe.Windows judges the control types itself.
function Find-Control($Window, [string] $Name) {
  $condition = [System.Windows.Automation.PropertyCondition]::new($Automation::NameProperty, $Name)
  return $Window.FindFirst($Scope::Descendants, $condition)
}

# Wait until one of the named buttons is on screen and enabled; return it.
function Wait-Button($Window, [string[]] $Names, [int] $Seconds = 120) {
  $deadline = (Get-Date).AddSeconds($Seconds)
  while ((Get-Date) -lt $deadline) {
    foreach ($name in $Names) {
      $button = Find-Control $Window $name
      # Not IsOffscreen: on a CI desktop nobody watches, Windows can report
      # every control as off screen.
      if ($button -and $button.Current.IsEnabled) { return $button }
    }
    Start-Sleep -Milliseconds 500
  }
  Write-Host "Window '$($Window.Current.Name)' (class $($Window.Current.ClassName)) holds:"
  foreach ($element in $Window.FindAll($Scope::Descendants, [System.Windows.Automation.Condition]::TrueCondition)) {
    $c = $element.Current
    Write-Host "  $($c.ControlType.ProgrammaticName) '$($c.Name)' enabled=$($c.IsEnabled) offscreen=$($c.IsOffscreen)"
  }
  throw "None of the buttons '$($Names -join "', '")' appeared within $Seconds seconds."
}

function Invoke-Button($Button) {
  $invoke = $null
  if ($Button.TryGetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern, [ref] $invoke)) {
    $invoke.Invoke()
  } else {
    [Win32.Native]::SendMessage([System.IntPtr] $Button.Current.NativeWindowHandle, $BM_CLICK, [System.IntPtr]::Zero, [System.IntPtr]::Zero) | Out-Null
  }
}

$script:failures = @()
function Invoke-Scan($Window, [string] $Screen) {
  Start-Sleep -Seconds 1  # let the page finish drawing
  $processId = $Window.Current.ProcessId
  $handle = $Window.Current.NativeWindowHandle
  Write-Host "::group::Axe.Windows: $Screen (process $processId, window $handle)"
  $output = & $axe --processid $processId --scanrootwindowhandle $handle --scanid $Screen `
    --outputdirectory $OutputDirectory --alwayssavetestfile --verbosity verbose 2>&1
  $code = $LASTEXITCODE
  $output | ForEach-Object { Write-Host "  $_" }
  if ($code -eq 2) {
    # Could not complete with the window handle: scan the whole process.
    Write-Host "Scan by window failed (exit 2); scanning process $processId instead."
    $output = & $axe --processid $processId --scanid $Screen `
      --outputdirectory $OutputDirectory --alwayssavetestfile --verbosity verbose 2>&1
    $code = $LASTEXITCODE
    $output | ForEach-Object { Write-Host "  $_" }
  }
  Write-Host "::endgroup::"
  switch ($code) {
    0 { Write-Host "$Screen`: no errors found" }
    1 { $script:failures += $Screen; Write-Host "::error::Axe.Windows found errors on the installer screen '$Screen'." }
    default { throw "Axe.Windows could not scan '$Screen' (exit code $code)." }
  }
}

# Install
$setup = Start-Process -FilePath (Resolve-Path $Installer).Path -PassThru
$window = Wait-TopWindow { param($w) $w.Current.ProcessId -eq $setup.Id } "setup"
$next = Wait-Button $window @("Next >")
Invoke-Scan $window "setup-1-who-can-use-axcess"
Invoke-Button $next

$install = Wait-Button $window @("Install")
Invoke-Scan $window "setup-2-folder"
Invoke-Button $install

$finish = Wait-Button $window @("Finish") 600
Invoke-Scan $window "setup-3-installed"
# Do not start Axcess: its backend would still be running at uninstall.
$open = Find-Control $window "Open Axcess now"
if ($open) {
  $toggle = $null
  if ($open.TryGetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern, [ref] $toggle)) {
    if ($toggle.Current.ToggleState -eq [System.Windows.Automation.ToggleState]::On) { $toggle.Toggle() }
  } else {
    [Win32.Native]::SendMessage([System.IntPtr] $open.Current.NativeWindowHandle, $BM_SETCHECK, [System.IntPtr]::Zero, [System.IntPtr]::Zero) | Out-Null
  }
}
Invoke-Button $finish
if (-not $setup.WaitForExit(60000)) { throw "Setup did not close after Finish." }

# Uninstall. The uninstaller copies itself to a temporary folder and runs
# that copy, so its window is found by title, not by the process started.
$uninstaller = Join-Path $env:LOCALAPPDATA "Programs\Axcess\Uninstall Axcess.exe"
if (-not (Test-Path $uninstaller)) { throw "No uninstaller at ${uninstaller}. Did Setup install for the current user?" }
Start-Process -FilePath $uninstaller | Out-Null
$window = Wait-TopWindow { param($w) $w.Current.Name -like "Axcess Uninstall*" } "uninstall"
$start = Wait-Button $window @("Uninstall", "Next >")
Invoke-Scan $window "uninstall-1-start"
Invoke-Button $start

$finish = Wait-Button $window @("Finish") 300
Invoke-Scan $window "uninstall-2-done"
Invoke-Button $finish

if ($script:failures.Count -gt 0) {
  Write-Host "Axe.Windows found errors on: $($script:failures -join ', '). The .a11ytest files in $OutputDirectory open in Accessibility Insights for Windows."
  exit 1
}
Write-Host "Axe.Windows found no errors on the 5 installer and uninstaller screens."
