Write-Output "=== JS ASSETS ONLY ==="
Get-ChildItem "C:\Users\hman\Desktop\games\frontend\dist\assets" | ForEach-Object { "{0,12}  {1}" -f $_.Length, $_.Name }
Write-Output "=== TARGETED FINDSTR ==="
foreach ($p in @("new Worker","Worker(","ai.worker","chooseAiMoveAsync","searchBestMove","MATE_SCORE","import.meta.url")) {
  Write-Output "--- pattern: $p ---"
  $r = cmd /c "findstr /i /m /c:`"$p`" C:\Users\hman\Desktop\games\frontend\dist\assets\*.js"
  if ($LASTEXITCODE -eq 0) { $r } else { "(no matches)" }
}
Write-Output "=== COUNT Worker substring ==="
cmd /c "findstr /i /o /c:Worker C:\Users\hman\Desktop\games\frontend\dist\assets\*.js" | Select-Object -First 5
Write-Output "=== AICLIENT CONTENT ==="
Get-Content "C:\Users\hman\Desktop\games\frontend\src\games\dama\aiClient.ts"
Write-Output "=== AI.WORKER HEAD ==="
Get-Content "C:\Users\hman\Desktop\games\frontend\src\games\dama\ai.worker.ts" -TotalCount 40
