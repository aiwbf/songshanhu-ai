param(
  [string]$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path,
  [string]$Out = (Join-Path (Join-Path $PSScriptRoot "..") "data\\generated\\knowledge_bundle.json"),
  [string]$ReferenceDate = "2026-03-08"
)

python (Join-Path $PSScriptRoot "import_sources.py") --root $Root --out $Out --reference-date $ReferenceDate
