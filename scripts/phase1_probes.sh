#!/usr/bin/env bash
#
# phase1_probes.sh — resolve the Phase-1 OPEN-QUESTIONS against the live
# AUTO.RIA Used-Cars API with the minimum number of metered requests.
#
# Each request's response headers AND body are saved to ./probe_responses/ so
# we can inspect rate-limit headers (B1) and exact error envelopes (B2) offline.
#
# Usage:
#   export AUTORIA_API_KEY="your_key"
#   export AUTORIA_USER_ID="your_user_id"     # only needed for paid POST probes
#   RUN_OPTIONAL=1 RUN_PAID=1 ./phase1_probes.sh
#
# Toggles:
#   RUN_OPTIONAL=1   also run order_by (C2) and abroad (C5) comparisons (+4 freemium)
#   RUN_PAID=1       also run the paid POST probes E2/E6 (+2 metered/paid)
#
# Quota: core run = 8 freemium GETs. +4 optional. +2 paid. All under 30/hr.
set -u

BASE="https://developers.ria.com"
KEY="${AUTORIA_API_KEY:-}"
UID_="${AUTORIA_USER_ID:-}"
OUT="probe_responses"
mkdir -p "$OUT"

if [[ -z "$KEY" ]]; then
  echo "ERROR: set AUTORIA_API_KEY" >&2
  exit 1
fi

# get <label> <url>   — GET with api_key already in the URL; dumps headers+body
get() {
  local label="$1" url="$2"
  echo "==> [$label] GET $url"
  curl -sS -g \
    -D "$OUT/${label}.headers.txt" \
    -o "$OUT/${label}.body.json" \
    -w 'HTTP %{http_code}  %{time_total}s  %{size_download}B\n' \
    "$url"
  echo "    saved: $OUT/${label}.headers.txt , $OUT/${label}.body.json"
  echo
}

# post <label> <url> <json>
post() {
  local label="$1" url="$2" body="$3"
  echo "==> [$label] POST $url"
  curl -sS -X POST \
    -H 'Content-Type: application/json' \
    -D "$OUT/${label}.headers.txt" \
    -o "$OUT/${label}.body.json" \
    -w 'HTTP %{http_code}  %{time_total}s  %{size_download}B\n' \
    --data-raw "$body" \
    "$url"
  echo "    saved: $OUT/${label}.headers.txt , $OUT/${label}.body.json"
  echo
}

echo "######## FREEMIUM — CORE (8 calls) ########"

# P1  D2 — canonical fuel-type list (resolves the two-version conflict).
#     Also the reference call for B1 (inspect P1.headers.txt for X-RateLimit-*).
get P1_fuel_types          "$BASE/auto/type?api_key=$KEY"

# P2  D1 — passenger-car (category 1) drive map. Docs only showed moto.
get P2_drivertypes_cat1    "$BASE/auto/categories/1/driverTypes?api_key=$KEY"

# P3  D7 — countries; confirm ISO-3166 numeric hypothesis (276=DE, 408=KR...).
get P3_countries           "$BASE/auto/countries?api_key=$KEY"

# P4  D4 — grouped-models shape (array<array<NameValue>>?).
get P4_models_group        "$BASE/auto/categories/1/marks/9/models/_group?api_key=$KEY"

# P5  C7/C9/E3 — search with NO countpage: default page size, last_id, lang_id.
get P5_search_default      "$BASE/auto/search?api_key=$KEY&category_id=1&marka_id[0]=9"

# P6  C1 — same search + searchType=4: does data[].type lose new-auto/OfferOfTheDay?
get P6_search_type4        "$BASE/auto/search?api_key=$KEY&category_id=1&marka_id[0]=9&searchType=4"

# P12 B2 — missing key -> expect 403 API_KEY_MISSING. Capture exact JSON envelope.
get P12_err_no_key         "$BASE/auto/colors"

# P13 B2 — invalid key -> expect 403 API_KEY_INVALID. Capture envelope.
get P13_err_bad_key        "$BASE/auto/colors?api_key=DEFINITELY_WRONG_KEY_123"

if [[ "${RUN_OPTIONAL:-0}" == "1" ]]; then
  echo "######## FREEMIUM — OPTIONAL (4 calls) ########"

  # P7/P8 C2 — order_by 2 (price asc) vs 3 (price desc). countpage=5 keeps it cheap.
  get P7_order_by_2        "$BASE/auto/search?api_key=$KEY&category_id=1&marka_id[0]=9&countpage=5&order_by=2"
  get P8_order_by_3        "$BASE/auto/search?api_key=$KEY&category_id=1&marka_id[0]=9&countpage=5&order_by=3"

  # P9/P10 C5 — abroad tri-state. Compare counts: abroad=1 (include) vs 2 (exclude).
  #   Baseline (omitted) = P5. countpage=1 minimizes payload.
  get P9_abroad_1          "$BASE/auto/search?api_key=$KEY&category_id=1&marka_id[0]=9&countpage=1&abroad=1"
  get P10_abroad_2         "$BASE/auto/search?api_key=$KEY&category_id=1&marka_id[0]=9&countpage=1&abroad=2"
fi

if [[ "${RUN_PAID:-0}" == "1" ]]; then
  echo "######## PAID — POST (2 calls, METERED) ########"
  if [[ -z "$UID_" ]]; then
    echo "ERROR: RUN_PAID=1 requires AUTORIA_USER_ID" >&2
    exit 1
  fi

  # P14 E2 — period enum: read periodSelectorData.elements[].value for allowed set.
  post P14_statistic_period \
    "$BASE/auto/statistic-avarage-price/?user_id=$UID_&api_key=$KEY" \
    '{"langId":4,"period":365,"params":{"omniId":"TMBGP21U432674944"}}'

  # P15 E6 — unlisted car: 200 with empty/notice, or 4xx? Use an implausible VIN.
  post P15_vin_unlisted \
    "$BASE/auto/params/by/vin-code/?user_id=$UID_&api_key=$KEY" \
    '{"langId":4,"period":365,"params":{"omniId":"XX00000000000000X"}}'
fi

echo "######## DONE ########"
echo "Inspect:"
echo "  jq '.[0:3]'                 $OUT/P1_fuel_types.body.json"
echo "  jq '.'                      $OUT/P2_drivertypes_cat1.body.json"
echo "  grep -i ratelimit -- $OUT/P1_fuel_types.headers.txt   # B1"
echo "  cat                         $OUT/P12_err_no_key.body.json   # B2"
echo "  jq '.result.search_result.count, (.result.search_result.ids|length), .additional_params.lang_id' $OUT/P5_search_default.body.json"
echo "  jq '[.result.search_result_common.data[].type]|group_by(.)|map({(.[0]):length})' $OUT/P6_search_type4.body.json"
echo
echo "Then paste probe_responses/ back to me (or the jq output) and I'll fold the"
echo "answers into OPEN-QUESTIONS.md and finalize the spec enums."
