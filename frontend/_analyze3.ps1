Write-Output "=== IMPORTS OF aiClient ==="
Select-String -Path "C:\Users\hman\Desktop\games\frontend\src\**\*.{ts,tsx}" -Pattern "aiClient|chooseAiMoveAsync|ai\.worker" | ForEach-Object { "{0}:{1}:{2}" -f $_.Path, $_.LineNumber, $_.Line.Trim() }
Write-Output "=== DAMA IN APP ==="
Select-String -Path "C:\Users\hman\Desktop\games\frontend\src\**\*.{ts,tsx}" -Pattern "DamaGame|games/dama" | ForEach-Object { "{0}:{1}:{2}" -f $_.RelativePath($_), $_.LineNumber, $_.Line.Trim() }
Write-Output "=== TS ERROR CONTEXT ==="
Get-Content "C:\Users\hman\Desktop\games\frontend\src\games\dama\ai.ts" | Select-Object -Skip 420 -First 40
Write-Output "=== SEARCHCTX ==="
Select-String -Path "C:\Users\hman\Desktop\games\frontend\src\games\dama\ai.ts" -Pattern "SearchCtx|qNodes|MATE_SCORE" | Select-Object -First 30 | ForEach-Object { "{0}:{1}" -f $_.LineNumber, $_.Line.Trim() }
