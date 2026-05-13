# Receipt viewer

Single-file HTML viewer that verifies any Receipt v0.1 chain **client-side**
using the browser's built-in `crypto.subtle` (no server, no install, no
JavaScript dependencies).

Deployment options:
- Static file on Cloudflare Pages / Vercel / GitHub Pages
- Standalone open file:// in any browser
- Embed in your own `/verify` route

## Why client-side

1. **Trust**: users can right-click → view source. No black box.
2. **Cost**: zero. No server bill.
3. **Distribution**: anyone can fork the HTML and self-host. Standard
   propagation = the file gets copied around.
4. **Anti-fraud**: a trader can't run a fake "Receipt verifier" that lies,
   because users can run the canonical verifier on the same data and
   compare. Discrepancy = fraud signal.

## Usage

Locally:
```
python3 -m http.server 8080 -d receipt-viewer
open http://localhost:8080/index.html
```

Then either:
- Click "Verify" with a JSONL URL pasted in the input
- Or upload a local `.receipt.jsonl` file via the file picker

If you don't have a chain yet, `code-writing-demo.jsonl` in this directory
is a sample chain you can drop into the file picker as a smoke test.

## Renders

- `✅ VERIFIED` / `❌ INVALID_CHAIN` / `❌ SUSPECT_VERIFICATION` / etc. badge
- 0-100 **trust score** with letter grade (A/B/C/D/F) and full component breakdown
- Event counts by kind (claim/verified/error/heartbeat/...)
- Trust tier distribution
- Last 20 events in chain order
- Raw chain head JSON

## Differences from server verifier

| Capability | Client viewer | Server verifier |
|---|---|---|
| Static chain check (hashes, schema, pairing) | ✅ | ✅ |
| Trust score computation | ✅ | ✅ |
| Live exchange re-fetch (re-verify against Coinbase API) | ❌ | ✅ |
| Anchor URI dereferencing (IPFS / Arweave) | ❌ (browser CORS) | ✅ |
| Leaderboard / agent registry | ❌ | ✅ |

The client viewer is sufficient for "did this chain pass static integrity
checks". For full anchor + live reconciliation, use the server verifier
(see docs/verifier_api.md).
