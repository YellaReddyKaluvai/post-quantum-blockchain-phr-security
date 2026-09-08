#!/bin/bash
# First-time setup on a new machine.
#
#   ./setup.sh
#
# Checks the tools are present, creates .env, builds the Python environment,
# creates the database and loads the schema. Stops at the first real problem
# rather than continuing and failing later in a way that is harder to read.

set -u
cd "$(dirname "$0")"
[ -f ~/devtools/env.sh ] && source ~/devtools/env.sh 2>/dev/null

ok()   { printf "  \033[92m✓\033[0m %s\n" "$1"; }
bad()  { printf "  \033[91m✗\033[0m %s\n" "$1"; }
info() { printf "    %s\n" "$1"; }

echo ""
echo "════════════════════════════════════════════════"
echo "  QuantumCare — first-time setup"
echo "════════════════════════════════════════════════"
echo ""
echo "  1. Checking tools"

MISSING=0
for tool in psql python3 node npm; do
  if command -v "$tool" >/dev/null 2>&1; then
    ok "$tool"
  else
    bad "$tool not found"
    MISSING=1
  fi
done

# Optional. Their absence disables a feature; it does not stop the app, and the
# system reports the missing capability rather than pretending it is there.
for tool in anvil forge ipfs; do
  command -v "$tool" >/dev/null 2>&1 && ok "$tool (optional)" \
    || info "· $tool not found — blockchain/IPFS features will be inactive"
done

if [ "$MISSING" = "1" ]; then
  echo ""
  bad "Install the missing tools first, then run this again."
  echo ""
  exit 1
fi

echo ""
echo "  2. Configuration"
if [ -f backend/.env ]; then
  ok ".env already exists — leaving it alone"
else
  cp backend/.env.example backend/.env
  # Generate real secrets rather than shipping the placeholders. A default
  # signing key that everyone shares is not a secret at all.
  SECRET=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  ENCKEY=$(python3 -c "import secrets; print(secrets.token_hex(16))")
  python3 - "$SECRET" "$ENCKEY" <<'PY'
import sys, pathlib, re
secret, enckey = sys.argv[1], sys.argv[2]
p = pathlib.Path("backend/.env"); t = p.read_text()
t = re.sub(r"^SECRET_KEY=.*$", f"SECRET_KEY={secret}", t, flags=re.M)
t = re.sub(r"^ENCRYPTION_KEY=.*$", f"ENCRYPTION_KEY={enckey}", t, flags=re.M)
p.write_text(t)
PY
  ok ".env created with freshly generated keys"
  info "AWS, SMTP and IPFS are left blank — the app runs without them"
fi

echo ""
echo "  3. Python environment"
if [ -d backend/venv ]; then
  ok "venv already exists"
else
  python3 -m venv backend/venv && ok "venv created"
fi
( cd backend && source venv/bin/activate && pip install -q -r requirements.txt ) \
  && ok "dependencies installed" || bad "pip install failed"

echo ""
echo "  4. Node packages"
if [ -d frontend/node_modules ]; then
  ok "node_modules already present"
else
  ( cd frontend && npm install --silent ) && ok "npm packages installed" || bad "npm install failed"
fi

echo ""
echo "  5. Database"
PORT=$(grep -oE "^DB_PORT=.*" backend/.env | cut -d= -f2)
PORT=${PORT:-5433}
if ! nc -z 127.0.0.1 "$PORT" 2>/dev/null; then
  bad "No PostgreSQL on port $PORT"
  info "Start it, then run this script again. If yours is on 5432,"
  info "change DATABASE_URL and DB_PORT in backend/.env first."
  echo ""
  exit 1
fi
ok "PostgreSQL reachable on $PORT"

if psql -h 127.0.0.1 -p "$PORT" -U postgres -lqt 2>/dev/null | cut -d\| -f1 | grep -qw pqc_hospital; then
  ok "database pqc_hospital already exists"
else
  createdb -h 127.0.0.1 -p "$PORT" -U postgres pqc_hospital 2>/dev/null \
    && ok "database created" || bad "could not create the database"
fi

psql -h 127.0.0.1 -p "$PORT" -U postgres -d pqc_hospital -q -f backend/db/init.sql >/dev/null 2>&1 \
  && ok "schema loaded (30 tables)" || bad "schema load failed"

echo ""
echo "════════════════════════════════════════════════"
echo "  Setup complete."
echo ""
ROWS=$(psql -h 127.0.0.1 -p "$PORT" -U postgres -d pqc_hospital -t -A \
       -c "SELECT COUNT(*) FROM Users;" 2>/dev/null || echo 0)
if [ "${ROWS:-0}" -gt 5 ] 2>/dev/null; then
  echo "  The database already holds $ROWS users — nothing more to load."
else
  echo "  The database is empty. To fill it with 500 demo"
  echo "  users and ~8,400 clinical records:"
  echo ""
  echo "    cd backend && source venv/bin/activate"
  echo "    python3 generate_dataset.py"
fi
echo ""
echo "  Then start everything:"
echo ""
echo "    ./start.sh"
echo "════════════════════════════════════════════════"
echo ""
