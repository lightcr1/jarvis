# J.A.R.V.I.S. Windows Startup Client
# Adds JARVIS to Windows startup so it opens automatically when you log in.
# Run once in PowerShell as your normal user (no admin needed).
#
# Usage:
#   1. Open PowerShell
#   2. Run: powershell -ExecutionPolicy Bypass -File install_client_windows.ps1 -JarvisUrl "https://100.x.x.x"
#
# Where 100.x.x.x is your JARVIS server's Tailscale IP (or local IP).

param(
    [Parameter(Mandatory=$true)]
    [string]$JarvisUrl,

    [string]$Browser = "auto",       # auto, chrome, edge, firefox
    [switch]$RemoveStartup           # pass -RemoveStartup to uninstall
)

$ErrorActionPreference = "Stop"

$StartupFolder = [System.Environment]::GetFolderPath("Startup")
$ShortcutPath  = Join-Path $StartupFolder "JARVIS.lnk"
$TaskName      = "JARVIS-Startup"

function Write-J { param($msg) Write-Host "[jarvis] $msg" -ForegroundColor Cyan }

# --- Remove mode ---
if ($RemoveStartup) {
    if (Test-Path $ShortcutPath) { Remove-Item $ShortcutPath -Force; Write-J "Removed startup shortcut." }
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false; Write-J "Removed scheduled task."
    }
    Write-J "JARVIS startup removed."
    exit 0
}

# --- Detect browser ---
function Find-Browser {
    $candidates = @(
        @{ Name="chrome";  Exe="chrome.exe";    Paths=@("${env:ProgramFiles}\Google\Chrome\Application","${env:ProgramFiles(x86)}\Google\Chrome\Application","${env:LOCALAPPDATA}\Google\Chrome\Application") },
        @{ Name="msedge";  Exe="msedge.exe";    Paths=@("${env:ProgramFiles(x86)}\Microsoft\Edge\Application","${env:ProgramFiles}\Microsoft\Edge\Application") },
        @{ Name="firefox"; Exe="firefox.exe";   Paths=@("${env:ProgramFiles}\Mozilla Firefox","${env:ProgramFiles(x86)}\Mozilla Firefox") }
    )
    foreach ($b in $candidates) {
        foreach ($p in $b.Paths) {
            $full = Join-Path $p $b.Exe
            if (Test-Path $full) { return $full }
        }
    }
    return $null
}

$BrowserExe = if ($Browser -eq "auto") { Find-Browser } else {
    @{ chrome="chrome.exe"; edge="msedge.exe"; firefox="firefox.exe" }[$Browser]
}

if (-not $BrowserExe -or -not (Test-Path $BrowserExe)) {
    Write-J "Browser not found. Installing startup shortcut to open default browser..."
    $BrowserExe = $null
}

# --- Create startup shortcut ---
Write-J "Creating startup shortcut in: $StartupFolder"

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)

if ($BrowserExe) {
    # Chrome/Edge support app mode (no browser chrome, feels like a native app)
    $isChromium = $BrowserExe -match "chrome|edge"
    if ($isChromium) {
        $Shortcut.TargetPath  = $BrowserExe
        $Shortcut.Arguments   = "--app=$JarvisUrl --window-size=1200,800"
    } else {
        $Shortcut.TargetPath  = $BrowserExe
        $Shortcut.Arguments   = $JarvisUrl
    }
} else {
    # Fallback: open via default browser
    $Shortcut.TargetPath = "explorer.exe"
    $Shortcut.Arguments  = $JarvisUrl
}

$Shortcut.Description   = "J.A.R.V.I.S. Assistant"
$Shortcut.WindowStyle   = 1  # Normal window
$Shortcut.Save()

Write-J "Shortcut created: $ShortcutPath"

# --- Summary ---
Write-J ""
Write-J "======================================================"
Write-J "JARVIS will now open automatically at every login."
Write-J ""
Write-J "URL: $JarvisUrl"
if ($BrowserExe) { Write-J "Browser: $BrowserExe" }
Write-J ""
Write-J "To install as a home-screen app (recommended):"
Write-J "  Chrome/Edge: open $JarvisUrl, then click the install"
Write-J "  icon in the address bar (looks like a monitor + arrow)"
Write-J ""
Write-J "To remove from startup:"
Write-J "  powershell -File install_client_windows.ps1 -JarvisUrl '$JarvisUrl' -RemoveStartup"
Write-J "======================================================"
