Demo script: Verifying the P2P system

1) Start three seed nodes (each in its own terminal):
   python seed.py 5000
   python seed.py 5001
   python seed.py 5002

2) Start three peers (each in its own terminal):
   python peer.py 6000
   python peer.py 6001
   python peer.py 6002

3) Wait ~15 seconds for registration and initial gossip to begin.

4) Evidence to show the evaluator (commands & what to look for):
   - Show `outputfile.txt` tail to display recent events:
       Get-Content outputfile.txt -Tail 200 -Wait
   - Look for seed registration quorum messages (propose/vote/commit).
   - Look for peer logs showing fetched peer lists and selected neighbors.
   - Look for `GOSSIP first-time` messages in peer logs.
   - To test failure detection: stop a peer (Ctrl+C) then watch other peers for
     `Initiating suspicion` and seeds for `DEAD_REPORT` voting and `removed` commit.

5) Optional automated run (creates `logs/` and per-process logs):
   python run_integration.py

Files to attach in submission: `seed.py`, `peer.py`, `config.txt`, `utils.py`, `run_integration.py`, `README.TXT`, `outputfile.txt`, `DEMO.md`, `SAMPLE_LOGS.txt`.

Notes:
- Expected behavior is described in `SAMPLE_LOGS.txt` for easy comparison.
- If anything needs reproducing, I can produce a short recorded run or extra log captures.
