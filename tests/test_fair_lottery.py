"""End-to-end tests for the fair-lottery contract template.

The tests drive the real :class:`ContractEngine` against a ``WorldState``
exactly the way ``Blockchain._execute_transaction`` does (credit ``msg.value``
to the contract before invoking, snapshot/revert around failures).
"""

import hashlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.contract import ContractEngine
from backend.state import WorldState
from backend.templates import get_template

OWNER = "0x" + "a" * 40
ALICE = "0x" + "1" * 40
BOB = "0x" + "2" * 40
CAROL = "0x" + "3" * 40
CONTRACT = "0xc" + "f" * 40

CODE = get_template("fair_lottery")["source"]


def commitment(round_id, participant, salt):
    return hashlib.sha256(
        f"fair-lottery-v1-commit|{round_id}|{participant}|{salt}".encode()
    ).hexdigest()


class LotteryHarness:
    def __init__(self):
        self.ws = WorldState()
        self.engine = ContractEngine({})
        for addr in (OWNER, ALICE, BOB, CAROL):
            self.ws.set_balance(addr, 100_000)
        self.height = 1
        result = self.engine.deploy(CODE, OWNER, CONTRACT, self.ws,
                                    constructor=[], height=self.height,
                                    block_hash_at=self.block_hash_at)
        assert result["ok"], result["error"]

    def block_hash_at(self, h):
        h = int(h)
        if h < 0 or h >= self.height:
            return ""
        return f"{h:064x}"

    def call(self, fn, args, sender, value=0, height=None, expect_ok=True):
        height = self.height if height is None else height
        before = self.ws.copy()
        if value:
            self.ws.add_balance(sender, -value)
            self.ws.add_balance(CONTRACT, value)
        result = self.engine.invoke(CONTRACT, fn, list(args), sender, value,
                                    self.ws, height=height,
                                    block_hash_at=self.block_hash_at)
        if expect_ok:
            assert result["ok"], result["error"]
        else:
            assert not result["ok"]
            self.ws.accounts = before.accounts
            self.ws.contracts = before.contracts
        return result

    def read(self, fn, args, sender=OWNER):
        return self.engine.simulate(CONTRACT, fn, list(args), sender,
                                    self.ws, height=self.height,
                                    block_hash_at=self.block_hash_at)

    def balance(self, addr):
        return self.ws.balance(addr)


class FairLotteryTest(unittest.TestCase):
    def make_round(self, h, mode="rollover", price=10, winners=2,
                   purchase_end=20, reveal_end=25, claim_deadline=40):
        h.height = 10
        op_commit = commitment(1, OWNER, "operator-secret")
        result = h.call("create_round",
                        [price, winners, purchase_end, reveal_end,
                         claim_deadline, mode, op_commit], OWNER)
        return result["return"]

    def buy(self, h, buyer, count, salt, round_id=1):
        commit = commitment(round_id, buyer, salt)
        return h.call("buy_tickets", [count, commit], buyer,
                      value=count * 10)

    def test_full_lifecycle_rollover(self):
        h = LotteryHarness()
        round_id = self.make_round(h)
        self.assertEqual(round_id, 1)

        # Wrong payment is rejected and reverted.
        bad = commitment(1, ALICE, "s1")
        h.call("buy_tickets", [1, bad], ALICE, value=9, expect_ok=False)
        self.assertEqual(h.balance(CONTRACT), 0)

        # One address may buy many tickets; probability is weighted by tickets.
        self.buy(h, ALICE, 5, "alice-salt")
        self.buy(h, ALICE, 5, "alice-salt")   # same commitment, more tickets
        self.buy(h, BOB, 3, "bob-salt")
        self.buy(h, CAROL, 2, "carol-salt")
        info = h.read("current_round", [])["return"]
        self.assertEqual(info["sold"], 15)
        self.assertEqual(info["prize_pool"], 150)
        self.assertEqual(h.balance(CONTRACT), 150)

        # Changing the commitment mid-round is rejected.
        other = commitment(1, ALICE, "different")
        h.call("buy_tickets", [1, other], ALICE, value=10, expect_ok=False)

        # Reveal phase: wrong salt rejected, correct salts accepted.
        h.height = 21
        h.call("reveal", ["wrong"], ALICE, expect_ok=False)
        h.call("reveal", ["alice-salt"], ALICE)
        h.call("reveal", ["bob-salt"], BOB)
        h.call("reveal", ["carol-salt"], CAROL)
        h.call("operator_reveal", ["operator-secret"], OWNER)
        h.call("operator_reveal", ["wrong"], OWNER, expect_ok=False)

        # Draw is impossible before the seed block has enough confirmations.
        h.height = 25
        h.call("draw", [], OWNER, expect_ok=False)
        h.height = 27  # seed block (25) + 2 confirmations required
        h.call("draw", [], OWNER, expect_ok=False)
        h.height = 28
        result = h.call("draw", [], ALICE)  # anyone may trigger
        drawn = result["return"]
        self.assertEqual(drawn["status"], "drawn")
        winners = drawn["winners"]
        self.assertEqual(len(winners), 2)
        self.assertEqual(len(set(winners)), 2)  # one address, one prize

        # The result is publicly recomputable from the revealed record.
        replay = h.read("replay_winners", [1])["return"]
        self.assertEqual(replay, winners)
        record = h.read("verification_record", [1])["return"]
        self.assertEqual(record["seed"], drawn["seed"])
        self.assertEqual(record["seed_block_hash"], f"{25:064x}")
        self.assertEqual(record["winners"], winners)

        # Non-winners cannot claim; winners claim within the deadline.
        loser = next(a for a in (ALICE, BOB, CAROL) if a not in winners)
        h.call("claim", [], loser, expect_ok=False)
        share = drawn["winner_share"]
        self.assertEqual(share, 150 // 2)
        first = winners[0]
        before = h.balance(first)
        h.call("claim", [], first)
        self.assertEqual(h.balance(first), before + share)
        h.call("claim", [], first, expect_ok=False)  # no double claim

        # Deadline not reached yet: cannot finalize.
        h.call("finalize_round", [], OWNER, expect_ok=False)

        # After the deadline, the unclaimed share rolls into the reserve.
        h.height = 41
        h.call("finalize_round", [], BOB)
        self.assertEqual(h.read("reserve", [])["return"], share)

        # A new round can start; the reserve seeds its prize pool.
        op_commit2 = commitment(2, OWNER, "op2")
        h.call("create_round", [10, 1, 50, 55, 70, "rollover", op_commit2],
               OWNER)
        info = h.read("current_round", [])["return"]
        self.assertEqual(info["reserve_contribution"], share)
        self.assertEqual(info["prize_pool"], share)

    def test_refund_mode_returns_unclaimed_to_losers(self):
        h = LotteryHarness()
        self.make_round(h, mode="refund", winners=1)
        self.buy(h, ALICE, 2, "a")
        self.buy(h, BOB, 3, "b")
        self.buy(h, CAROL, 5, "c")
        h.height = 21
        for who, salt in ((ALICE, "a"), (BOB, "b"), (CAROL, "c")):
            h.call("reveal", [salt], who)
        h.call("operator_reveal", ["operator-secret"], OWNER)
        h.height = 28
        drawn = h.call("draw", [], OWNER)["return"]
        winner = drawn["winners"][0]
        # Winner never claims -> entire pot is refunded pro-rata to losers.
        h.height = 41
        balances_before = {a: h.balance(a) for a in (ALICE, BOB, CAROL)}
        h.call("finalize_round", [], OWNER)
        losers = [a for a in (ALICE, BOB, CAROL) if a != winner]
        tickets = {ALICE: 2, BOB: 3, CAROL: 5}
        losing_total = sum(tickets[a] for a in losers)
        pot = 100
        # Pro-rata payouts use integer division; only dust (one coin per loser
        # at most) may remain in the contract, retained as reserve.
        dust = h.balance(CONTRACT)
        self.assertGreaterEqual(dust, 0)
        self.assertLessEqual(dust, losing_total)
        self.assertEqual(h.read("reserve", [])["return"], dust)
        gained = sum(h.balance(a) - balances_before[a] for a in losers)
        self.assertEqual(h.balance(winner), balances_before[winner])
        # Pro-rata payouts plus integer dust must account for the full pot.
        self.assertEqual(gained + int(dust), pot)
        for a in losers:
            expect = (pot * tickets[a]) // losing_total
            self.assertEqual(h.balance(a) - balances_before[a], expect)

    def test_operator_no_reveal_cancels_and_refunds(self):
        h = LotteryHarness()
        self.make_round(h)
        self.buy(h, ALICE, 4, "a")
        self.buy(h, BOB, 6, "b")
        h.height = 21
        h.call("reveal", ["a"], ALICE)
        h.call("reveal", ["b"], BOB)
        # Operator never reveals -> draw cancels and refunds everyone.
        h.height = 28
        before_a, before_b = h.balance(ALICE), h.balance(BOB)
        result = h.call("draw", [], OWNER)["return"]
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(h.balance(ALICE), before_a + 40)
        self.assertEqual(h.balance(BOB), before_b + 60)
        self.assertEqual(h.balance(CONTRACT), 0)
        info = h.read("get_round", [1])["return"]
        self.assertEqual(info["status"], "cancelled")

    def test_no_buyer_reveal_cancels(self):
        h = LotteryHarness()
        self.make_round(h)
        self.buy(h, ALICE, 2, "a")
        self.buy(h, BOB, 2, "b")
        h.height = 21
        h.call("operator_reveal", ["operator-secret"], OWNER)
        h.height = 28
        result = h.call("draw", [], OWNER)["return"]
        self.assertEqual(result["status"], "cancelled")
        self.assertEqual(result["reason"], "no_buyer_reveal")

    def test_insufficient_participants_cancels(self):
        h = LotteryHarness()
        self.make_round(h, winners=3)
        self.buy(h, ALICE, 2, "a")
        self.buy(h, BOB, 2, "b")
        h.height = 21
        h.call("reveal", ["a"], ALICE)
        h.call("reveal", ["b"], BOB)
        h.call("operator_reveal", ["operator-secret"], OWNER)
        h.height = 28
        result = h.call("draw", [], OWNER)["return"]
        self.assertEqual(result["reason"], "not_enough_participants")

    def test_only_owner_can_create_round(self):
        h = LotteryHarness()
        h.height = 10
        h.call("create_round", [10, 1, 20, 25, 40, "rollover", "x" * 64],
               ALICE, expect_ok=False)

    def test_weighted_selection_respects_ticket_share(self):
        """Chi-bin sanity check without re-executing a full round each draw.

        ``select_winners`` itself is pure; we call it through one deployed
        contract with many explicit seed overrides and check the empirical
        frequency tracks the 1:3 ticket weights.
        """
        h = LotteryHarness()
        self.make_round(h, winners=1)
        self.buy(h, ALICE, 1, "a")
        self.buy(h, BOB, 3, "b")

        counts = {ALICE: 0, BOB: 0}
        for n in range(600):
            seed = hashlib.sha256(f"probe-{n}".encode()).hexdigest()
            winner = h.read("replay_winners", [1, seed])["return"][0]
            counts[winner] += 1

        share_a = counts[ALICE] / 600
        share_b = counts[BOB] / 600
        self.assertAlmostEqual(share_a, 0.25, delta=0.06)
        self.assertAlmostEqual(share_b, 0.75, delta=0.06)
        self.assertEqual(counts[ALICE] + counts[BOB], 600)

        # Both addresses can win (not biased to a fixed winner).
        self.assertGreater(counts[ALICE], 0)
        self.assertGreater(counts[BOB], 0)


if __name__ == "__main__":
    unittest.main()
