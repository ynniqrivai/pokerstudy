import csv
import tomllib
from pathlib import Path

ROOT = Path("data")
hands, hand_players = [], []

for path in sorted(ROOT.rglob("*.phh")):
    with path.open("rb") as f:
        h = tomllib.load(f)

    rel = path.relative_to(ROOT)
    parts = rel.parts
    # Files directly in data/ (e.g. dwan-ivey-2009.phh) are one-off famous hands
    source = parts[0] if len(parts) > 1 else "famous"

    hand_id = str(rel).replace("/", "_").removesuffix(".phh")
    blinds = h.get("blinds_or_straddles", [])
    antes  = h.get("antes", [])
    start  = h.get("starting_stacks", [])
    finish = h.get("finishing_stacks", [])
    names  = h.get("players", [])
    acts   = h.get("actions", [])

    # One entry per seat; the big blind is the largest forced bet, wherever it sits
    big_blind = max(blinds) if blinds else None
    if not big_blind:
        big_blind = None
    positive_blinds = sorted(b for b in blinds if b > 0)
    small_blind = positive_blinds[0] if len(positive_blinds) > 1 else None

    hands.append({
        "hand_id": hand_id,
        "source": source,
        "session": path.parent.name if source != "famous" else None,
        "hand_index": h.get("hand"),
        "variant": h.get("variant"),
        "num_players": len(start),
        "small_blind": small_blind,
        "big_blind": big_blind,
        "ante": antes[0] if antes else None,
        "num_actions": len(acts),
        "event": h.get("event"),
        "year": h.get("year"),
        "actions": " | ".join(acts),
    })

    for i, s in enumerate(start):
        f_stack = finish[i] if i < len(finish) else None
        net = (f_stack - s) if f_stack is not None else None
        hand_players.append({
            "hand_id": hand_id,
            "seat": i + 1,
            "player": names[i] if i < len(names) else None,
            "starting_stack": s,
            "finishing_stack": f_stack,
            "net": net,
            # Net in big blinds makes results comparable across stakes
            "net_bb": net / big_blind if net is not None and big_blind else None,
        })


def write(rows, name):
    with open(name, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {name}")


write(hands, "hands.csv")
write(hand_players, "hand_players.csv")