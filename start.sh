#!/bin/bash
# Start every service QuantumCare needs, in dependency order.
#
#   ./start.sh
#
#   ./start.sh --lan      also reachable from other devices on this network
#   ./start.sh --tunnel   public URL, reachable from anywhere (Cloudflare)
#
# Safe to re-run: anything already running is left alone.
#
# LAN mode binds the backend and frontend to 0.0.0.0. PostgreSQL is
# deliberately NOT exposed — the backend reaches it over the loopback
# interface, and a database listening on the network is a far larger target
# than an API that at least demands a token.

set -u
LAN=0
TUNNEL=0
[ "${1:-}" = "--lan" ] && LAN=1
[ "${1:-}" = "--tunnel" ] && { LAN=1; TUNNEL=1; }

if [ "$LAN" = "1" ]; then
  LAN_IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null)
  if [ -z "$LAN_IP" ]; then
    echo "  Could not determine a LAN address — is Wi-Fi connected?"
    exit 1
  fi
  BIND_HOST=0.0.0.0
  if [ "$TUNNEL" = "1" ]; then
    # Relative, so the browser calls whatever host it loaded the page from and
    # Next.js proxies it onward. An absolute address baked in here would point
    # at a machine the visitor cannot reach.
    API_URL=""
  else
    API_URL="http://$LAN_IP:8000"
  fi
else
  BIND_HOST=127.0.0.1
  API_URL="http://127.0.0.1:8000"
fi
cd "$(dirname "$0")"
source ~/devtools/env.sh 2>/dev/null

up() { nc -z 127.0.0.1 "$1" 2>/dev/null; }

# Wait for a port, up to $2 seconds. Fixed sleeps were reporting services as
# FAILED on slower machines when they were seconds from being ready — IPFS in
# particular logged "Daemon is ready" moments after the script had given up.
wait_up() {
  local port="$1" limit="${2:-30}" waited=0
  while [ "$waited" -lt "$limit" ]; do
    up "$port" && return 0
    sleep 1
    waited=$((waited + 1))
  done
  return 1
}
say() { printf "  %-22s %s\n" "$1" "$2"; }

echo ""
echo "════════════════════════════════════════════════"
echo "  QuantumCare — starting services"
echo "════════════════════════════════════════════════"

# 1. PostgreSQL — everything else needs it, so it goes first.
#
# Read the port from .env rather than assuming: a Homebrew or Postgres.app
# install uses 5432, while the portable build used in development is on 5433.
# The script previously hardcoded 5433 and reported FAILED on any machine with
# a perfectly healthy database somewhere else.
DB_PORT_CFG=$(grep -oE "^DB_PORT=[0-9]+" backend/.env 2>/dev/null | cut -d= -f2)
DB_PORT_CFG=${DB_PORT_CFG:-5433}

if up "$DB_PORT_CFG"; then
  say "PostgreSQL ($DB_PORT_CFG)" "already running"
elif [ -d ~/devtools/pgdata ]; then
  # The portable build this project ships with. Only started when it is present.
  pg_ctl -D ~/devtools/pgdata -o "-p $DB_PORT_CFG" -l ~/devtools/pgdata/server.log start >/dev/null 2>&1
  wait_up "$DB_PORT_CFG" 20 && say "PostgreSQL ($DB_PORT_CFG)" "started" \
    || say "PostgreSQL ($DB_PORT_CFG)" "FAILED — see ~/devtools/pgdata/server.log"
else
  say "PostgreSQL ($DB_PORT_CFG)" "NOT RUNNING — start it, e.g. brew services start postgresql@14"
fi

# 2. Local EVM chain.
if up 8545; then
  say "EVM chain (8545)" "already running"
elif ! command -v anvil >/dev/null 2>&1; then
  # Not installed is a supported configuration: anchors are then labelled
  # local-simulated, which the admin dashboard reports honestly.
  say "EVM chain (8545)" "not installed — anchoring will be simulated"
else
  nohup anvil --silent > /tmp/anvil.log 2>&1 &
  wait_up 8545 25 && say "EVM chain (8545)" "started" || say "EVM chain (8545)" "FAILED — see /tmp/anvil.log"
fi

# The contract lives in anvil's memory, so a chain restart wipes it. Without
# this, anchoring silently falls back to "local-simulated" — which looks like
# a working chain until someone checks.
if up 8545 && command -v forge >/dev/null 2>&1; then
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
elif [ ! -x ~/devtools/kubo/ipfs ] && ! command -v ipfs >/dev/null 2>&1; then
  say "IPFS node (5001)" "not installed — publishing disabled"
else
  IPFS_BIN=$(command -v ipfs || echo ~/devtools/kubo/ipfs)
  # Use the portable repo only when it exists. Forcing IPFS_PATH at a fixed
  # location meant a perfectly good default repo at ~/.ipfs was ignored and the
  # daemon exited with "no IPFS repo found" — pointing at a directory that only
  # exists on the machine this script was written on.
  if [ -d ~/devtools/ipfs-repo ]; then
    export IPFS_PATH=~/devtools/ipfs-repo
  fi
  # Initialise on first use rather than failing with instructions.
  "$IPFS_BIN" repo stat >/dev/null 2>&1 || "$IPFS_BIN" init --profile server >/dev/null 2>&1
  nohup "$IPFS_BIN" daemon --enable-gc > /tmp/ipfs.log 2>&1 &
  wait_up 5001 45 && say "IPFS node (5001)" "started" || say "IPFS node (5001)" "FAILED — see /tmp/ipfs.log"
fi

# 4. Backend API.
if up 8000; then
  say "Backend API (8000)" "already running"
else
  ( cd backend && source venv/bin/activate \
    && DYLD_LIBRARY_PATH="$HOME/_oqs/lib:${DYLD_LIBRARY_PATH:-}" \
       nohup python3 -m uvicorn app.main:app --host "$BIND_HOST" --port 8000 > /tmp/backend.log 2>&1 & )
  wait_up 8000 45 && say "Backend API (8000)" "started" || say "Backend API (8000)" "FAILED — see /tmp/backend.log"
fi

# 5. Frontend.
if up 3000; then
  say "Frontend (3000)" "already running"
else
  # NEXT_PUBLIC_* is compiled into the browser bundle, so this URL is resolved
  # by the visiting device, not by this Mac. Pointing it at 127.0.0.1 would make
  # a phone try to reach itself.
  if [ "$LAN" = "1" ]; then
    # Run from frontend/ directly. The root "dev" script proxies through
    # `npm --prefix`, and a `-- --hostname` passthrough loses the flag name on
    # the way, leaving next to read the address as a directory.
    ( cd frontend && NEXT_PUBLIC_BACKEND_URL="$API_URL" \
        nohup npx next dev -H 0.0.0.0 > /tmp/frontend.log 2>&1 & )
  else
    nohup npm run dev > /tmp/frontend.log 2>&1 &
  fi
  wait_up 3000 60 && say "Frontend (3000)" "started" || say "Frontend (3000)" "FAILED — see /tmp/frontend.log"
fi

echo ""
echo "════════════════════════════════════════════════"
if [ "$LAN" = "1" ]; then
  up 3000 && echo "  Open here        http://localhost:3000"
  up 3000 && echo "  Other devices    http://$LAN_IP:3000"
  up 8000 && echo "  API docs         http://$LAN_IP:8000/docs"
  echo ""
  echo "  Reachable by anyone on this network. Fine for a demo on a"
  echo "  trusted network; stop it with ./stop.sh when you are done."
else
  up 3000 && echo "  Open      http://localhost:3000"
  up 8000 && echo "  API docs  http://localhost:8000/docs"
fi
if [ "$TUNNEL" = "1" ] && up 3000; then
  echo ""
  echo "  opening public tunnel…"
  PUBLIC=""

  # ngrok first. It carries its traffic over 443, which restricted networks
  # generally leave open; cloudflared needs port 7844, which college and
  # corporate Wi-Fi commonly block. Preferring the one that works avoids a
  # confusing failure five minutes before a demo.
  if command -v ngrok >/dev/null 2>&1; then
    nohup ngrok http 3000 --log stdout > /tmp/ngrok.log 2>&1 &
    for _ in $(seq 1 12); do
      sleep 2
      PUBLIC=$(grep -oE "url=https://[a-z0-9-]+\.ngrok[a-z.-]*" /tmp/ngrok.log 2>/dev/null | tail -1 | cut -d= -f2)
      [ -n "$PUBLIC" ] && break
    done
  fi

  if [ -z "$PUBLIC" ] && command -v cloudflared >/dev/null 2>&1; then
    echo "  ngrok unavailable — trying cloudflared…"
    nohup cloudflared tunnel --url http://127.0.0.1:3000 > /tmp/tunnel.log 2>&1 &
    for _ in $(seq 1 12); do
      sleep 2
      PUBLIC=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" /tmp/tunnel.log 2>/dev/null | head -1)
      [ -n "$PUBLIC" ] && break
    done
  fi

  if [ -n "$PUBLIC" ]; then
    echo ""
    echo "  PUBLIC URL       $PUBLIC"
    echo ""
    echo "  Works from any network. Anyone with the link can reach the app,"
    echo "  the data is synthetic and the logins are shared demo accounts,"
    echo "  so treat the link as public. Run ./stop.sh when finished."
  else
    echo "  No tunnel could be established."
    echo "  This network may block tunnelling — a phone hotspot usually works."
    echo "  Logs: /tmp/ngrok.log  /tmp/tunnel.log"
  fi
fi

echo ""
echo "  Login     PAT-2026-000035  /  Demo@1234"
echo "════════════════════════════════════════════════"
echo ""
