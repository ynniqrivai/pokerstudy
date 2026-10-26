# Poker Study Analytics

A natural-language analytics system over 10,088 hands from the **Pluribus** poker AI experiment. Ask a question in plain English, get back the SQL that was run, the result, and an explanation of what it means.

Pluribus was the Facebook AI Research and Carnegie Mellon bot that beat five human professionals at six-player no-limit hold'em in 2019. The hands it played are public. This project makes them queryable by someone who knows poker but not SQL.

```
$ python3 src/coach.py "How often does Pluribus fold before the flop?"

Takeaway: Pluribus folds 73.76% of its hands preflop, demonstrating that a
world-class winning strategy requires playing a tight, disciplined range of
about 26% of starting hands.
```

## Why this exists

Poker hand histories are a good test case for a problem that shows up everywhere: the question people want to ask is in domain vocabulary, and the data is in schema vocabulary. Nobody asks "what is the mean of net_bb grouped by player." They ask "was Pluribus actually winning?"

Answering that correctly turns out to require more than translating English to SQL, which is most of what this repo is about.

## Architecture

```
question
   │
   ▼
Gemini (Vertex AI) ──── schema + domain rules in system prompt
   │
   ▼
generated SQL ──── validation: read-only, single statement, no DDL/DML
   │
   ▼
BigQuery ──── per-query byte cap
   │
   ├── on error ──► back to Gemini with the error, regenerate (once)
   │
   ▼
results ──── Gemini explains, grounded only in returned rows
```

**Two tables, built by `src/ingest.py`:**

| table | grain | notable columns |
|---|---|---|
| `hands` | one row per hand | `source`, `variant`, `big_blind`, `actions` (PHH notation) |
| `hand_players` | one row per player per hand | `net`, `net_bb`, `starting_stack`, `finishing_stack` |

## Why the obvious query gives the wrong answer

Ask "was Pluribus winning?" and the natural query is a sum of `net` grouped by
player. It returns a confident, specific, wrong number.

**The easy trap.** The corpus spans three sources — Pluribus cash-game sessions
at 50/100 blinds, WSOP 2023 tournament hands, and a few famous single hands.
Summing `net` across them adds tournament chips to cash-game chips, which is why
one player initially showed +25,200,000 against others in the hundreds. Obvious
once seen, because the number is absurd.

**The trap worth caring about.** Normalize to big blinds per hand, filter to the
Pluribus sessions, and the bot comes out at roughly **−0.07 bb/hand**. The
published result has Pluribus *winning* at about 48 mbb/game. That is not a bug
in the pipeline.

Ten thousand six-handed hands is nowhere near enough to resolve an edge that
size from raw chip counts. The standard deviation of the estimate swamps the
effect. This is exactly why Brown and Sandholm reported AIVAT-adjusted results
rather than raw winnings: without variance reduction, ten thousand hands cannot
distinguish a strong winning strategy from a small losing one.

The first error announces itself. The second produces a plausible figure that
contradicts published work, and a reasonable person reports it.

Both are now constraints the system cannot violate:

- never aggregate across `source` values
- measure in `net_bb`, never raw `net`
- always report hand counts alongside any per-player result
- warn when a player has fewer than ~1,000 hands
- explanations may only use numbers present in the returned rows

## Guardrails

An LLM writing SQL against a warehouse is an untrusted input problem. Three defenses:

- **`check_sql`** — single statement, must start with `SELECT` or `WITH`, rejects `INSERT/UPDATE/DELETE/MERGE/DROP/CREATE/ALTER/TRUNCATE/GRANT/REVOKE`
- **`maximum_bytes_billed`** — hard per-query cost cap
- **retry with exponential backoff** — Vertex AI shared capacity returns transient 429s, especially on new projects

Note that the self-correction loop deliberately does *not* retry on a guardrail violation. A blocked query is a decision, not a transient failure.

## Running it

```bash
git clone https://github.com/ynniqrivai/pokerstudy.git
cd pokerstudy
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

export GCP_PROJECT="your-gcp-project-id"

# fetch the hand histories (not vendored: not my data)
# the full repo is ~1.7GB; only these sources are used, so trim after cloning
git clone https://github.com/uoftcprg/phh-dataset.git data
rm -rf data/handhq data/.git        # leaves ~39MB

python3 src/ingest.py               # writes hands.csv and hand_players.csv

bq mk --dataset "$GCP_PROJECT:pokerstudy"
bq load --autodetect --source_format=CSV pokerstudy.hands hands.csv
bq load --autodetect --source_format=CSV pokerstudy.hand_players hand_players.csv

python3 src/coach.py "Which player had the best win rate per 100 hands?"
```

## Data

Hand histories come from the [PHH dataset](https://github.com/uoftcprg/phh-dataset) published by the University of Toronto Computer Poker Research Group, in the TOML-based Poker Hand History format. Not redistributed here.

## Status and what's next

Working: ingest, BigQuery warehouse, text-to-SQL with schema grounding, self-correction, guardrails, explanation.

Planned:
- retrieval over the TDA rules and the Pluribus/Libratus/DeepStack papers, so domain terms the schema doesn't contain ("donk bet", "three-bet") resolve to correct queries
- token, latency and cost-per-request instrumentation, to measure whether the agentic path beats a fixed pipeline
- deployment behind an HTTP endpoint

## Reading

- Brown & Sandholm, [*Superhuman AI for multiplayer poker*](https://www.science.org/doi/10.1126/science.aay2400), Science, 2019
- [PHH format specification](https://github.com/uoftcprg/phh-std)
