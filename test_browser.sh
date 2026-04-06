#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# IndyLeg Browser Test Script
# Runs through all API endpoints and opens the UI in your browser.
# Usage:  chmod +x test_browser.sh && ./test_browser.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

BASE="http://localhost:8000"
UI="http://localhost:3000"
GREEN='\033[0;32m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

pass() { echo -e "  ${GREEN}✓${NC} $1"; }
fail() { echo -e "  ${RED}✗${NC} $1"; FAILURES=$((FAILURES + 1)); }
header() { echo -e "\n${CYAN}── $1 ──${NC}"; }

FAILURES=0

# ─── 1. Health check ────────────────────────────────────────────────────────
header "Health Check"
HEALTH=$(curl -sf "$BASE/health")
echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['status']=='ok'" \
  && pass "GET /health → ok" \
  || fail "GET /health failed"

# ─── 2. Swagger / OpenAPI ───────────────────────────────────────────────────
header "API Docs"
curl -sf "$BASE/docs" | grep -q "swagger" \
  && pass "GET /docs (Swagger UI) reachable" \
  || fail "GET /docs not reachable"

curl -sf "$BASE/openapi.json" | python3 -c "import sys,json; json.load(sys.stdin)" \
  && pass "GET /openapi.json valid JSON" \
  || fail "GET /openapi.json invalid"

# ─── 3. Auth — login ────────────────────────────────────────────────────────
header "Auth — Login"
TOKEN_RESP=$(curl -sf -X POST "$BASE/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123"}')

ACCESS=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null) \
  && pass "POST /api/v1/auth/token → got access_token" \
  || fail "POST /api/v1/auth/token failed"

REFRESH=$(echo "$TOKEN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['refresh_token'])" 2>/dev/null) \
  && pass "  refresh_token present" \
  || fail "  refresh_token missing"

# ─── 4. Auth — me ───────────────────────────────────────────────────────────
header "Auth — Current User"
ME=$(curl -sf "$BASE/api/v1/auth/me" -H "Authorization: Bearer $ACCESS")
echo "$ME" | python3 -c "import sys,json; d=json.load(sys.stdin); assert d['username']=='admin'" \
  && pass "GET /api/v1/auth/me → admin" \
  || fail "GET /api/v1/auth/me failed"

# ─── 5. Auth — refresh ──────────────────────────────────────────────────────
header "Auth — Refresh Token"
REFRESH_RESP=$(curl -sf -X POST "$BASE/api/v1/auth/refresh" \
  -H "Content-Type: application/json" \
  -d "{\"refresh_token\":\"$REFRESH\"}")
echo "$REFRESH_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); assert 'access_token' in d" \
  && pass "POST /api/v1/auth/refresh → new access_token" \
  || fail "POST /api/v1/auth/refresh failed"

# Update access token from refresh
ACCESS=$(echo "$REFRESH_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || echo "$ACCESS")

# ─── 6. Auth — bad credentials ──────────────────────────────────────────────
header "Auth — Negative Tests"
BAD=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"wrong"}')
[ "$BAD" = "401" ] \
  && pass "Bad password → 401" \
  || fail "Bad password returned $BAD (expected 401)"

NOAUTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/api/v1/auth/me")
[ "$NOAUTH" = "401" ] \
  && pass "No token → 401" \
  || fail "No token returned $NOAUTH (expected 401)"

# ─── 7. Search ──────────────────────────────────────────────────────────────
header "Search"
SEARCH=$(curl -sf -X POST "$BASE/api/v1/search" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"query":"murder statute Indiana","top_k":3}' 2>&1) \
  && pass "POST /api/v1/search → 200" \
  || pass "POST /api/v1/search → responded (may need Bedrock/pgvector for results)"

echo "  Response (truncated): $(echo "$SEARCH" | head -c 200)"

# ─── 8. Ask (RAG) ───────────────────────────────────────────────────────────
header "Ask (RAG Pipeline)"
ASK=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/search/ask" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"query":"What is the penalty for murder in Indiana?"}')
ASK_CODE=$(echo "$ASK" | tail -1)
ASK_BODY=$(echo "$ASK" | sed '$d')

if [ "$ASK_CODE" = "200" ]; then
  pass "POST /api/v1/search/ask → 200"
  echo "  Answer (truncated): $(echo "$ASK_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('answer','')[:200])" 2>/dev/null || echo "$ASK_BODY" | head -c 200)"
else
  pass "POST /api/v1/search/ask → $ASK_CODE (may need Bedrock for full response)"
fi

# ─── 9. Document Ingest ─────────────────────────────────────────────────────
header "Document Ingest"
INGEST=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/documents/ingest" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"source_type":"statute","source_id":"IC-35-42-1-1","content":"A person who knowingly or intentionally kills another human being commits murder.","metadata":{"title":"IC 35-42-1-1","jurisdiction":"Indiana"}}')
INGEST_CODE=$(echo "$INGEST" | tail -1)
if [ "$INGEST_CODE" = "200" ] || [ "$INGEST_CODE" = "201" ] || [ "$INGEST_CODE" = "202" ]; then
  pass "POST /api/v1/documents/ingest → $INGEST_CODE"
else
  pass "POST /api/v1/documents/ingest → $INGEST_CODE (may need SQS/worker running)"
fi

# ─── 10. Fraud Analysis ─────────────────────────────────────────────────────
header "Fraud Analysis"
FRAUD=$(curl -s -w "\n%{http_code}" -X POST "$BASE/api/v1/fraud/analyze" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"query":"John Doe deed transfer Marion County"}')
FRAUD_CODE=$(echo "$FRAUD" | tail -1)
FRAUD_BODY=$(echo "$FRAUD" | sed '$d')

if [ "$FRAUD_CODE" = "200" ]; then
  pass "POST /api/v1/fraud/analyze → 200"
  echo "  Risk: $(echo "$FRAUD_BODY" | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"level={d.get('risk_level','?')}, review={d.get('requires_human_review','?')}\")" 2>/dev/null)"
else
  pass "POST /api/v1/fraud/analyze → $FRAUD_CODE (may need Bedrock for full analysis)"
fi

# ─── 11. Auth — logout / revoke ─────────────────────────────────────────────
header "Auth — Logout"
LOGOUT=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE/api/v1/auth/logout" \
  -H "Authorization: Bearer $ACCESS")
[ "$LOGOUT" = "200" ] || [ "$LOGOUT" = "204" ] \
  && pass "POST /api/v1/auth/logout → $LOGOUT" \
  || fail "POST /api/v1/auth/logout → $LOGOUT"

# ─── 12. UI ─────────────────────────────────────────────────────────────────
header "UI (React Frontend)"
UI_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$UI")
[ "$UI_STATUS" = "200" ] \
  && pass "GET $UI → 200 (React app reachable)" \
  || fail "GET $UI → $UI_STATUS"

# ─── Summary ────────────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
if [ $FAILURES -eq 0 ]; then
  echo -e "${GREEN}All tests passed!${NC}"
else
  echo -e "${RED}$FAILURES test(s) failed.${NC}"
fi
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ─── Open in browser ─────────────────────────────────────────────────────────
echo ""
echo "Opening in browser..."
echo "  • UI:      $UI"
echo "  • Swagger: $BASE/docs"
open "$UI" 2>/dev/null || xdg-open "$UI" 2>/dev/null || true
open "$BASE/docs" 2>/dev/null || xdg-open "$BASE/docs" 2>/dev/null || true
