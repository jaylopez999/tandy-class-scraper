import time, sys

print("Worker online — scheduling will be added after first deploy.", flush=True) try: while True: time.sleep(3600) # stay alive except KeyboardInterrupt: sys.exit(0)
