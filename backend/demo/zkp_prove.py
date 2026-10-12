"""Make a zero-knowledge consent proof on the doctor's side.

The token never goes back to the server, so the proof has to be produced where
the token is kept. This is that prover. It needs no database, no liboqs and no
network — only the token, and the challenge the server handed out.

    # 1. once, after the patient approves:   GET  /api/doctor/consent-token/{patient_id}
    # 2. per proof:                          POST /api/doctor/zkp/challenge?patient_id=...
    python demo/zkp_prove.py --token "mlwe1:..." --challenge <challenge> \
        --context "consent:<patient_id>" > proof.json
    # 3.                                     POST /api/doctor/zkp/verify   (body: proof.json)

Pass ``--commitment`` too and the proof is checked locally before you send it.
A token can also be read from the QUANTUMCARE_CONSENT_TOKEN environment
variable, which keeps it out of shell history.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import zkp_service as zkp  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--token", default=os.getenv("QUANTUMCARE_CONSENT_TOKEN"),
                        help="consent token (or set QUANTUMCARE_CONSENT_TOKEN)")
    parser.add_argument("--challenge", required=True, help="challenge from /api/doctor/zkp/challenge")
    parser.add_argument("--context", required=True, help='context from the same response, e.g. "consent:<patient_id>"')
    parser.add_argument("--commitment", help="optional: check the proof locally before sending it")
    args = parser.parse_args()

    if not args.token:
        parser.error("no token given (use --token or QUANTUMCARE_CONSENT_TOKEN)")
    # Values pasted from a JSON response or a file often carry a stray newline.
    args.token = args.token.strip()
    if args.commitment:
        args.commitment = args.commitment.strip()

    started = time.perf_counter()
    try:
        proof = zkp.prove(args.token, args.challenge, args.context)
    except zkp.ZKPError as exc:
        print(f"Could not make a proof: {exc}", file=sys.stderr)
        return 2
    elapsed = time.perf_counter() - started

    if args.commitment and not zkp.verify(args.commitment, proof, args.challenge, args.context):
        print("The proof does not verify against that commitment — wrong token, challenge "
              "or context. Nothing was sent.", file=sys.stderr)
        return 1

    print(json.dumps({"challenge": args.challenge, **proof}))
    print(f"{proof['scheme']} proof made in {elapsed:.2f}s"
          + (", checked locally" if args.commitment else ""), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
