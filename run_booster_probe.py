"""Record everything the game says about the booster after separation (read-only: sends nothing to KSP).

Start the kRPC server in KSP, then run this before you launch:

    python run_booster_probe.py

When the vessel you fly drops several parts at once (the stack separating), it takes the vessel left within 5 km for
the booster and writes a row about it every half second: position, speed, altitude, air speed in Mach, dynamic pressure,
g-force, mass, parts, every engine's state and thrust, and the Starship Expansion Project engine mode. Rows go to
booster-probe.csv in the folder you ran it from, down to the moment the game stops answering. Stop with Ctrl+C.
"""

import argparse
import csv
import sys
import time

from ground_station.booster_probe import COLUMNS, BoosterFinder, read_booster


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--rpc-port", type=int, default=50000)
    parser.add_argument("--stream-port", type=int, default=50001)
    parser.add_argument("--every", type=float, default=0.5, help="seconds between rows")
    parser.add_argument("--csv", default="booster-probe.csv")
    args = parser.parse_args()

    import krpc

    conn = krpc.connect(name="Booster probe", address=args.address, rpc_port=args.rpc_port, stream_port=args.stream_port)
    centre = conn.space_center
    finder = BoosterFinder()
    print(f"Connected. Waiting for the separation. Writing {args.csv}. Ctrl+C to stop.")
    started, found = time.time(), False
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        try:
            while True:
                wall = time.time() - started
                try:
                    vessel = finder.update(wall, centre)
                    if vessel is not None:
                        if not found:
                            found = True
                            print(f"Booster found at {wall:.1f}s.")
                        row = read_booster(vessel, centre.active_vessel, centre.ut, wall)
                        writer.writerow(row)
                        handle.flush()
                        print(
                            f"{row['wall_s']:8} alt {str(row['altitude_m']):>9} speed {str(row['speed_ms']):>7} "
                            f"parts {row['parts']} engines {row['engines']} {row['errors'][:60]}"
                        )
                except Exception as exc:  # e.g. the game is loading a scene
                    print(f"(waiting: {type(exc).__name__})")
                time.sleep(args.every)
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
