"""Watch how healthy KSP and kRPC are while you fly (read-only: sends nothing to KSP).

    python run_game_health.py

Once a second it writes the game clock against the real clock (so a freeze or a lag spike shows as game time running
slow), the time warp, the active vessel, and kRPC's own counters. Rows go to game-health.csv. Stop with Ctrl+C. Use it
to tell whether a glitch came from the game, from a mod, or from something reading too much.
"""

import argparse
import csv
import sys
import time

FIELDS = [
    "wall_s", "ut", "ut_per_wall", "warp_rate", "mission_s", "vessel", "parts", "rpc_ms", "rpcs", "bytes_read",
    "time_per_rpc_update", "errors",
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--address", default="127.0.0.1")
    parser.add_argument("--rpc-port", type=int, default=50000)
    parser.add_argument("--stream-port", type=int, default=50001)
    parser.add_argument("--every", type=float, default=1.0)
    parser.add_argument("--csv", default="game-health.csv")
    args = parser.parse_args()

    import krpc

    conn = krpc.connect(name="Game health", address=args.address, rpc_port=args.rpc_port, stream_port=args.stream_port)
    centre = conn.space_center
    started, last = time.time(), None
    with open(args.csv, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        try:
            while True:
                wall = time.time() - started
                row, errors = {"wall_s": round(wall, 2)}, []

                def get(name, read):
                    try:
                        row[name] = read()
                    except Exception as exc:
                        row[name] = ""
                        errors.append(f"{name}={type(exc).__name__}")

                asked = time.time()
                get("ut", lambda: round(centre.ut, 2))
                row["rpc_ms"] = round((time.time() - asked) * 1000, 1)
                get("warp_rate", lambda: centre.warp_rate)
                get("mission_s", lambda: round(centre.active_vessel.met, 1))
                get("vessel", lambda: centre.active_vessel.name)
                get("parts", lambda: len(centre.active_vessel.parts.all))
                try:
                    status = conn.krpc.get_status()
                    row["rpcs"] = status.rpcs_executed
                    row["bytes_read"] = status.bytes_read
                    row["time_per_rpc_update"] = round(status.time_per_rpc_update, 6)
                except Exception as exc:
                    errors.append(f"status={type(exc).__name__}")
                if row.get("ut") != "":
                    if last is not None and wall > last[0]:
                        row["ut_per_wall"] = round((row["ut"] - last[1]) / (wall - last[0]), 3)
                    last = (wall, row["ut"])
                row["errors"] = ";".join(errors)
                writer.writerow(row)
                handle.flush()
                print(f"{row['wall_s']:8} ut {row.get('ut')} x{row.get('ut_per_wall', '')} rpc {row['rpc_ms']}ms {row['errors']}")
                time.sleep(args.every)
        except KeyboardInterrupt:
            print("\nStopped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
