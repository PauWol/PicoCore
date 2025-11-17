function Test-PythonInstalled {
    param()
    return (Get-Command python -ErrorAction SilentlyContinue) -ne $null
}

function Test-PythonModulesInstalled {
    param([string[]]$Modules)
    foreach ($module in $Modules) {
        if (-not (Get-Command "python -m pip list $module" -ErrorAction SilentlyContinue)) {
            return $false
        }
    }
    return $true
}

function Install-PythonModules {
    param([string[]]$Modules)
    if (-not (Test-PythonInstalled)) {
        Write-Error "Python not installed. Please install Python and try again."
        exit 1
    }
    foreach ($module in $Modules) {
        if (-not (Test-PythonModulesInstalled $module)) {
            Write-Host "Installing $module"
            & python -m pip install $module 2>&1 | ForEach-Object { Write-Output $_ }
        }
    }
}


if (-not (Test-PythonInstalled)) {
    Write-Error "Python is not installed. Please install Python to proceed."
    exit 1
}

$requiredModules = @( "mypy", "pylint")

Install-PythonModules -Modules $requiredModules
$allModulesInstalled = $true
foreach ($module in $requiredModules) {
    if (-not (Test-PythonModulesInstalled $module)) {
        Write-Error "$module is not installed even after attempting installation."
        $allModulesInstalled = $false
    }
}

if ($allModulesInstalled) {
    Write-Host "All required modules are installed." -ForegroundColor Green
} else {
    Write-Error "Some required modules are still missing. Please check the errors above."
    exit 1
}