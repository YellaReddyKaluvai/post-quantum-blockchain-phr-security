#!/bin/bash
# Stop everything start.sh launched. The database is left running, since
# stopping it is rarely what you want between sessions.
source ~/devtools/env.sh 2>/dev/null
echo ""
for pat in "next dev" "uvicorn app.main" "ipfs daemon" "anvil"; do
  pkill -f "$pat" 2>/dev/null && printf "  stopped  %s\n" "$pat" || printf "  not running  %s\n" "$pat"
done
echo ""
echo "  PostgreSQL left running. To stop it:"
echo "    pg_ctl -D ~/devtools/pgdata stop"
echo ""
