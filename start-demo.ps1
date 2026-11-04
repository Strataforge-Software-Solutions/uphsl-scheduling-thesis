# Starts the backend (Django) and the frontend (npm start) in two windows.
# Run from the project folder:   .\start-demo.ps1
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$activate = Join-Path $root "backend\venv\Scripts\Activate.ps1"
$venv = ""
if (Test-Path $activate) { $venv = "& '$activate'; " }
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\backend'; $venv python manage.py runserver"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm start"
Write-Host "Backend: http://127.0.0.1:8000   Frontend: http://localhost:3000 (opens in your browser)"
