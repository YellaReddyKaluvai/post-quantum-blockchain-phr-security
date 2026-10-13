// Cross-checks the browser prover (src/lib/zkpLattice.ts) against vectors made
// by the Python implementation the server verifies with. Run: node scripts/check-zkp.mjs
// (Node 22.18+ runs the TypeScript module directly). With --write it also stores
// a browser-made proof in the vectors for the Python side to verify.
import { readFileSync, writeFileSync } from "node:fs";
import { commitmentFor, prove, verify } from "../src/lib/zkpLattice.ts";

const path = new URL("../../backend/tests/fixtures/zkp_vectors.json", import.meta.url);
const v = JSON.parse(readFileSync(path, "utf8"));
const check = (ok, what) => { if (!ok) { console.error("FAIL:", what); process.exit(1); } console.log("ok  ", what); };

check(commitmentFor(v.token) === v.commitment, "commitment matches the Python implementation");
check(verify(v.commitment, v.python_proof, v.challenge, v.context), "accepts a proof made by the Python prover");
const started = performance.now();
const mine = prove(v.token, v.challenge, v.context);
const ms = Math.round(performance.now() - started);
check(mine.scheme === "mlwe-v1" && verify(v.commitment, mine.proof, v.challenge, v.context),
  `its own proof verifies (${ms} ms)`);
check(!verify(v.commitment, mine.proof, v.challenge + "x", v.context), "rejects a proof replayed against another challenge");
check(!verify(v.commitment, mine.proof, v.challenge, "consent:someone-else"), "rejects a proof for another patient");
if (v.browser_proof) {
  check(verify(v.commitment, v.browser_proof, v.challenge, v.context), "stored browser proof still verifies");
}
if (process.argv.includes("--write")) {
  writeFileSync(path, JSON.stringify({ ...v, browser_proof: mine.proof }, null, 1) + "\n");
  console.log("wrote browser_proof");
}
