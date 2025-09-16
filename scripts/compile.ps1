<#
.SYNOPSIS
  MPY-Cross PicoCore AUTOCOMPILER (with .version checks)
  Defaults:
    Source = ../src/core  (relative to script)
    Output = ../build/core (relative to script)
#>

param(
    [string]$Source = (Join-Path -Path (Split-Path -Path $PSCommandPath -Parent) -ChildPath "..\src\core"), # default source path change as needed
    [string]$Output = (Join-Path -Path (Split-Path -Path $PSCommandPath -Parent) -ChildPath "..\build\core") # default output path change as needed
)

Set-StrictMode -Version Latest

function Ensure-Dir {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        New-Item -ItemType Directory -Path $Path -Force | Out-Null
    }
}

function Ask-Continue {
    param([string]$Message)
    $resp = Read-Host "$Message (y/n)"
    if ($resp -ne 'y') {
        Write-Host "Aborting." -ForegroundColor Yellow
        exit 1
    }
}

function Get-MpyCrossVersion {
    try {
        $out = & python -m mpy_cross --version 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        if ($out -match '([\d]+\.[\d]+(?:\.[\d]+)?)') { return $matches[1] }
        return $out.Trim()
    } catch { return $null }
}

function Install-MpyCross {
    param([string]$Version)
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Error "Python not available to install mpy-cross."
        exit 1
    }
    if ($Version) {
        & python -m pip install "mpy-cross==$Version" 2>&1 | ForEach-Object { Write-Output $_ }
    } else {
        & python -m pip install mpy-cross 2>&1 | ForEach-Object { Write-Output $_ }
    }
    if ($LASTEXITCODE -ne 0) {
        Write-Error "mpy-cross installation failed."
        exit 1
    }
}

function Get-ProjectVersions {
    param([string]$ProjectPath)
    $version_file = Join-Path $ProjectPath ".version"
    if (Test-Path $version_file) {
        $lines = Get-Content $version_file | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
        if ($lines.Count -ge 2) {
            return [PSCustomObject]@{
                core        = $lines[0]
                micropython = $lines[1]
            }
        } else {
            Write-Warning ".version exists but does not contain 2 lines (core / micropython): $version_file"
            return $null
        }
    } else {
        return $null
    }
}

function Compare-Versions {
    param($SourceVersions, $OutputVersions)
    if ($null -eq $SourceVersions -or $null -eq $OutputVersions) { return }
    if ($SourceVersions.core -eq $OutputVersions.core) {
        Write-Warning "Same PicoCore version in source and output: $($SourceVersions.core)"
        Write-Warning "This may mean nothing changed (no new features/fixes compiled)."
    }
}

function Check-MpyCrossCompatibility {
    param([string]$MpyCrossVersion, [string]$MicroPythonVersion)
    if (-not $MpyCrossVersion -or -not $MicroPythonVersion) { return }

    $mpParts = @($MpyCrossVersion -split '\.')
    $mp = if ($mpParts.Count -ge 2) { "$($mpParts[0]).$($mpParts[1])" } else { $mpParts[0] }

    $pyParts = @($MicroPythonVersion -split '\.')
    $mpy = if ($pyParts.Count -ge 2) { "$($pyParts[0]).$($pyParts[1])" } else { $pyParts[0] }

    if ($mp -ne $mpy) {
        Write-Warning "mpy-cross version ($MpyCrossVersion) != MicroPython version in .version ($MicroPythonVersion)."
        Ask-Continue "Continue despite version mismatch?"
    }
}

function Compile-ToMpy {
    param(
        [Parameter(Mandatory)][string]$SourceFile,
        [Parameter(Mandatory)][string]$DestMpy
    )

    $tmpDir = Join-Path ([System.IO.Path]::GetTempPath()) ([System.Guid]::NewGuid().ToString())
    Ensure-Dir $tmpDir
    try {
        $fileName = [System.IO.Path]::GetFileName($SourceFile)
        $tmpSrc = Join-Path $tmpDir $fileName
        Copy-Item -Path $SourceFile -Destination $tmpSrc -Force

        Push-Location $tmpDir
        try {
            & python -m mpy_cross $fileName 2>&1 | ForEach-Object { Write-Output $_ }
            if ($LASTEXITCODE -ne 0) {
                Write-Warning "mpy-cross failed for $SourceFile"
                return $false
            }

            $base = [System.IO.Path]::GetFileNameWithoutExtension($fileName)
            $tmpMpy = Join-Path $tmpDir ("$base.mpy")
            if (-not (Test-Path $tmpMpy)) {
                $found = Get-ChildItem -Path $tmpDir -Filter "*.mpy" -File | Select-Object -First 1
                if ($found) { $tmpMpy = $found.FullName } else {
                    Write-Warning "No .mpy produced for $SourceFile"
                    return $false
                }
            }

            Ensure-Dir (Split-Path -Path $DestMpy -Parent)
            Copy-Item -Path $tmpMpy -Destination $DestMpy -Force
            return $true
        } finally {
            Pop-Location
        }
    } catch {
        Write-Warning "Error compiling $SourceFile : $_"
        return $false
    } finally {
        Remove-Item -Path $tmpDir -Recurse -Force -ErrorAction SilentlyContinue
    }
}

# ---- Main ----
Write-Host "MPY-Cross PicoCore AUTOCOMPILER (with .version checks)" -ForegroundColor Cyan

try {
    $srcRoot = (Resolve-Path -Path $Source -ErrorAction Stop).Path
} catch {
    Write-Error "Source path not found: $Source"
    exit 1
}

if (-not (Test-Path $Output)) { Ensure-Dir $Output }
$dstRoot = (Resolve-Path -Path $Output -ErrorAction SilentlyContinue).Path
if (-not $dstRoot) { Ensure-Dir $Output; $dstRoot = (Resolve-Path $Output).Path }

Write-Host "Source: $srcRoot"
Write-Host "Output: $dstRoot"

# python + mpy-cross checks
if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python not found in PATH. Install Python and try again."
    exit 1
}

$mpyCrossVersion = Get-MpyCrossVersion
if (-not $mpyCrossVersion) {
    Write-Warning "mpy-cross not found."
    $install = Read-Host "Attempt to install mpy-cross via pip now? (y/n)"
    if ($install -eq 'y') {
        Install-MpyCross $null
        $mpyCrossVersion = Get-MpyCrossVersion
        if (-not $mpyCrossVersion) { Write-Error "mpy-cross still not available. Aborting."; exit 1 }
    } else {
        Write-Error "mpy-cross is required. Install with: python -m pip install mpy-cross"
        exit 1
    }
}

Write-Host "Detected mpy-cross version: $mpyCrossVersion"

# Read project .version files
$project_source_versions = Get-ProjectVersions -ProjectPath $srcRoot
$project_output_versions = Get-ProjectVersions -ProjectPath $dstRoot

Write-Host "Project Source versions:"
if ($project_source_versions) { $project_source_versions | Format-List | Out-String | Write-Output } else { Write-Host "  (none)" }

Write-Host "Project Output versions:"
if ($project_output_versions) { $project_output_versions | Format-List | Out-String | Write-Output } else { Write-Host "  (none)" }

if ($project_source_versions) {
    Check-MpyCrossCompatibility -MpyCrossVersion $mpyCrossVersion -MicroPythonVersion $project_source_versions.micropython
}
Compare-Versions -SourceVersions $project_source_versions -OutputVersions $project_output_versions

Ask-Continue "Do you want to compile now?"

# Gather files
$pyFiles = @(Get-ChildItem -Path $srcRoot -Recurse -File -Include *.py)
$otherFiles = @(Get-ChildItem -Path $srcRoot -Recurse -File | Where-Object { $_.Extension -ne ".py" })

Write-Host "Found $($pyFiles.Count) .py files and $($otherFiles.Count) other files."

$processed = 0

foreach ($file in $pyFiles) {
    $relative = $file.FullName.Substring($srcRoot.Length).TrimStart('\','/')
    $destRelative = [System.IO.Path]::ChangeExtension($relative, ".mpy")
    $destPath = Join-Path $dstRoot $destRelative

    Write-Host "Compiling: $relative -> $destRelative"
    $ok = Compile-ToMpy -SourceFile $file.FullName -DestMpy $destPath
    if (-not $ok) { Write-Warning "Failed: $relative" }
    $processed++
}

foreach ($f in $otherFiles) {
    $relative = $f.FullName.Substring($srcRoot.Length).TrimStart('\','/')
    $destPath = Join-Path $dstRoot $relative
    Ensure-Dir (Split-Path -Path $destPath -Parent)

    Copy-Item -Path $f.FullName -Destination $destPath -Force
    Write-Host "Copied: $relative"
    $processed++
}

Write-Host "Done. Processed approx. $processed files. Output in: $dstRoot" -ForegroundColor Green
