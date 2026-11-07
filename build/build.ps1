param([switch]$Console)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

python -m pip install -r requirements-build.txt

$mode = if ($Console) { "--console" } else { "--windowed" }

python -m PyInstaller `
  --noconfirm --clean --onedir `
  --name SocialClubChatExporter `
  --specpath build `
  --workpath build/work `
  --distpath dist `
  $mode `
  --add-data "$root\socialclub_exporter\resources\chat_template.html;resources" `
  --collect-all mitmproxy `
  --collect-all mitmproxy_rs `
  --collect-all mitmproxy_windows `
  run_exporter.py
