Write-Output "=== SearchCtx interface ==="
Get-Content "C:\Users\hman\Desktop\games\frontend\src\games\dama\ai.ts" | Select-Object -Skip 398 -First 25
Write-Output "=== ctx init ==="
Get-Content "C:\Users\hman\Desktop\games\frontend\src\games\dama\ai.ts" | Select-Object -Skip 630 -First 25
Write-Output "=== who imports aiClient ==="
cmd /c "findstr /s /i /n /c:aiClient /c:chooseAiMoveAsync C:\Users\hman\Desktop\games\frontend\src\*.ts C:\Users\hman\Desktop\games\frontend\src\*.tsx C:\Users\hman\Desktop\games\frontend\src\*\*.ts C:\Users\hman\Desktop\games\frontend\src\*\*.tsx C:\Users\hman\Desktop\games\frontend\src\*\*\*.ts C:\Users\hman\Desktop\games\frontend\src\*\*\*.tsx C:\Users\hman\Desktop\games\frontend\src\*\*\*\*.ts C:\Users\hman\Desktop\games\frontend\src\*\*\*\*.tsx"
Write-Output "=== DamaGame usage ==="
cmd /c "findstr /s /i /n DamaGame C:\Users\hman\Desktop\games\frontend\src\*.tsx C:\Users\hman\Desktop\games\frontend\src\*\*.tsx C:\Users\hman\Desktop\games\frontend\src\*\*\*.tsx"
