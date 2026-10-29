"""Find out how long a booster stays readable once you have flown away from it (read-only: sends nothing to KSP).

Start the kRPC server in KSP, launch, and run this next to the game:

    python run_vessel_probe.py

Every second it prints each vessel kRPC knows about: how far away it is, and whether its speed, altitude and parts can
still be read ("ERR ..." means the game no longer gives that). It also writes every reading to vessel-probe.csv in the
folder you ran it from. Stop it with Ctrl+C. Send me the csv or the last screenful and I can see when the booster went
unreadable.
"""

import argparse
import csv
import sys
import time

from ground_station.vessel_probe import COLUMNS, probe


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--rpc-port", type=int, default=50000)
    parser.add_argument("--stream-port", type=int, default=50001)
    parser.add_argument("--every", type=float, default=1.0, help="seconds between readings")
    parser.add_argument("--csv", default="vessel-probe.csv")
    args = parser.parse_args()

    import krpc

    conn = krpc.connect(
        name="Vessel probe", address=args.address, rpc_port=args.rpc_port, stream_port=args.stream_port
    )
    centre = conn.space_center
    print(f"Connected. Writing {args.csv}. Ctrl+C to stop.")
    fields = ["wall_s", "game_ut", "mission_s", "active", "readable", *COLUMNS]
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        started = time.time()
        try:
            while True:
                try:
                    rows = probe(centre)
                    ut = centre.ut
                    mission = centre.active_vessel.met
                except Exception as exc:  # e.g. the game is loading a scene
                    print(f"(waiting: {type(exc).__name__})")
                    time.sleep(args.every)
                    continue
                print(f"\nT+{mission:7.1f}s")
                for row in rows:
                    flag = ">" if row["active"] else " "
                    ok = "readable" if row["readable"] else "NOT READABLE"
                    print(
                        f"{flag} {str(row['name'])[:24]:24} {str(row['distance_m']):>10} m  "
                        f"alt {str(row['altitude_m']):>9}  speed {str(row['speed_ms']):>8}  {ok}"
                    )
                    writer.writerow({"wall_s": round(time.time() - started, 1), "game_ut": round(ut, 1), "mission_s": round(mission, 1), **row})
                handle.flush()
                time.sleep(args.every)
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
