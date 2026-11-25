#!/bin/bash
# Second flight scanner (another IP than GitHub): small Google batches with a cool-down.
# Saves to local_checks.json on the working branch ([skip ci]); the GitHub job and Atlas merge it in.
# Usage: bash scan_loop.sh <rounds> [budget] [cooldown_min]
cd "$(dirname "$0")"
B=claude/compassionate-hawking-lq51s3
ROUNDS=${1:-8}; BUDGET=${2:-10}; COOL=${3:-25}
W=$(mktemp -d)
for i in $(seq 1 "$ROUNDS"); do
  git pull -q --ff-only origin $B
  git fetch -q --depth 1 origin flight-data && git show FETCH_HEAD:flight_checks.json > "$W/gh.json" || echo '{}' > "$W/gh.json"
  [ -f local_checks.json ] || echo '{}' > local_checks.json
  python3 merge_checks.py "$W/gh.json" local_checks.json "$W/prev.json" > /dev/null
  GOOGLE_BUDGET=$BUDGET python3 scan_flights.py search_config.json "$W/prev.json" "$W/new.json" | grep -E "^google|blocked|ok queries"
  python3 merge_checks.py "$W/prev.json" "$W/new.json" local_checks.json | tr '\n' ' '; echo
  git add local_checks.json && git commit -qm "Second scanner flight checks $(date -u +%FT%TZ) [skip ci]" && git push -q origin $B && echo "round $i saved $(date -u +%T)"
  if grep -q '"blocked": true' "$W/new.json"; then sleep $((COOL*2*60)); else sleep $((COOL*60)); fi
done
