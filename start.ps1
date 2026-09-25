$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

# Backend
& "$Root\backend\venv\Scripts\Activate.ps1"
$Backend = Start-Process -NoNewWindow -PassThru -FilePath "$Root\backend\venv\Scripts\uvicorn.exe" -ArgumentList "app.main:app", "--reload" -WorkingDirectory "$Root\backend"

# Frontend
$Frontend = Start-Process -NoNewWindow -PassThru -FilePath "cmd" -ArgumentList "/c npm run dev" -WorkingDirectory "$Root\frontend"

Write-Host ""
Write-Host "  Backend  -> http://localhost:8000"
Write-Host "  Frontend -> http://localhost:3000"
Write-Host ""
Write-Host "  Press Ctrl+C to stop both"
Write-Host ""

try {
    Wait-Process -Id $Backend.Id
} finally {
    Stop-Process -Id $Backend.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $Frontend.Id -Force -ErrorAction SilentlyContinue
}
