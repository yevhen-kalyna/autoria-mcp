# phase1_probes.ps1 — PowerShell port of the Phase-1 probes.
# Closes the 4 remaining OPEN-QUESTIONS (B1 headers, B2 error envelope,
# E2 period enum, E6 unlisted VIN). Uses curl.exe (Windows 10 1803+).
#
# Run:
#   cd "C:\Users\Yevhen\Documents\Claude\Projects\AutoRia MCP"
#   $env:AUTORIA_API_KEY="..."
#   $env:AUTORIA_USER_ID="..."
#   powershell -ExecutionPolicy Bypass -File scripts\phase1_probes.ps1
#
# Output: probe_responses\*.headers.txt and *.body.json

$ErrorActionPreference = "Stop"
$BASE = "https://developers.ria.com"
$KEY  = $env:AUTORIA_API_KEY
$UID  = $env:AUTORIA_USER_ID
$OUT  = "probe_responses"
New-Item -ItemType Directory -Force -Path $OUT | Out-Null

if (-not $KEY) { Write-Error "Set `$env:AUTORIA_API_KEY first"; exit 1 }

function Get-Probe([string]$label, [string]$url) {
    Write-Host "==> [$label] GET $url"
    curl.exe -sS -g `
        -D "$OUT\$label.headers.txt" `
        -o "$OUT\$label.body.json" `
        -w "    HTTP %{http_code}  %{time_total}s  %{size_download}B`n" `
        $url
}

function Post-Probe([string]$label, [string]$url, [string]$body) {
    Write-Host "==> [$label] POST $url"
    curl.exe -sS -X POST `
        -H "Content-Type: application/json" `
        -D "$OUT\$label.headers.txt" `
        -o "$OUT\$label.body.json" `
        -w "    HTTP %{http_code}  %{time_total}s  %{size_download}B`n" `
        --data-raw $body `
        $url
}

Write-Host "######## FREEMIUM ########"

# B1 — rate-limit headers (inspect P1_fuel_types.headers.txt). Doubles as a 200 ref.
Get-Probe "P1_fuel_types"   "$BASE/auto/type?api_key=$KEY"

# B2 — missing key (expect 403 API_KEY_MISSING) and invalid key (403 API_KEY_INVALID).
Get-Probe "P12_err_no_key"  "$BASE/auto/colors"
Get-Probe "P13_err_bad_key" "$BASE/auto/colors?api_key=DEFINITELY_WRONG_KEY_123"

if ($UID) {
    Write-Host "######## PAID — POST (metered) ########"

    # E2 — period enum: read periodSelectorData.elements[].value in the body.
    Post-Probe "P14_statistic_period" `
        "$BASE/auto/statistic-avarage-price/?user_id=$UID&api_key=$KEY" `
        '{"langId":4,"period":365,"params":{"omniId":"TMBGP21U432674944"}}'

    # E6 — unlisted car: 200 w/ notice, or 4xx? Implausible VIN.
    Post-Probe "P15_vin_unlisted" `
        "$BASE/auto/params/by/vin-code/?user_id=$UID&api_key=$KEY" `
        '{"langId":4,"period":365,"params":{"omniId":"XX00000000000000X"}}'
} else {
    Write-Host "Set `$env:AUTORIA_USER_ID to run paid POST probes P14/P15."
}

Write-Host ""
Write-Host "######## DONE — files in $OUT\ ########"
Write-Host "Rate-limit headers (B1):"
Get-Content "$OUT\P1_fuel_types.headers.txt" | Select-String -Pattern "ratelimit|retry|limit|remaining" -CaseSensitive:$false
Write-Host ""
Write-Host "Error envelope (B2), no key:"
Get-Content "$OUT\P12_err_no_key.body.json"
Write-Host ""
Write-Host "Error envelope (B2), bad key:"
Get-Content "$OUT\P13_err_bad_key.body.json"
