$ErrorActionPreference = 'Stop'
$quotaRuntimeInstaller = Join-Path $env:RUNNER_TEMP 'WindowsAppRuntimeInstall-2.6.5-x64.exe'
Invoke-WebRequest -Uri 'https://aka.ms/windowsappsdk/2.6/2.6.5/windowsappruntimeinstall-x64.exe' -OutFile $quotaRuntimeInstaller
$quotaRuntimeSignature = Get-AuthenticodeSignature -LiteralPath $quotaRuntimeInstaller
if ($quotaRuntimeSignature.Status -ne 'Valid' -or $quotaRuntimeSignature.SignerCertificate.Subject -notlike '*Microsoft Corporation*') {
  throw 'The official Windows App Runtime installer signature could not be verified'
}
$quotaRuntimeProcess = Start-Process -FilePath $quotaRuntimeInstaller -ArgumentList @('--quiet') -WindowStyle Hidden -Wait -PassThru
if ($quotaRuntimeProcess.ExitCode -ne 0) { throw ('Windows App Runtime installation failed: ' + $quotaRuntimeProcess.ExitCode) }
python -c "import win32more.appsdk; win32more.appsdk.initialize(); print('Windows App Runtime initialized successfully')"
if ($LASTEXITCODE -ne 0) { throw 'Windows App Runtime failed initialization after installation' }
