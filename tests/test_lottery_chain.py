"""Chain-level integration test for the fair-lottery template.

Drives a full round through real blocks (deploy → create_round → buy →
reveal → draw → claim → finalize) so the ``block_hash`` wiring between
:class:`~backend.blockchain.Blockchain` and the contract engine is covered,
not just the engine in isolation.
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend import crypto, pow as pow_mod
from backend.block import Block
from backend.blockchain import Blockchain
from backend.storage import DataPaths
from backend.templates import get_template
from backend.transaction import Transaction, create_coinbase

try:
    crypto.generate_private_key()
    _CRYPTO_OK = True
except Exception:  # pragma: no cover - minimal environments without ECDSA
    _CRYPTO_OK = False

if not _CRYPTO_OK:
    # The crypto backend is unavailable (e.g. missing ``cryptography``); the
    # signature scheme is not what this test exercises, so bypass it.
    Transaction.validate_signature = lambda self: True
    Transaction.derived_sender = lambda self: self.sender

OWNER = "0x" + "a" * 40
BUYER = "0x" + "1" * 40
CODE = get_template("fair_lottery")["source"]


class LotteryChainTest(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp()
        paths = DataPaths(self.root, {})
        paths.ensure()
        self.bc = Blockchain({"INITIAL_DIFFICULTY_BITS": 4}, paths)
        self.bc.create_genesis()
        self.bc.state.set_balance(OWNER, 10_000)
        self.bc.state.set_balance(BUYER, 10_000)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def mine_with(self, txs, height):
        blk = Block(height, self.bc.head.hash,
                    [create_coinbase(OWNER, 50, height)] + txs)
        blk.difficulty = pow_mod.next_difficulty(self.bc, blk)
        blk._recompute_header()
        new_state, receipts = self.bc.apply_block(blk, self.bc.state.copy())
        blk.set_state_root(new_state.root())
        pow_mod.mine(blk, blk.difficulty)
        status, msg = self.bc.add_block(blk)
        self.assertEqual(status, "extended", msg)
        return receipts

    def call_tx(self, sender, contract, fn, args, nonce, value=0):
        return Transaction(sender, contract, value, 0, nonce, "call",
                           data={"function": fn, "args": args})

    def test_full_round_on_chain(self):
        bc = self.bc

        # Deploy at height 1.
        deploy = Transaction(OWNER, None, 0, 0, 0, "deploy",
                             data={"code": CODE, "constructor": []})
        receipts = self.mine_with([deploy], 1)
        self.assertTrue(receipts[1]["ok"], receipts[1]["error"])
        contract = receipts[1]["contract"]

        # Create the round at height 2.
        commit = crypto.sha256_hex(
            f"fair-lottery-v1-commit|1|{OWNER}|opsecret")
        receipts = self.mine_with(
            [self.call_tx(OWNER, contract, "create_round",
                          [10, 1, 5, 8, 20, "rollover", commit], 1)], 2)
        self.assertTrue(receipts[1]["ok"], receipts[1]["error"])

        # Buy 2 tickets at height 3.
        bcommit = crypto.sha256_hex(
            f"fair-lottery-v1-commit|1|{BUYER}|bsalt")
        receipts = self.mine_with(
            [self.call_tx(BUYER, contract, "buy_tickets",
                          [2, bcommit], 0, value=20)], 3)
        self.assertTrue(receipts[1]["ok"], receipts[1]["error"])
        self.assertEqual(bc.state.balance(contract), 20)

        self.mine_with([], 4)
        self.mine_with([], 5)

        # Reveal at height 6 (purchase ended at 5).
        receipts = self.mine_with([
            self.call_tx(BUYER, contract, "reveal", ["bsalt"], 1),
            self.call_tx(OWNER, contract, "operator_reveal", ["opsecret"], 2),
        ], 6)
        self.assertTrue(receipts[1]["ok"], receipts[1]["error"])
        self.assertTrue(receipts[2]["ok"], receipts[2]["error"])

        # Wait out the seed block (8) plus SEED_CONFIRMATIONS (2).
        for h in range(7, 12):
            self.mine_with([], h)

        receipts = self.mine_with(
            [self.call_tx(OWNER, contract, "draw", [], 3)], 12)
        self.assertTrue(receipts[1]["ok"], receipts[1]["error"])
        ret = receipts[1]["return"]
        self.assertEqual(ret["status"], "drawn")
        self.assertEqual(ret["winners"], [BUYER])
        self.assertEqual(ret["winner_share"], 20)

        # The seed committed on-chain must be reproducible from the real
        # block hash at the seed height.
        record = bc.engine.simulate(
            contract, "verification_record", [1], OWNER, bc.state, bc.height,
            block_hash_at=lambda h: (
                bc.get_block(int(h)).hash if bc.get_block(int(h)) else ""))
        self.assertTrue(record["ok"], record["error"])
        self.assertEqual(record["return"]["seed_block_hash"],
                         bc.get_block(8).hash)
        self.assertEqual(record["return"]["seed"], ret["seed"])

        # Claim within the deadline.
        receipts = self.mine_with(
            [self.call_tx(BUYER, contract, "claim", [], 2)], 13)
        self.assertTrue(receipts[1]["ok"], receipts[1]["error"])
        self.assertEqual(receipts[1]["return"], 20)
        self.assertEqual(bc.state.balance(contract), 0)

        # Finalize after the claim deadline.
        for h in range(14, 22):
            self.mine_with([], h)
        receipts = self.mine_with(
            [self.call_tx(OWNER, contract, "finalize_round", [], 4)], 22)
        self.assertTrue(receipts[1]["ok"], receipts[1]["error"])
        self.assertEqual(receipts[1]["return"]["status"], "finalized")


if __name__ == "__main__":
    unittest.main()
