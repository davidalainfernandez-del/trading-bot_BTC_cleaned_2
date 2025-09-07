#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse, csv, math, sys
import matplotlib.pyplot as plt
from pathlib import Path

def load_losses(history_path):
    losses = []
    with open(history_path, "r", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            try:
                ret = float(r.get("ret", "nan"))
                if math.isfinite(ret) and ret < 0:
                    losses.append(abs(ret)*100.0)  # in %
            except Exception:
                pass
    return losses

def main():
    ap = argparse.ArgumentParser(description="Histogramme des pertes absolues (%) et seuil SL recommandé.")
    ap.add_argument("--history", default="paper_roundtrips.csv")
    ap.add_argument("--sl", type=float, default=None, help="SL en décimal (ex: 0.006). Si non fourni, pas de ligne verticale.")
    ap.add_argument("--out", default="loss_distribution.png")
    args = ap.parse_args()

    losses = load_losses(args.history)
    if not losses:
        print("Aucune perte observée dans l'historique; rien à tracer.", file=sys.stderr)
        sys.exit(1)

    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.hist(losses, bins=min(20, max(5, int(len(losses)/2))), alpha=0.8)
    ax.set_title("Distribution des pertes absolues (%)")
    ax.set_xlabel("Perte (%)")
    ax.set_ylabel("Fréquence")

    if args.sl is not None:
        ax.axvline(args.sl*100.0)

    out = Path(args.out)
    fig.savefig(out, dpi=120, bbox_inches="tight")
    print(str(out))

if __name__ == "__main__":
    main()
