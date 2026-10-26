import pandas as pd

pd.set_option("display.width", 120)

hp = pd.read_csv("hand_players.csv")
h = pd.read_csv("hands.csv")

# Attach each player-row to its hand's source and big blind
df = pd.merge(hp, h[["hand_id", "source", "big_blind"]], on="hand_id")

print("\nHands and missing results by source:")
print(df.groupby("source").agg(
    hands=("hand_id", "nunique"),
    player_rows=("player", "size"),
    missing_net=("net", lambda s: s.isna().sum()),
))

for src in ["pluribus", "wsop"]:
    sub = df[(df["source"] == src) & df["net_bb"].notna()]
    print(f"\nNet in big blinds by player ({src}):")
    print(sub.groupby("player")["net_bb"]
             .agg(hands="count", total_bb="sum", bb_per_hand="mean")
             .sort_values("total_bb", ascending=False)
             .round(3))