import subprocess
import sys
import time
import os

ROOT = os.path.dirname(__file__)
PY = sys.executable

def start(cmd):
    # redirect stdout/stderr to log files per process
    name = f"{cmd[0].split('.')[0]}_{cmd[1] if len(cmd)>1 else '0'}.log"
    logfile = open(os.path.join(ROOT, 'logs', name), 'a', buffering=1)
    return subprocess.Popen([PY] + cmd, cwd=ROOT, stdout=logfile, stderr=logfile)

def main():
    seeds = [5000, 5001, 5002]
    peers = [6000, 6001, 6002]

    procs = []
    os.makedirs(os.path.join(ROOT, 'logs'), exist_ok=True)

    print("Starting seeds...")
    for p in seeds:
        procs.append(start(['seed.py', str(p)]))
        time.sleep(0.2)

    print("Starting peers...")
    for p in peers:
        procs.append(start(['peer.py', str(p)]))
        time.sleep(0.2)

    # allow time for registration and gossip
    print("Waiting 12s for registration/gossip...")
    time.sleep(12)

    # stop one peer to simulate failure
    print("Stopping peer 6000 to simulate failure")
    # find the Popen for peer 6000 (started after seeds)
    peer_proc = None
    for proc in procs:
        if proc.args and len(proc.args) >= 3 and proc.args[2].endswith('6000'):
            peer_proc = proc
            break

    if peer_proc:
        peer_proc.terminate()
    else:
        print("Couldn't find peer process for 6000; killing all peers by PID heuristic")
        # best-effort: continue

    # wait for peers to detect and seeds to reach consensus
    wait_time = 35
    print(f"Waiting {wait_time}s for detection and seed consensus...")
    time.sleep(wait_time)

    # read outputfile.txt for evidence of removal
    outpath = os.path.join(ROOT, 'outputfile.txt')
    found = False
    if os.path.exists(outpath):
        with open(outpath, 'r', encoding='utf-8', errors='ignore') as f:
            data = f.read()
            if "6000" in data and ("removed" in data.lower() or "dead" in data.lower()):
                found = True

    print("Removal evidence found:" , found)

    print("Cleaning up processes...")
    for proc in procs:
        try:
            proc.terminate()
        except Exception:
            pass

if __name__ == '__main__':
    main()
