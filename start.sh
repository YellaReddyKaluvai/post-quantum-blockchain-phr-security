#!/bin/bash
# Start every service QuantumCare needs, in dependency order.
#
#   ./start.sh
#
# Safe to re-run: anything already running is left alone.

set -u
cd "$(dirname "$0")"
source ~/devtools/env.sh 2>/dev/null

up() { nc -z 127.0.0.1 "$1" 2>/dev/null; }
say() { printf "  %-22s %s\n" "$1" "$2"; }

echo ""
echo "════════════════════════════════════════════════"
echo "  QuantumCare — starting services"
echo "════════════════════════════════════════════════"

# 1. PostgreSQL — everything else needs it, so it goes first.
if up 5433; then
  say "PostgreSQL (5433)" "already running"
else
  pg_ctl -D ~/devtools/pgdata -o "-p 5433" -l ~/devtools/pgdata/server.log start >/dev/null 2>&1
  sleep 3
  up 5433 && say "PostgreSQL (5433)" "started" || say "PostgreSQL (5433)" "FAILED — see ~/devtools/pgdata/server.log"
fi

# 2. Local EVM chain.
if up 8545; then
  say "EVM chain (8545)" "already running"
else
  nohup anvil --silent > /tmp/anvil.log 2>&1 &
  sleep 4
  up 8545 && say "EVM chain (8545)" "started" || say "EVM chain (8545)" "FAILED — see /tmp/anvil.log"
fi

# The contract lives in anvil's memory, so a chain restart wipes it. Without
# this, anchoring silently falls back to "local-simulated" — which looks like
# a working chain until someone checks.
if up 8545; then
  CODE=$(cast code 0x5FbDB2315678afecb367f032d93F642f64180aa3 --rpc-url http://127.0.0.1:8545 2>/dev/null)
  if [ "$CODE" = "0x" ] || [ -z "$CODE" ]; then
    # Anvil funds accounts from a fixed, publicly documented test mnemonic.
    # Derive the key rather than hardcoding it — a wrong key fails with
    # "out of gas: allowance 0", which reads as a chain problem rather than
    # an unfunded account.
    ANVIL_KEY=$(cast wallet private-key --mnemonic \
      "test test test test test test test test test test test junk" 2>/dev/null)
    if forge create contracts/PHR.sol:PHR_Security \
         --rpc-url http://127.0.0.1:8545 \
         --private-key "$ANVIL_KEY" --broadcast >/tmp/deploy.log 2>&1; then
      say "PHR.sol contract" "deployed"
    else
      say "PHR.sol contract" "DEPLOY FAILED — see /tmp/deploy.log"
      echo "      anchors will fall back to 'local-simulated'"
    fi
  else
    say "PHR.sol contract" "already deployed"
  fi
fi

# 3. IPFS node.
if up 5001; then
  say "IPFS node (5001)" "already running"
else
  IPFS_PATH=~/devtools/ipfs-repo nohup ~/devtools/kubo/ipfs daemon --enable-gc > /tmp/ipfs.log 2>&1 &
  sleep 8
  up 5001 && say "IPFS node (5001)" "started" || say "IPFS node (5001)" "FAILED — see /tmp/ipfs.log"
fi

# 4. Backend API.
if up 8000; then
  say "Backend API (8000)" "already running"
else
  ( cd backend && source venv/bin/activate \
    && DYLD_LIBRARY_PATH="$HOME/_oqs/lib:${DYLD_LIBRARY_PATH:-}" \
       nohup python3 -m uvicorn app.main:app --host 127.0.0.1 --port 8000 > /tmp/backend.log 2>&1 & )
  sleep 8
  up 8000 && say "Backend API (8000)" "started" || say "Backend API (8000)" "FAILED — see /tmp/backend.log"
fi

# 5. Frontend.
if up 3000; then
  say "Frontend (3000)" "already running"
else
  nohup npm run dev > /tmp/frontend.log 2>&1 &
  sleep 12
  up 3000 && say "Frontend (3000)" "started" || say "Frontend (3000)" "FAILED — see /tmp/frontend.log"
fi

echo ""
echo "════════════════════════════════════════════════"
up 3000 && echo "  Open      http://localhost:3000"
up 8000 && echo "  API docs  http://localhost:8000/docs"
echo ""
echo "  Login     PAT-2026-000035  /  Demo@1234"
echo "════════════════════════════════════════════════"
echo ""
