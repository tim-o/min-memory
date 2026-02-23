#!/bin/bash
# Integration test for update_memory tool
set -euo pipefail

BASE="http://localhost:8080"
KEY="5ce181db9b13502a7bde13b8c51fadffed71b1748cc901c04632710715db65ee"
USER="google-oauth2|test-user-123"
PASS=0
FAIL=0

mcp() {
  curl -s -X POST "$BASE/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: $SESSION_ID" \
    -H "X-Backend-Key: $KEY" \
    -H "X-User-Id: $USER" \
    -d "$1"
}

assert_contains() {
  local label="$1" response="$2" expected="$3"
  if echo "$response" | grep -qF "$expected"; then
    echo "  PASS: $label"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $label (expected '$expected' in response)"
    echo "    Got: $response"
    FAIL=$((FAIL + 1))
  fi
}

init_session() {
  local user="$1" header_file="$2"
  curl -s -X POST "$BASE/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "X-Backend-Key: $KEY" \
    -H "X-User-Id: $user" \
    -d '{"jsonrpc":"2.0","id":0,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"test","version":"1.0"}}}' \
    -D "$header_file" > /dev/null
  local sid=$(grep -i 'mcp-session-id' "$header_file" | tr -d '\r' | awk '{print $2}')
  # Send required initialized notification
  curl -s -X POST "$BASE/mcp" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: $sid" \
    -H "X-Backend-Key: $KEY" \
    -H "X-User-Id: $user" \
    -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' > /dev/null
  echo "$sid"
}

echo "=== Initialize MCP session ==="
SESSION_ID=$(init_session "$USER" /tmp/test-headers)
echo "  Session: $SESSION_ID"

echo ""
echo "=== Test 1: Store a memory ==="
STORE=$(mcp '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"store_memory","arguments":{"text":"Tim prefers dark roast coffee","memory_type":"core_identity","scope":"global","entity":"tim-preferences"}}}')
echo "  Response: $STORE"
MEMORY_ID=$(echo "$STORE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(json.loads(r['result']['content'][0]['text'])['memory_id'])")
echo "  Memory ID: $MEMORY_ID"
assert_contains "store returns stored status" "$STORE" 'stored'

echo ""
echo "=== Test 2: Update text (should re-embed) ==="
UPDATE_TEXT=$(mcp "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"update_memory\",\"arguments\":{\"memory_id\":\"$MEMORY_ID\",\"text\":\"Tim prefers medium roast coffee\"}}}")
echo "  Response: $UPDATE_TEXT"
assert_contains "update text returns updated" "$UPDATE_TEXT" 'updated'

echo ""
echo "=== Test 3: Verify text was updated via fetch ==="
FETCH=$(mcp "{\"jsonrpc\":\"2.0\",\"id\":3,\"method\":\"tools/call\",\"params\":{\"name\":\"fetch\",\"arguments\":{\"id\":\"$MEMORY_ID\"}}}")
echo "  Response: $FETCH"
assert_contains "fetch shows new text" "$FETCH" "medium roast"

echo ""
echo "=== Test 4: Update metadata only (tags + status) ==="
UPDATE_META=$(mcp "{\"jsonrpc\":\"2.0\",\"id\":4,\"method\":\"tools/call\",\"params\":{\"name\":\"update_memory\",\"arguments\":{\"memory_id\":\"$MEMORY_ID\",\"tags\":[\"coffee\",\"preferences\"],\"status\":\"verified\"}}}")
echo "  Response: $UPDATE_META"
assert_contains "update metadata returns updated" "$UPDATE_META" 'updated'

echo ""
echo "=== Test 5: Verify metadata via search ==="
SEARCH=$(mcp '{"jsonrpc":"2.0","id":5,"method":"tools/call","params":{"name":"retrieve_context","arguments":{"query":"coffee preferences","limit":1}}}')
echo "  Response: $SEARCH"
assert_contains "search finds updated memory" "$SEARCH" "medium roast"

echo ""
echo "=== Test 6: Update nonexistent memory ==="
UPDATE_MISSING=$(mcp '{"jsonrpc":"2.0","id":6,"method":"tools/call","params":{"name":"update_memory","arguments":{"memory_id":"00000000-0000-0000-0000-000000000000","text":"nope"}}}')
echo "  Response: $UPDATE_MISSING"
assert_contains "nonexistent returns error" "$UPDATE_MISSING" "not found"

echo ""
echo "=== Test 7: Update a deleted memory ==="
DELETE=$(mcp "{\"jsonrpc\":\"2.0\",\"id\":7,\"method\":\"tools/call\",\"params\":{\"name\":\"delete_memory\",\"arguments\":{\"memory_id\":\"$MEMORY_ID\"}}}")
UPDATE_DELETED=$(mcp "{\"jsonrpc\":\"2.0\",\"id\":8,\"method\":\"tools/call\",\"params\":{\"name\":\"update_memory\",\"arguments\":{\"memory_id\":\"$MEMORY_ID\",\"text\":\"should fail\"}}}")
echo "  Response: $UPDATE_DELETED"
assert_contains "deleted memory returns error" "$UPDATE_DELETED" "deleted"

echo ""
echo "=== Test 8: Update memory owned by another user ==="
# Store as different user
SESSION2=$(init_session "google-oauth2|other-user" /tmp/test-headers2)
OTHER_STORE=$(curl -s -X POST "$BASE/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: $SESSION2" \
  -H "X-Backend-Key: $KEY" \
  -H "X-User-Id: google-oauth2|other-user" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"store_memory","arguments":{"text":"Other user secret","memory_type":"core_identity","scope":"global","entity":"other-prefs"}}}')
OTHER_ID=$(echo "$OTHER_STORE" | python3 -c "import sys,json; r=json.load(sys.stdin); print(json.loads(r['result']['content'][0]['text'])['memory_id'])")
# Try to update as original user
UPDATE_UNAUTH=$(mcp "{\"jsonrpc\":\"2.0\",\"id\":9,\"method\":\"tools/call\",\"params\":{\"name\":\"update_memory\",\"arguments\":{\"memory_id\":\"$OTHER_ID\",\"text\":\"hacked\"}}}")
echo "  Response: $UPDATE_UNAUTH"
assert_contains "cross-user update blocked" "$UPDATE_UNAUTH" "Unauthorized"

echo ""
echo "================================"
echo "Results: $PASS passed, $FAIL failed"
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
