"""End-to-end test of the fair-lottery contract template on a real chain.

Drives a full multi-round lifecycle through actual blocks and transactions:

* deploy with constructor args;
* uniform-price multi-ticket purchases (wrong payment rejected);
* commit-reveal draw: early draw / wrong secret rejected, correct secret
  produces winners that are independently recomputed here with hashlib —
  proving anyone can re-derive the result from public data;
* verify() read-only recomputation matches the on-chain result;
* claim deadline: winners claim, non-winners / double / late claims rejected;
* unclaimed prizes roll into the next round (rollover=1) or are returned
  to the operator (rollover=0);
* operator failing to reveal => round cancelled, buyers fully refunded.

Run:  python3 tests/test_lottery.py
"""

import hashlib
import os
import shutil
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.config import build_config
from backend.node import Node
from backend import pow as pow_mod
from backend.state import ZERO_ADDRESS
from backend.templates import get_template

LOTTERY = get_template("lottery")["source"]

# Constructor args shared by both test contracts.  Windows are generous
# because every (even reverting) transaction is mined into its own block.
PRICE = 10
NUM_WINNERS = 2
SALE_BLOCKS = 10
REVEAL_BLOCKS = 8
CLAIM_BLOCKS = 8


def sha256_hex(s):
    return hashlib.sha256(str(s).encode("utf-8")).hexdigest()


def recompute_winners(rnd, secret, tickets, k):
    """Independent off-chain replica of the contract's public draw rule."""
    n = len(tickets)
    seed = str(rnd) + "|" + str(secret) + "|" + sha256_hex(",".join(tickets))
    idxs = []
    i = 0
    while len(idxs) < k:
        attempt = 0
        while True:
            h = sha256_hex(seed + "|" + str(i) + "|" + str(attempt))
            idx = int(h, 16) % n
            if idx not in idxs:
                idxs.append(idx)
                break
            attempt += 1
        i += 1
    return idxs, [tickets[j] for j in idxs]


def make_node(data_dir):
    args = SimpleNamespace(
        id="lottery-test", port=18999, host="127.0.0.1", peers=None,
        data_dir=data_dir, mine=False, seed=False, mining_interval=None)
    cfg = build_config(args)
    cfg["mine"] = False
    cfg["INITIAL_DIFFICULTY_BITS"] = 1  # keep test mining instant
    # pow.py reads the retarget interval from its module globals, not cfg;
    # with instant back-to-back blocks the adjustment would otherwise keep
    # raising difficulty.  Disable re-targeting for the test chain.
    pow_mod.DIFFICULTY_ADJUST_INTERVAL = 10 ** 9
    node = Node(cfg)
    node.start()
    return node


class LotteryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="lottery-test-")
        cls.node = make_node(cls.tmp)
        cls.miner, _ = cls.node.wallets.create("miner")
        cls.owner, _ = cls.node.wallets.create("owner")
        cls.alice, _ = cls.node.wallets.create("alice")
        cls.bob, _ = cls.node.wallets.create("bob")
        cls.carol, _ = cls.node.wallets.create("carol")
        # Fund every participant with block rewards (50 each block).
        for addr in (cls.owner, cls.alice, cls.bob, cls.carol):
            for _ in range(4):
                cls.node.mine_block(addr)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def mine(self, n=1):
        for _ in range(n):
            status, msg, _ = self.node.mine_block(self.miner)
            self.assertEqual(status, "extended", msg)

    def receipt_of(self, txid):
        for r in self.node.blockchain.last_receipts:
            if r.get("txid") == txid:
                return r
        raise AssertionError("receipt not found for " + txid)

    def call(self, sender, caddr, fn, args=None, value=0):
        """Submit a contract call, mine it, return its receipt."""
        tx, err = self.node.create_call(sender, caddr, fn, args or [],
                                        fee=0, value=value)
        self.assertIsNone(err)
        ok, reason = self.node.submit_transaction(tx)
        self.assertTrue(ok, reason)
        self.mine()
        return self.receipt_of(tx.txid)

    def view(self, caddr, fn, args=None):
        res = self.node.blockchain.engine.simulate(
            caddr, fn, args or [], ZERO_ADDRESS,
            self.node.blockchain.state, self.node.blockchain.height)
        self.assertTrue(res["ok"], res["error"])
        return res["return"]

    def balance(self, addr):
        return self.node.blockchain.state.balance(addr)

    def deploy(self, rollover):
        ctor = [PRICE, NUM_WINNERS, SALE_BLOCKS, REVEAL_BLOCKS,
                CLAIM_BLOCKS, rollover]
        tx, err = self.node.create_deploy(self.owner, LOTTERY, 0,
                                          constructor=ctor)
        self.assertIsNone(err)
        ok, reason = self.node.submit_transaction(tx)
        self.assertTrue(ok, reason)
        self.mine()
        rec = self.receipt_of(tx.txid)
        self.assertTrue(rec["ok"], rec["error"])
        return rec["contract"]

    def wait_until(self, height):
        while self.node.blockchain.height < height:
            self.mine()

    # ------------------------------------------------------------------ #
    # Round 1: draw + public recomputation + rollover of unclaimed prizes
    # ------------------------------------------------------------------ #
    def test_full_lifecycle(self):
        caddr = self.deploy(rollover=1)
        secret1 = "round-1-secret"

        # Only the operator may open a round.
        rec = self.call(self.alice, caddr, "start_round", [sha256_hex(secret1)])
        self.assertFalse(rec["ok"])
        # Malformed commitment rejected.
        rec = self.call(self.owner, caddr, "start_round", ["not-a-hash"])
        self.assertFalse(rec["ok"])
        # No round open yet -> cannot buy.
        rec = self.call(self.alice, caddr, "buy", [1], value=PRICE)
        self.assertFalse(rec["ok"])

        rec = self.call(self.owner, caddr, "start_round", [sha256_hex(secret1)])
        self.assertTrue(rec["ok"], rec["error"])
        info = self.view(caddr, "round_info", [1])
        self.assertEqual(info["status"], "open")
        self.assertEqual(info["pot"], 0)
        sale_end = info["sale_end"]

        # Uniform price, exact payment required.
        rec = self.call(self.alice, caddr, "buy", [2], value=PRICE * 2 - 1)
        self.assertFalse(rec["ok"])                      # underpayment
        rec = self.call(self.alice, caddr, "buy", [2], value=PRICE * 2 + 1)
        self.assertFalse(rec["ok"])                      # overpayment
        rec = self.call(self.alice, caddr, "buy", [0], value=0)
        self.assertFalse(rec["ok"])                      # zero tickets
        # One address may hold many tickets.
        rec = self.call(self.alice, caddr, "buy", [3], value=PRICE * 3)
        self.assertTrue(rec["ok"], rec["error"])
        rec = self.call(self.bob, caddr, "buy", [1], value=PRICE)
        self.assertTrue(rec["ok"], rec["error"])
        rec = self.call(self.carol, caddr, "buy", [2], value=PRICE * 2)
        self.assertTrue(rec["ok"], rec["error"])

        # Cannot draw before sales close; cannot buy after they do.
        rec = self.call(self.owner, caddr, "draw", [secret1])
        self.assertFalse(rec["ok"])
        self.wait_until(sale_end)
        rec = self.call(self.alice, caddr, "buy", [1], value=PRICE)
        self.assertFalse(rec["ok"])                      # sales closed

        # Wrong secret does not match the commitment.
        rec = self.call(self.owner, caddr, "draw", ["wrong-secret"])
        self.assertFalse(rec["ok"])
        # Correct secret opens the draw (anyone may relay it).
        rec = self.call(self.carol, caddr, "draw", [secret1])
        self.assertTrue(rec["ok"], rec["error"])

        info = self.view(caddr, "round_info", [1])
        self.assertEqual(info["status"], "drawn")
        tickets = info["tickets"]
        self.assertEqual(len(tickets), 6)
        self.assertEqual(info["winners"].__len__(), NUM_WINNERS)
        pool = PRICE * 6
        self.assertAlmostEqual(info["prize"], pool / NUM_WINNERS)

        # --- Public verifiability: recompute from chain data alone. ---
        idxs, winners = recompute_winners(1, secret1, tickets, NUM_WINNERS)
        self.assertEqual(winners, info["winners"])
        self.assertEqual(idxs, info["winning_indices"])
        # The contract's own verify() agrees too.
        v = self.view(caddr, "verify", [1])
        self.assertTrue(v["commit_ok"])
        self.assertTrue(v["match"])
        self.assertEqual(v["recomputed_winners"], info["winners"])

        # Nobody claims in round 1 -> whole pool stays unclaimed.
        claim_end = info["claim_end"]
        rec = self.call(self.owner, caddr, "settle")
        self.assertFalse(rec["ok"])                      # claim window open
        self.wait_until(claim_end + 1)
        rec = self.call(self.miner, caddr, "settle")     # anyone may settle
        self.assertTrue(rec["ok"], rec["error"])
        cur = self.view(caddr, "current_round")
        self.assertEqual(cur["status"], "settled")
        self.assertAlmostEqual(cur["carry"], pool)       # rolled over

        # A settled round cannot be settled again / drawn again.
        rec = self.call(self.owner, caddr, "settle")
        self.assertFalse(rec["ok"])
        rec = self.call(self.owner, caddr, "draw", [secret1])
        self.assertFalse(rec["ok"])

        # ---------------- Round 2: rollover pot + claims ---------------- #
        secret2 = "round-2-secret"
        rec = self.call(self.owner, caddr, "start_round", [sha256_hex(secret2)])
        self.assertTrue(rec["ok"], rec["error"])
        info = self.view(caddr, "round_info", [2])
        self.assertAlmostEqual(info["pot"], pool)        # carry enters pot

        rec = self.call(self.alice, caddr, "buy", [1], value=PRICE)
        self.assertTrue(rec["ok"], rec["error"])
        rec = self.call(self.bob, caddr, "buy", [4], value=PRICE * 4)
        self.assertTrue(rec["ok"], rec["error"])
        self.wait_until(info["sale_end"])
        rec = self.call(self.owner, caddr, "draw", [secret2])
        self.assertTrue(rec["ok"], rec["error"])

        info = self.view(caddr, "round_info", [2])
        idxs, winners = recompute_winners(2, secret2, info["tickets"],
                                          NUM_WINNERS)
        self.assertEqual(winners, info["winners"])
        prize = info["prize"]
        self.assertAlmostEqual(prize, (pool + PRICE * 5) / NUM_WINNERS)

        # Non-winner cannot claim.
        winners_set = set(winners)
        non_winner = next(a for a in (self.alice, self.bob, self.carol)
                          if a not in winners_set) if len(winners_set) < 3 \
            else self.owner
        rec = self.call(non_winner, caddr, "claim")
        self.assertFalse(rec["ok"])

        # Each distinct winner claims exactly their slots.
        for w in winners_set:
            slots = winners.count(w)
            before = self.balance(w)
            rec = self.call(w, caddr, "claim")
            self.assertTrue(rec["ok"], rec["error"])
            self.assertAlmostEqual(self.balance(w), before + prize * slots)
            rec = self.call(w, caddr, "claim")           # double claim
            self.assertFalse(rec["ok"])

        # Everything claimed -> nothing rolls over.
        self.wait_until(info["claim_end"] + 1)
        rec = self.call(self.owner, caddr, "settle")
        self.assertTrue(rec["ok"], rec["error"])
        cur = self.view(caddr, "current_round")
        self.assertAlmostEqual(cur["carry"], 0)

        # --------------- Round 3: operator never reveals ---------------- #
        secret3 = "round-3-secret"
        rec = self.call(self.owner, caddr, "start_round", [sha256_hex(secret3)])
        self.assertTrue(rec["ok"], rec["error"])
        info = self.view(caddr, "round_info", [3])
        before = self.balance(self.alice)
        rec = self.call(self.alice, caddr, "buy", [2], value=PRICE * 2)
        self.assertTrue(rec["ok"], rec["error"])
        self.assertAlmostEqual(self.balance(self.alice), before - PRICE * 2)

        # Cannot cancel while the reveal window is still open.
        self.wait_until(info["sale_end"])
        rec = self.call(self.bob, caddr, "cancel_round")
        self.assertFalse(rec["ok"])
        # After the reveal deadline the draw is impossible...
        self.wait_until(info["reveal_end"] + 1)
        rec = self.call(self.owner, caddr, "draw", [secret3])
        self.assertFalse(rec["ok"])
        # ...and anyone may cancel the round.
        rec = self.call(self.bob, caddr, "cancel_round")
        self.assertTrue(rec["ok"], rec["error"])

        # Buyer refunds in full; refunding twice fails.
        rec = self.call(self.alice, caddr, "refund", [3])
        self.assertTrue(rec["ok"], rec["error"])
        self.assertAlmostEqual(self.balance(self.alice), before)
        rec = self.call(self.alice, caddr, "refund", [3])
        self.assertFalse(rec["ok"])
        rec = self.call(self.bob, caddr, "refund", [3])   # never bought
        self.assertFalse(rec["ok"])

        # Round data stays public and auditable after cancellation.
        info = self.view(caddr, "round_info", [3])
        self.assertEqual(info["status"], "cancelled")

    # ------------------------------------------------------------------ #
    # rollover=0: unclaimed prizes return to the operator
    # ------------------------------------------------------------------ #
    def test_unclaimed_returned_to_operator(self):
        caddr = self.deploy(rollover=0)
        secret = "no-rollover-secret"
        rec = self.call(self.owner, caddr, "start_round", [sha256_hex(secret)])
        self.assertTrue(rec["ok"], rec["error"])
        rec = self.call(self.alice, caddr, "buy", [2], value=PRICE * 2)
        self.assertTrue(rec["ok"], rec["error"])
        info = self.view(caddr, "round_info", [1])
        self.wait_until(info["sale_end"])
        rec = self.call(self.owner, caddr, "draw", [secret])
        self.assertTrue(rec["ok"], rec["error"])
        info = self.view(caddr, "round_info", [1])

        # Only one distinct winner claims; the rest of the pool is forfeit.
        winners = info["winners"]
        first = winners[0]
        before_winner = self.balance(first)
        rec = self.call(first, caddr, "claim")
        self.assertTrue(rec["ok"], rec["error"])
        slots = winners.count(first)
        self.assertAlmostEqual(self.balance(first),
                               before_winner + info["prize"] * slots)

        # Late claims are rejected once the deadline passes.
        self.wait_until(info["claim_end"] + 1)
        others = [w for w in set(winners) if w != first]
        if others:
            rec = self.call(others[0], caddr, "claim")
            self.assertFalse(rec["ok"])

        before_owner = self.balance(self.owner)
        rec = self.call(self.owner, caddr, "settle")
        self.assertTrue(rec["ok"], rec["error"])
        unclaimed = info["prize"] * (len(winners) - slots)
        self.assertAlmostEqual(self.balance(self.owner),
                               before_owner + unclaimed)
        cur = self.view(caddr, "current_round")
        self.assertAlmostEqual(cur["carry"], 0)          # nothing rolls over


if __name__ == "__main__":
    unittest.main(verbosity=2)
