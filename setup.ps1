$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root 'backend'
$frontend = Join-Path $root 'frontend'
$venvPython = Join-Path $backend '.venv\Scripts\python.exe'
$modelDir = Join-Path $backend 'models'
$modelPath = Join-Path $modelDir 'face_landmarker.task'

Push-Location $backend
try {
    if (-not (Test-Path -LiteralPath $venvPython)) {
        py -3.12 -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python 3.12 was not found. Install it, then rerun setup.ps1.' }
    }
    & $venvPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Backend dependency installation failed.' }
    if (-not (Test-Path -LiteralPath (Join-Path $backend '.env'))) {
        Copy-Item -LiteralPath (Join-Path $backend '.env.example') -Destination (Join-Path $backend '.env')
    }
}
finally { Pop-Location }

if (-not (Test-Path -LiteralPath $modelPath)) {
    New-Item -ItemType Directory -Path $modelDir -Force | Out-Null
    Invoke-WebRequest -Uri 'https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task' -OutFile $modelPath
    if ($LASTEXITCODE -ne 0) { throw 'Could not download the MediaPipe face model.' }
}

Push-Location $frontend
try {
    npm install
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
}
finally { Pop-Location }

Write-Host 'Setup complete. In VS Code, run Terminal > Run Task > ProctorAI: Start both.' -ForegroundColor Green
