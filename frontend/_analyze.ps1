$ErrorActionPreference = "Continue"
Write-Output "=== DIST FILES ==="
Get-ChildItem -Recurse "C:\Users\hman\Desktop\games\frontend\dist" | ForEach-Object {
  "{0,12}  {1}" -f $_.Length, $_.FullName
}
Write-Output "=== SELECT-STRING ==="
Select-String -Path "C:\Users\hman\Desktop\games\frontend\dist\assets\*.js" -Pattern "Worker|ai\.worker|chooseAiMoveAsync|searchBestMove|MATE_SCORE|100000" | ForEach-Object {
  $line = $_.Line
  if ($line.Length -gt 180) { $line = $line.Substring(0, 180) }
  "{0}:{1}:{2}" -f $_.Filename, $_.LineNumber, $line
}
Write-Output "=== FINDSTR Worker ==="
cmd /c "findstr /i /n /c:Worker /c:ai.worker /c:chooseAiMoveAsync /c:searchBestMove /c:MATE_SCORE C:\Users\hman\Desktop\games\frontend\dist\assets\*.js"
Write-Output "=== AI FILES ==="
Get-ChildItem -Recurse "C:\Users\hman\Desktop\games\frontend\src" -File | Where-Object { $_.Name -match "aiClient|worker|ai\.ts" } | ForEach-Object { $_.FullName }
