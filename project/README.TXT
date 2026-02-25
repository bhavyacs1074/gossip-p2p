 Project: Gossip-based P2P network with quorum-based seed consensus

 Overview
 --------
 This project implements a gossip-style peer-to-peer (P2P) network with
 multiple seed nodes that coordinate membership via quorum consensus.
 The goals are reliable message dissemination, robust liveness detection,
 and consensus-driven membership management so no single node can
 unilaterally add or remove peers.

 Components
 ----------
 - `seed.py`: Seed node implementation. Seeds maintain a Peer List (PL)
	 and run a simple propose/vote/commit quorum protocol for registrations
	 and removals.
 - `peer.py`: Peer node implementation. Peers register with seeds,
	 compute neighbors to approximate a power-law degree distribution,
	 gossip messages, and run liveness checks with peer-level confirmation
	 before reporting dead nodes to seeds.
 - `utils.py`: Utility functions including logger setup and `config.txt`
	 parsing.
 - `test_client.py`: Simple client for manual `REGISTER`, `GET` and
	 `DEAD` messages (useful for quick tests).
 - `run_integration.py`: Automated script to start seeds and peers,
	 simulate a failure, and check logs.
 - `outputfile.txt`: Aggregated log file written by the node loggers.

 Configuration
 -------------
 Seeds are listed in `config.txt` as comma-separated `IP,PORT` per line.
 Example:

 127.0.0.1,5000
 127.0.0.1,5001
 127.0.0.1,5002

 Protocol Summary
 ----------------
 1) Seed Quorum
		- Let n be the number of seeds. Any change (peer add/remove) requires
			a quorum of at least floor(n/2) + 1 seeds to agree.
		- Seeds exchange lightweight JSON proposals and respond with `YES` or `NO`.
		- When the proposer collects quorum `YES` votes it sends a `SEED_COMMIT`
			to other seeds to finalize the change.

 2) Peer Startup & Registration
		- A peer reads `config.txt`, randomly selects k = floor(n/2) + 1 seeds
			and sends `REGISTER` (JSON) to them.
		- Each contacted seed runs the `SEED_PROPOSE` handler; the peer treats
			the registration as successful only after a quorum of seeds votes `YES`.

 3) Peer Join: Peer Lists & Neighbor Selection
		- After registration, the peer requests peer lists (`GET_PEER_LIST`) from
			the seeds it registered with. It unions all returned lists to form a
			candidate set.
		- The peer selects a neighbor degree using an approximate power-law
			(Zipf-like) sampler and chooses peers from the candidate set. This
			yields an overlay whose degree distribution approximates a power law.

 4) Gossip Protocol
		- Each peer periodically generates messages of the form
			`<timestamp>:<ip>:<msg#>` every 5 seconds (max 10 messages).
		- On first receipt, a peer records `hash(msg)` in its Message List (ML)
			and forwards the message to all neighbors except the sender.
		- Duplicates are ignored.

 5) Liveness & Dead-node Reporting
		- Peers periodically (application-level) `PING` neighbors over TCP.
		- On missed replies a peer enters a local suspicion phase and asks its
			neighbors via `SUSPICION` RPC whether *they* can reach the target.
		- If a majority of responding neighbors report inability to reach the
			node, the peer-level consensus marks the node as dead and the reporting
			peer sends a `DEAD_REPORT` to all registered seeds.
		- Seeds then run the same propose/vote/commit quorum protocol before
			removing the peer from their PLs. Removal only occurs when a seed
			quorum is reached.

 Message Formats (JSON)
 ----------------------
 - REGISTER: {"type":"REGISTER","ip":"127.0.0.1","port":6000}
 - GET_PEER_LIST: {"type":"GET_PEER_LIST"}
 - PEER_LIST: {"type":"PEER_LIST","peers":[{"ip":"...","port":...},...]}
 - GOSSIP: {"type":"GOSSIP","msg":"<ts>:<ip>:<#>","origin":{"ip":...,"port":...},"ts":...}
 - SUSPICION: {"type":"SUSPICION","target_ip":"...","target_port":...}
 - SUSPICION_RESPONSE: {"type":"SUSPICION_RESPONSE","can_reach":true|false}
 - DEAD_REPORT: {"type":"DEAD_REPORT","dead_ip":"...","dead_port":...,"reporter":{"ip":...,"port":...},"ts":...}
 - SEED_PROPOSE / SEED_VOTE / SEED_COMMIT: simple JSON objects exchanged among seeds.

 Logging & Output
 ----------------
 - Nodes use `utils.setup_logger` and log to both console and `outputfile.txt`.
 - `run_integration.py` also creates per-process logs in `logs/` (seed_*.log, peer_*.log).
 - Logs show proposals, votes, commits, gossip first-time receipts, suspicion
	 phases, and dead-node removals.

 Running the System (quick)
 -------------------------
 Open separate terminals for each node (or use the integration script).

 Start seeds:
	 python seed.py 5000
	 python seed.py 5001
	 python seed.py 5002

 Start peers:
	 python peer.py 6000
	 python peer.py 6001
	 python peer.py 6002

 Optional automated demo:
	 python run_integration.py

 Tail logs while running:
	 Get-Content outputfile.txt -Tail 200 -Wait


 - Seeds form a quorum (n>1) and log `SEED_PROPOSE` / `SEED_VOTE` / `SEED_COMMIT` events.
 - A new peer registers only after receiving quorum approval from seeds.
 - Peers fetch peer lists and log chosen neighbors (neighbor count follows an
	 approximate power-law selection).
 - Peers generate gossip every 5s (max 10) and other peers log "GOSSIP first-time" entries.
 - On killing a peer process, other peers enter suspicion, perform neighbor
	 checks, and send `DEAD_REPORT` only after peer-level majority confirmation.
 - Seeds remove the peer only after seed-level quorum — look for removal commit logs.


 --------------
 - The system requires two-level consensus (peer-level then seed-level) to
	 reduce false positives and Sybil-style attacks.
 - Known limitations: messages are not cryptographically signed; an attacker
	 controlling a seed majority can still tamper with membership. See README
	 for suggested hardening (signatures, authenticated channels, rate limiting).

 Files to Submit
 ---------------
 - seed.py, peer.py, utils.py, config.txt, outputfile.txt
 - run_integration.py, test_client.py (optional), DEMO.md, SAMPLE_LOGS.txt
 - README.TXT (this file)


-- Files --
- `seed.py` : seed node implementation (consensus for register/remove)
- `peer.py` : peer implementation (registration, gossip, liveness)
- `test_client.py` : simple client to send REGISTER/GET/DEAD commands
- `run_integration.py` : starts multiple seeds/peers and simulates a failure
- `config.txt` : list of seed IP,port pairs
- `outputfile.txt` : shared log file used by all nodes

Please see source files for implementation details and adjust `config.txt` to match your environment.