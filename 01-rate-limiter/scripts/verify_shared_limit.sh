#!/usr/bin/env bash
# Fires requests at the load-balanced endpoint (round-robin across 3 app
# instances) and confirms the total allowed count matches the configured
# bucket capacity, not capacity x 3 -- which is what the naive
# per-instance-memory design (see design doc, "naive solution") would
# produce, since each instance would enforce its own independent limit.
set -euo pipefail

CAPACITY=20
ALLOWED_COUNT=0
TOTAL_REQUESTS=30

for i in $(seq 1 "$TOTAL_REQUESTS"); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
    http://localhost:8080/api/write -H "X-User-Id: test_user")
  if [ "$STATUS" == "200" ]; then
    ALLOWED_COUNT=$((ALLOWED_COUNT + 1))
  fi
done

echo "Allowed: $ALLOWED_COUNT / $TOTAL_REQUESTS requests (bucket capacity: $CAPACITY)"

if [ "$ALLOWED_COUNT" -eq "$CAPACITY" ]; then
  echo "PASS: shared limit correctly enforced across 3 app instances"
  exit 0
else
  echo "FAIL: expected exactly $CAPACITY allowed, got $ALLOWED_COUNT -- likely per-instance state leaking in"
  exit 1
fi
