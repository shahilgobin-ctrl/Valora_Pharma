param(
    [string]$Address = "127.0.0.1:8000"
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$requirements = Join-Path $projectRoot "requirements.txt"
$managePy = Join-Path $projectRoot "backend\manage.py"
$versionCheck = 'import sys; raise SystemExit(0 if (3, 10) <= sys.version_info[:2] < (3, 15) else 1)'

function Invoke-PythonStep {
    param([string[]]$Arguments)
    & $venvPython @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Python could not finish this step: $($Arguments -join ' ')"
    }
}

Push-Location -LiteralPath $projectRoot
try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        $chosenCommand = $null
        $chosenArguments = @()
        $candidates = @(
            @{ Name = "py"; Arguments = @("-3") },
            @{ Name = "python3"; Arguments = @() },
            @{ Name = "python"; Arguments = @() }
        )
        foreach ($candidate in $candidates) {
            $command = Get-Command -Name $candidate.Name -ErrorAction SilentlyContinue
            if ($null -eq $command) { continue }
            $candidateArguments = $candidate.Arguments
            try {
                & $command.Source @candidateArguments -c $versionCheck *> $null
                if ($LASTEXITCODE -eq 0) {
                    $chosenCommand = $command.Source
                    $chosenArguments = $candidateArguments
                    break
                }
            } catch {
                # A launcher without an installed runtime may fail; try the next one.
            }
        }
        if ($null -eq $chosenCommand) {
            throw "Install Python 3.10 through 3.14 from https://www.python.org/downloads/ and run this script again. The py launcher alone is not a Python installation."
        }
        Write-Host "Creating your local Python environment..."
        & $chosenCommand @chosenArguments -m venv (Join-Path $projectRoot ".venv")
        if ($LASTEXITCODE -ne 0) { throw "The Python environment could not be created." }
    }

    & $venvPython -c $versionCheck
    if ($LASTEXITCODE -ne 0) {
        throw "This .venv needs Python 3.10 through 3.14. Recreate it with a supported Python version."
    }
    Write-Host "Installing the project dependencies..."
    Invoke-PythonStep -Arguments @("-m", "pip", "install", "-r", $requirements)
    Write-Host "Preparing the local database..."
    Invoke-PythonStep -Arguments @($managePy, "migrate", "--noinput")
    Write-Host ""
    Write-Host "Open http://$Address/login/ in your browser."
    Write-Host "Keep this window open. Press Ctrl+C to stop the server."
    Invoke-PythonStep -Arguments @($managePy, "runserver", $Address)
} finally {
    Pop-Location
}
