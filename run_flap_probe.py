"""Record what the game says about the flaps of the vessel you fly (read-only: sends nothing to KSP).

Start the kRPC server in KSP, fly the ship, then run this for about a minute:

    python run_flap_probe.py

It writes a row per flap every quarter second to flap-probe.csv in the folder you ran it from, and prints a line whenever
something about a flap changes. During the minute, retract and deploy the flaps, change the deploy angle and the authority
limiter, and move the stick, so the log shows which values follow what. It stops by itself after 60 seconds (--seconds).
"""

import argparse
import csv
import sys
import time

from ground_station.flap_probe import COLUMNS, read_flaps

WATCHED = ("modules", "deployed", "deploy_angle", "authority_limiter", "direction", "fields")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--rpc-port", type=int, default=50000)
    parser.add_argument("--stream-port", type=int, default=50001)
    parser.add_argument("--every", type=float, default=0.25, help="seconds between rows")
    parser.add_argument("--seconds", type=float, default=60.0, help="how long to record")
    parser.add_argument("--csv", default="flap-probe.csv")
    args = parser.parse_args()

    import krpc

    conn = krpc.connect(name="Flap probe", address=args.address, rpc_port=args.rpc_port, stream_port=args.stream_port)
    started, last = time.time(), {}
    print(f"Connected. Recording {args.seconds:.0f} s to {args.csv}. Move the flaps now. Ctrl+C to stop early.")
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        try:
            while time.time() - started < args.seconds:
                wall = time.time() - started
                try:
                    rows = read_flaps(conn.space_center.active_vessel, wall)
                    for row in rows:
                        writer.writerow(row)
                        shown = {key: row.get(key) for key in WATCHED}
                        if shown != last.get(row["flap"]):
                            last[row["flap"]] = shown
                            print(f"{wall:6.1f}s {row['flap']} " + " ".join(f"{k}={v}" for k, v in shown.items() if k != "fields"))
                    handle.flush()
                except Exception as exc:  # e.g. the game is loading a scene
                    print(f"(waiting: {type(exc).__name__})")
                time.sleep(args.every)
        except KeyboardInterrupt:
            print("\nStopped.")
    print(f"Done. {len(last)} flaps seen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
