param([ValidateSet('setup','build','demo','test','all')][string]$Action='demo')
$ErrorActionPreference='Stop'
Push-Location $PSScriptRoot
try {
 if ($Action -eq 'setup') {
  if (-not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Install Node.js with npm, then reopen VS Code.' }
  if (Test-Path package-lock.json) { & npm.cmd ci --no-audit --no-fund } else { & npm.cmd install --no-audit --no-fund }
  if ($LASTEXITCODE -ne 0) { throw 'OCR dependency setup failed' }
  Write-Host 'Setup complete. Choose Run demo or Run 8 tests.'
  return
 }
 if (-not (Get-Command java -ErrorAction SilentlyContinue)) { throw 'Java 8 or newer must be on PATH.' }
 New-Item -ItemType Directory -Force build | Out-Null
 $sources=Get-ChildItem src/*.java | ForEach-Object FullName
 & java -jar lib/ecj-3.26.0.jar -1.8 -encoding UTF-8 -cp lib/jsoup-1.17.2.jar -d build $sources
 if ($LASTEXITCODE -ne 0) { throw 'Java compilation failed' }
 if ($Action -eq 'build') { Write-Host 'Build successful'; return }
 if (-not (Test-Path node_modules/tesseract.js)) { throw 'Run the Setup OCR dependencies task first.' }
 $node=(Get-Command node -ErrorAction Stop).Source
 if ($Action -in @('test','all')) {
  & java -cp 'build;lib/jsoup-1.17.2.jar' StrategyTests $node
  if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
 }
 if ($Action -in @('demo','all')) {
  & java -cp 'build;lib/jsoup-1.17.2.jar' Demo $node
  if ($LASTEXITCODE -ne 0) { throw 'Demo failed' }
 }
} finally { Pop-Location }
