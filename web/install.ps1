# Install the Lemmata command-line checker (Windows).
#
#   irm https://lemmata.sous.systems/install.ps1 | iex
#
# What it does, so you can read it before running it:
#   1. uses uv (https://docs.astral.sh/uv/) if you have it, or installs it
#      with Astral's own installer;
#   2. installs the `lemmata` command with `uv tool install`, from the source
#      on GitHub, with its own Python 3.12 -- nothing else on your system is
#      touched;
#   3. runs `lemmata --version` to show it works.
# Running it again upgrades to the newest version.  To remove it:
#   uv tool uninstall aether
#
# $env:LEMMATA_REF picks a branch or tag (default: master).

$ErrorActionPreference = "Stop"

$Repo = "https://github.com/SamuelSmthSmth/lemmata"
$Ref = if ($env:LEMMATA_REF) { $env:LEMMATA_REF } else { "master" }

function Find-Uv {
    $cmd = Get-Command uv -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    foreach ($candidate in @("$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe")) {
        if (Test-Path $candidate) { return $candidate }
    }
    return $null
}

$Uv = Find-Uv
if (-not $Uv) {
    Write-Host "Installing uv, which manages Lemmata's Python for it..."
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression
    $Uv = Find-Uv
    if (-not $Uv) { throw "uv was installed but cannot be found; open a new terminal and run this again" }
}

Write-Host "Installing Lemmata from $Repo ($Ref)..."
& $Uv tool install --force --python 3.12 "git+$Repo@$Ref"
if ($LASTEXITCODE -ne 0) { throw "uv tool install failed" }

$Bin = (& $Uv --color never tool dir --bin)
$Lemmata = Get-Command lemmata -ErrorAction SilentlyContinue
if ($Lemmata) {
    & lemmata --version
} else {
    & (Join-Path $Bin "lemmata.exe") --version
    Write-Host ""
    Write-Host "Add $Bin to your PATH to run lemmata from anywhere:"
    Write-Host "  $Uv tool update-shell"
}
Write-Host ""
Write-Host "Check a proof:  lemmata proof.aether"
Write-Host "Or open the app in your browser: https://lemmata.sous.systems/app/"
