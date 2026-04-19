# Set password hash across all three apps
# Run this after generate_hash.py to update .env files

$hash = Read-Host "Paste your password hash"

$envFiles = @(
    "C:\Users\james\src\excercise-tracker\.env",
    "C:\Users\james\src\weight-tracker\.env",
    "C:\Users\james\src\pullup-calculator\.env"
)

foreach ($file in $envFiles) {
    if (Test-Path $file) {
        $content = Get-Content $file -Raw
        if ($content -match '(?m)^TIMELINE_PASSWORD=.*$') {
            $content = $content -replace '(?m)^TIMELINE_PASSWORD=.*$', "TIMELINE_PASSWORD=$hash"
        } else {
            $content = $content.TrimEnd() + "`nTIMELINE_PASSWORD=$hash`n"
        }
        Set-Content $file $content -NoNewline
        Write-Host "Updated: $file" -ForegroundColor Green
    } else {
        Write-Host "Skipped (not found): $file" -ForegroundColor Yellow
    }
}

Write-Host ""
Write-Host "Local .env files updated!" -ForegroundColor Cyan
Write-Host "Remember to also update TIMELINE_PASSWORD on Render for all three services." -ForegroundColor Yellow
