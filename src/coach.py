import json
import os
import re
import sys

from google import genai
from google.genai import types
from google.cloud import bigquery

PROJECT = os.environ["GCP_PROJECT"]
GEMINI_LOCATION = "global"
BQ_LOCATION = "us-central1"
MODEL = "gemini-3.5-flash"
DATASET = f"{PROJECT}.pokerstudy"
MAX_BYTES_BILLED = 100 * 1024 * 1024  # 100 MB cost cap per query

SCHEMA = f"""
Table `{DATASET}.hands` (one row per hand):
- hand_id STRING (primary key)
- source STRING: 'pluribus' = Pluribus AI vs. pros, 6-max no-limit hold'em, ~10k hands;
  'wsop' = WSOP 2023 tournament hands, very high stakes, may include several poker variants;
  'famous' = a handful of famous single hands, results (net) are NULL
- session STRING, hand_index INTEGER
- variant STRING (PHH variant code, e.g. 'NT' = no-limit Texas hold'em)
- num_players INTEGER, small_blind FLOAT, big_blind FLOAT, ante FLOAT
- num_actions INTEGER, event STRING, year INTEGER
- actions STRING: PHH action notation joined by ' | '. Examples:
  'd dh p1 AsKd' (deal hole cards to seat 1), 'd db 7h8h9c' (deal board),
  'p3 cbr 225' (seat 3 bets/raises to 225), 'p2 cc' (seat 2 checks/calls),
  'p4 f' (seat 4 folds), 'p1 sm AsKd' (seat 1 shows)

Table `{DATASET}.hand_players` (one row per player per hand):
- hand_id STRING (joins to hands.hand_id)
- seat INTEGER (1-indexed; seat N is 'pN' in actions)
- player STRING
- starting_stack FLOAT, finishing_stack FLOAT
- net FLOAT (chips won/lost this hand)
- net_bb FLOAT (net divided by big blind; use this to compare results)
"""

SQL_INSTRUCTIONS = f"""You write BigQuery Standard SQL for a poker analytics app.
{SCHEMA}
Rules:
- Use fully qualified table names exactly as written above.
- Never compare or combine results across different sources; filter by source.
  If the question doesn't name a source, default to 'pluribus'.
- Measure results with net_bb, not net. Exclude rows where net_bb IS NULL.
- Include the number of hands in any per-player result, so sample size is visible.
- Read-only: a single SELECT (or WITH ... SELECT) statement, no semicolon.
- Always end with LIMIT 50 or less.
Respond with JSON only, in this shape: {{"sql": "...", "reasoning": "one sentence"}}
"""

COACH_INSTRUCTIONS = """You are a poker coach explaining data to a student.
Use only the numbers in the query results; never invent statistics.
If a player has fewer than about 1,000 hands, warn that the result may be mostly luck (variance).
Answer in 3-5 sentences, then end with one concrete takeaway starting with 'Takeaway:'.
"""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|merge|drop|create|alter|truncate|grant|revoke)\b", re.I
)


def generate_sql(client, question, previous_sql=None, error=None):
    prompt = f"Question: {question}"
    if previous_sql:
        prompt += (
            f"\n\nYour previous SQL failed.\nSQL:\n{previous_sql}\nError:\n{error}\n"
            "Return corrected SQL."
        )
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=SQL_INSTRUCTIONS,
            response_mime_type="application/json",
        ),
    )
    data = json.loads(resp.text)
    return data["sql"].strip().rstrip(";")


def check_sql(sql):
    if not re.match(r"^\s*(select|with)\b", sql, re.I):
        raise ValueError("Blocked: only SELECT queries are allowed.")
    if ";" in sql:
        raise ValueError("Blocked: only one statement is allowed.")
    if FORBIDDEN.search(sql):
        raise ValueError("Blocked: query contains a write/admin keyword.")


def run_sql(bq, sql):
    config = bigquery.QueryJobConfig(maximum_bytes_billed=MAX_BYTES_BILLED)
    return bq.query(sql, job_config=config).to_dataframe()


def explain(client, question, sql, df):
    prompt = (
        f"Question: {question}\n\nSQL that was run:\n{sql}\n\n"
        f"Results (CSV):\n{df.head(50).to_csv(index=False)}"
    )
    resp = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(system_instruction=COACH_INSTRUCTIONS),
    )
    return resp.text


def main():
    question = " ".join(sys.argv[1:]) or input("Ask the coach: ")
    client = genai.Client(
        vertexai=True,
        project=PROJECT,
        location=GEMINI_LOCATION,
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=5, initial_delay=2.0, max_delay=30.0)
        ),
    )
    bq = bigquery.Client(project=PROJECT, location=BQ_LOCATION)

    sql = generate_sql(client, question)
    try:
        check_sql(sql)
        df = run_sql(bq, sql)
    except ValueError:
        raise
    except Exception as e:
        print(f"\n(First query failed, asking Gemini to fix it: {e})")
        sql = generate_sql(client, question, previous_sql=sql, error=str(e))
        check_sql(sql)
        df = run_sql(bq, sql)

    print("\n--- SQL ---\n" + sql)
    print("\n--- Results ---")
    print(df.head(20).to_string(index=False))
    print("\n--- Coach ---")
    print(explain(client, question, sql, df))


if __name__ == "__main__":
    main()
