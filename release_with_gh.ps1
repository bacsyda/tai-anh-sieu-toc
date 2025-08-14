param(
  [Parameter(Mandatory=$true)] [string]$Version,
  [string]$Owner = "bacsyda",
  [string]$Repo  = "tai-anh-sieu-toc"
)

$ErrorActionPreference = "Stop"
# --- Auto-bump __version__ trong image_downloader_app.py ---
$src = Join-Path $PWD "image_downloader_app.py"
(Get-Content $src -Raw) `
  -replace '__version__\s*=\s*["''][^"'']+["'']', "__version__ = `"$Version`"" `
  | Set-Content -Encoding UTF8 $src

# 1) Build
pip install --upgrade pyinstaller | Out-Null
pyinstaller --onefile --windowed --collect-all PySide6 --name "TaiAnhSieuToc" image_downloader_app.py

# 2) SHA256
$exe = Join-Path -Path (Join-Path -Path $PWD -ChildPath "dist") -ChildPath "TaiAnhSieuToc.exe"
if (!(Test-Path $exe)) { throw "Không tìm thấy $exe" }
$sha = (Get-FileHash -Path $exe -Algorithm SHA256).Hash

# 3) Commit/Pull/Push
git add -A
if ((git status --porcelain).Length -gt 0) {
  git commit -m "chore: release $Version"
}
git fetch origin
git pull --rebase --autostash origin main
git push

# 4) Tạo release + upload .exe
gh release create "v$Version" $exe `
  --title "Tải ảnh siêu tốc $Version" `
  --notes "Phát hành $Version" `
  --latest

# 5) Cập nhật manifest JSON
$url = "https://github.com/$Owner/$Repo/releases/download/v$Version/TaiAnhSieuToc.exe"
$manifest = @"
{
  "version": "$Version",
  "windows": { "url": "$url", "sha256": "$sha" },
  "notes":  "Phát hành $Version"
}
"@
$pub = Join-Path $PWD "public\tai_anh_sieu_toc.json"
$pub = ".\public\tai_anh_sieu_toc.json"
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)
[System.IO.File]::WriteAllText((Resolve-Path $pub), $manifest, $utf8NoBom)


git add $pub
git commit -m "chore: manifest $Version"
git push

Write-Host "✅ Xong! Manifest: $pub"
Write-Host "   URL: $url"
Write-Host "   SHA256: $sha"
