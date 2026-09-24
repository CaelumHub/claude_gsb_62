"""Built-in smart-contract templates for the template library.

Each template is a complete, sandbox-valid contract written against the
contract API (``state``, ``msg``, ``emit``, ``require``, ``transfer``,
``balance_of``).  They are exposed on the template-library page and can be
deployed with one click.
"""

TEMPLATES = [
    {
        "name": "token",
        "title": "可替代代币 (ERC-20 风格)",
        "category": "金融",
        "description": "发行一种可转账的代币，包含铸造、转账、余额查询与总量查询。",
        "constructor": [
            {"name": "name", "type": "string", "desc": "代币名称"},
            {"name": "symbol", "type": "string", "desc": "代币符号"},
            {"name": "supply", "type": "int", "desc": "初始发行量"},
        ],
        "functions": [
            {"name": "transfer", "desc": "向指定地址转账", "params": ["to", "amount"]},
            {"name": "balance_of", "desc": "查询某地址余额", "params": ["addr"]},
            {"name": "total_supply", "desc": "查询代币总量", "params": []},
        ],
        "source": '''# 可替代代币模板 (ERC-20 风格)
def init(name, symbol, supply):
    require(state.get("name") is None, "合约已初始化")
    state["name"] = name
    state["symbol"] = symbol
    state["total_supply"] = supply
    state["bal_" + msg.sender] = supply
    emit("Minted", to=msg.sender, amount=supply)

def transfer(to, amount):
    amount = int(amount)
    require(amount > 0, "转账金额必须为正")
    bal = state.get("bal_" + msg.sender, 0)
    require(bal >= amount, "余额不足")
    state["bal_" + msg.sender] = bal - amount
    state["bal_" + to] = state.get("bal_" + to, 0) + amount
    emit("Transfer", frm=msg.sender, to=to, amount=amount)

def balance_of(addr):
    return state.get("bal_" + addr, 0)

def total_supply():
    return state.get("total_supply", 0)
''',
    },
    {
        "name": "kv_store",
        "title": "键值存储",
        "category": "存储",
        "description": "一个简单的持久化键值对存储，支持写入与读取。",
        "constructor": [],
        "functions": [
            {"name": "set", "desc": "写入键值", "params": ["key", "value"]},
            {"name": "get", "desc": "读取键值", "params": ["key"]},
        ],
        "source": '''# 键值存储模板
def init():
    state["owner"] = msg.sender
    state["count"] = 0
    emit("Initialized", owner=msg.sender)

def set(key, value):
    key = str(key)
    require(key != "", "键不能为空")
    state[key] = value
    state["count"] = state.get("count", 0) + 1
    emit("Set", key=key, value=value, by=msg.sender)

def get(key):
    return state.get(str(key), None)
''',
    },
    {
        "name": "voting",
        "title": "投票合约",
        "category": "治理",
        "description": "创建候选人、投票、查看票数。每个地址限投一次。",
        "constructor": [
            {"name": "candidates", "type": "list", "desc": "候选人列表，如 ['Alice','Bob']"},
        ],
        "functions": [
            {"name": "vote", "desc": "给候选人投票", "params": ["candidate"]},
            {"name": "tally", "desc": "查询候选人票数", "params": ["candidate"]},
        ],
        "source": '''# 投票合约模板
def init(candidates):
    require(state.get("owner") is None, "已初始化")
    state["owner"] = msg.sender
    state["candidates"] = list(candidates)
    for c in candidates:
        state["vote_" + str(c)] = 0
    emit("Created", candidates=candidates)

def vote(candidate):
    require(str(candidate) in state.get("candidates", []), "候选人不存在")
    require(state.get("voted_" + msg.sender, False) is False, "已投过票")
    state["voted_" + msg.sender] = True
    state["vote_" + str(candidate)] = state.get("vote_" + str(candidate), 0) + 1
    emit("Voted", voter=msg.sender, candidate=str(candidate))

def tally(candidate):
    return state.get("vote_" + str(candidate), 0)
''',
    },
    {
        "name": "escrow",
        "title": "托管合约",
        "category": "金融",
        "description": "买家存入资金，买家确认后资金释放给卖家，买家可申请退款。",
        "constructor": [
            {"name": "seller", "type": "address", "desc": "卖家地址"},
        ],
        "functions": [
            {"name": "deposit", "desc": "买家存入资金", "params": []},
            {"name": "release", "desc": "买家确认放款给卖家", "params": []},
            {"name": "refund", "desc": "买家申请退款", "params": []},
            {"name": "amount", "desc": "查询托管金额", "params": []},
        ],
        "source": '''# 托管合约模板
def init(seller):
    require(state.get("seller") is None, "已初始化")
    state["seller"] = seller
    state["buyer"] = msg.sender
    state["amount"] = 0
    state["released"] = False
    emit("Created", seller=seller, buyer=msg.sender)

def deposit():
    require(msg.sender == state["buyer"], "只有买家可存入")
    require(state["released"] is False, "合约已结束")
    state["amount"] = state.get("amount", 0) + msg.value
    emit("Deposited", by=msg.sender, amount=msg.value)

def release():
    require(msg.sender == state["buyer"], "只有买家可确认放款")
    require(state["released"] is False, "已放款")
    state["released"] = True
    transfer(state["seller"], state["amount"])
    emit("Released", seller=state["seller"], amount=state["amount"])

def refund():
    require(msg.sender == state["buyer"], "只有买家可退款")
    require(state["released"] is False, "已放款")
    state["released"] = True
    transfer(state["buyer"], state["amount"])
    emit("Refunded", buyer=state["buyer"], amount=state["amount"])

def amount():
    return state.get("amount", 0)
''',
    },
    {
        "name": "auction",
        "title": "拍卖合约",
        "category": "金融",
        "description": "英式拍卖：出价必须高于当前最高价，拍卖结束后最高出价者胜出。",
        "constructor": [
            {"name": "item", "type": "string", "desc": "拍卖品名称"},
            {"name": "starting_price", "type": "int", "desc": "起拍价"},
            {"name": "end_height", "type": "int", "desc": "结束区块高度"},
        ],
        "functions": [
            {"name": "bid", "desc": "出价（需附带 value）", "params": []},
            {"name": "highest_bidder", "desc": "查询最高出价者", "params": []},
            {"name": "highest_bid", "desc": "查询最高出价", "params": []},
        ],
        "source": '''# 拍卖合约模板
def init(item, starting_price, end_height):
    require(state.get("item") is None, "已初始化")
    state["item"] = item
    state["highest_bid"] = int(starting_price)
    state["highest_bidder"] = msg.sender
    state["end_height"] = int(end_height)
    state["ended"] = False
    emit("AuctionCreated", item=item, start=int(starting_price))

def bid():
    require(block_height < state["end_height"], "拍卖已结束")
    require(msg.value > state["highest_bid"], "出价必须高于当前最高价")
    prev_bidder = state["highest_bidder"]
    prev_bid = state["highest_bid"]
    # 退回上一出价人
    transfer(prev_bidder, prev_bid)
    state["highest_bid"] = msg.value
    state["highest_bidder"] = msg.sender
    emit("Bid", bidder=msg.sender, amount=msg.value)

def highest_bidder():
    return state["highest_bidder"]

def highest_bid():
    return state["highest_bid"]
''',
    },
    {
        "name": "crowdfunding",
        "title": "众筹合约",
        "category": "金融",
        "description": "众筹目标金额，支持出资与查询进度，达到目标后项目方可提现。",
        "constructor": [
            {"name": "goal", "type": "int", "desc": "众筹目标金额"},
        ],
        "functions": [
            {"name": "contribute", "desc": "出资（需附带 value）", "params": []},
            {"name": "progress", "desc": "查询已筹金额", "params": []},
            {"name": "withdraw", "desc": "项目方提现（需达到目标）", "params": []},
        ],
        "source": '''# 众筹合约模板
def init(goal):
    require(state.get("owner") is None, "已初始化")
    state["owner"] = msg.sender
    state["goal"] = int(goal)
    state["raised"] = 0
    state["withdrawn"] = False
    emit("CampaignStarted", goal=int(goal))

def contribute():
    require(state["withdrawn"] is False, "众筹已结束")
    state["raised"] = state.get("raised", 0) + msg.value
    state["contrib_" + msg.sender] = state.get("contrib_" + msg.sender, 0) + msg.value
    emit("Contribution", from_=msg.sender, amount=msg.value)

def progress():
    return state.get("raised", 0)

def withdraw():
    require(msg.sender == state["owner"], "只有项目方可提现")
    require(state["raised"] >= state["goal"], "未达到众筹目标")
    require(state["withdrawn"] is False, "已提现")
    state["withdrawn"] = True
    transfer(state["owner"], state["raised"])
    emit("Withdrawn", amount=state["raised"])
''',
    },
    {
        "name": "fair_lottery",
        "title": "多名额公平抽奖（Commit-Reveal + 可复算）",
        "category": "金融",
        "description": "统一年价、多买多中概率；多名中奖者、链上抽签、公开种子与算法可复算，中奖者需在期限内领取，逾期奖金可退回或滚入下一轮。",
        "constructor": [],
        "functions": [
            {"name": "create_round", "desc": "运营方创建新一轮并提交开奖承诺", "params": ["ticket_price", "winner_count", "purchase_end", "reveal_end", "claim_deadline", "unclaimed_mode", "operator_commitment"]},
            {"name": "commitment", "desc": "按链下盐值计算购票承诺", "params": ["round_id", "participant", "salt"]},
            {"name": "buy_tickets", "desc": "按统一价格购买多张票（需附带票款）", "params": ["count", "commitment"]},
            {"name": "reveal", "desc": "购票者公布盐值", "params": ["salt"]},
            {"name": "operator_reveal", "desc": "运营方公布开奖盐值", "params": ["salt"]},
            {"name": "draw", "desc": "在揭示期结束后公开开奖", "params": []},
            {"name": "claim", "desc": "中奖者在领奖期限内领取奖金", "params": []},
            {"name": "finalize_round", "desc": "逾期后结算未领奖金", "params": []},
            {"name": "verification_record", "desc": "导出复算抽签所需的全部公开记录", "params": ["round_id"]},
        ],
        "source": '''# 多名额公平抽奖合约（fair-lottery-v1）
#
# 开奖随机数 = SHA256(协议域 || 合约 || 轮次 || 运营方 reveal
#                 || 所有购票者 reveal（按地址排序）|| 购票结束区块哈希)
# 运营方在售票前先提交哈希承诺；购票者也在购票时提交承诺。所有盐值必须在
# “种子区块”之前公开，随后才使用该未来区块哈希。运营方不能在售票后改盐，
# 矿工不能单独选择未来区块哈希，任何人都可用 verification_record() 公布的
# 记录和 replay_winners() 重新算出结果。

LOTTERY_VERSION = "fair-lottery-v1"
MODE_ROLLOVER = "rollover"
MODE_REFUND = "refund"
# 开奖必须等待种子区块再确认若干个区块，降低短重组改变开奖结果的风险。
SEED_CONFIRMATIONS = 2


def init():
    require(state.get("owner") is None, "合约已初始化")
    state["owner"] = msg.sender
    state["round_count"] = 0
    state["active_round"] = 0
    state["reserve"] = 0
    emit("LotteryInitialized", owner=msg.sender, version=LOTTERY_VERSION)


def commitment(round_id, participant, salt):
    """购票者/运营方承诺的公开计算公式，可在提交前只读调用。"""
    return sha256_hex(
        LOTTERY_VERSION + "-commit|" + str(round_id) + "|"
        + str(participant) + "|" + str(salt))


def next_round_id():
    return int(state.get("round_count", 0)) + 1


def reserve():
    return int(state.get("reserve", 0))


def get_round(round_id):
    round_id = int(round_id)
    r = state.get("round_" + str(round_id))
    require(r is not None, "轮次不存在")
    return r


def current_round():
    round_id = int(state.get("active_round", 0))
    require(round_id > 0, "没有进行中的轮次")
    return get_round(round_id)


def create_round(ticket_price, winner_count, purchase_end, reveal_end,
                 claim_deadline, unclaimed_mode, operator_commitment):
    require(msg.sender == state["owner"], "只有运营方可以创建轮次")
    require(msg.value == 0, "创建轮次不需要转账")
    require(int(state.get("active_round", 0)) == 0, "上一轮尚未结算")

    ticket_price = int(ticket_price)
    winner_count = int(winner_count)
    purchase_end = int(purchase_end)
    reveal_end = int(reveal_end)
    claim_deadline = int(claim_deadline)
    unclaimed_mode = str(unclaimed_mode)

    require(ticket_price > 0, "票价必须为正整数")
    require(winner_count > 0, "中奖名额必须大于 0")
    require(block_height < purchase_end, "购票截止高度必须在未来")
    require(purchase_end < reveal_end, "揭示期必须晚于购票截止")
    require(reveal_end < claim_deadline, "领奖截止必须晚于揭示截止")
    require(unclaimed_mode == MODE_ROLLOVER or unclaimed_mode == MODE_REFUND,
            "逾期处理模式只能是 rollover 或 refund")
    operator_commitment = str(operator_commitment)
    require(len(operator_commitment) == 64, "运营方承诺必须是 64 位哈希")

    round_id = int(state.get("round_count", 0)) + 1
    reserve_contribution = int(state.get("reserve", 0))
    r = {
        "id": round_id,
        "ticket_price": ticket_price,
        "winner_count": winner_count,
        "purchase_end": purchase_end,
        "reveal_end": reveal_end,
        "claim_deadline": claim_deadline,
        "unclaimed_mode": unclaimed_mode,
        "operator_commitment": operator_commitment,
        "operator_salt": "",
        "status": "open",
        "buyers": [],
        "tickets": {},
        "commitments": {},
        "revealed": {},
        "sold": 0,
        "prize_pool": reserve_contribution,
        "reserve_contribution": reserve_contribution,
        "seed_block": reveal_end,
        "seed": "",
        "winners": [],
        "winner_share": 0,
        "claimed": {},
        "drawn_height": -1,
    }
    state["round_" + str(round_id)] = r
    state["round_count"] = round_id
    state["active_round"] = round_id
    state["reserve"] = 0
    emit("RoundCreated", round_id=round_id, ticket_price=ticket_price,
         winner_count=winner_count, purchase_end=purchase_end,
         reveal_end=reveal_end, claim_deadline=claim_deadline,
         unclaimed_mode=unclaimed_mode,
         operator_commitment=operator_commitment,
         reserve_contribution=reserve_contribution)
    return round_id


def buy_tickets(count, buyer_commitment):
    r = current_round()
    require(r["status"] == "open", "本轮不在售票阶段")
    require(block_height < int(r["purchase_end"]), "售票已截止")
    count = int(count)
    require(count > 0, "购票数量必须为正")

    price = int(r["ticket_price"])
    required = price * count
    require(int(msg.value) == msg.value, "票款必须是整数")
    require(msg.value == required, "必须按统一票价精确支付")

    buyer_commitment = str(buyer_commitment)
    require(len(buyer_commitment) == 64, "购票承诺必须是 64 位哈希")
    old_commitment = r["commitments"].get(msg.sender)
    if old_commitment is None:
        r["buyers"].append(msg.sender)
        r["tickets"][msg.sender] = count
        r["commitments"][msg.sender] = buyer_commitment
    else:
        require(old_commitment == buyer_commitment, "同一地址本轮只能使用一个承诺")
        r["tickets"][msg.sender] = int(r["tickets"][msg.sender]) + count

    r["sold"] = int(r["sold"]) + count
    r["prize_pool"] = int(r["prize_pool"]) + required
    emit("TicketsPurchased", round_id=r["id"], buyer=msg.sender,
         count=count, total_tickets=int(r["tickets"][msg.sender]),
         paid=required, commitment=buyer_commitment)
    return int(r["tickets"][msg.sender])


def _enter_reveal_phase(r):
    if r["status"] == "open":
        require(block_height >= int(r["purchase_end"]), "购票尚未截止")
        r["status"] = "revealing"
    require(r["status"] == "revealing", "本轮不在揭示阶段")
    require(block_height < int(r["reveal_end"]), "揭示期已结束")


def reveal(salt):
    r = current_round()
    _enter_reveal_phase(r)
    commit = r["commitments"].get(msg.sender)
    require(commit is not None, "该地址本轮未购票")
    require(commit == commitment(r["id"], msg.sender, salt), "盐值与购票承诺不匹配")
    if r["revealed"].get(msg.sender) is None:
        r["revealed"][msg.sender] = str(salt)
        emit("SaltRevealed", round_id=r["id"], participant=msg.sender,
             salt=str(salt))
    return True


def operator_reveal(salt):
    r = current_round()
    _enter_reveal_phase(r)
    require(msg.sender == state["owner"], "只有运营方可以公布运营盐值")
    expected = r["operator_commitment"]
    require(expected == commitment(r["id"], state["owner"], salt),
            "运营盐值与预先承诺不匹配")
    r["operator_salt"] = str(salt)
    emit("OperatorSaltRevealed", round_id=r["id"], salt=str(salt))
    return True


def build_weight_tree(weights):
    tree = [0]
    for w in weights:
        tree.append(int(w))
    n = len(weights)
    i = 1
    while i <= n:
        parent = i + (i & -i)
        if parent <= n:
            tree[parent] = int(tree[parent]) + int(tree[i])
        i = i + 1
    return tree


def fenwick_prefix(tree, index):
    total = 0
    i = int(index)
    while i > 0:
        total = total + int(tree[i])
        i = i - (i & -i)
    return total


def fenwick_add(tree, index, delta):
    i = int(index)
    n = len(tree) - 1
    while i <= n:
        tree[i] = int(tree[i]) + delta
        i = i + (i & -i)


def uniform_index(total, seed, slot):
    """Rejection-sampled uniform index; avoids modulo bias."""
    total = int(total)
    require(total > 0, "没有可抽选票券")
    modulus = 2 ** 256
    limit = modulus - (modulus % total)
    guard = 0
    while guard < 1000:
        digest = sha256_hex(str(seed) + "|u|" + str(slot) + "|" + str(guard))
        value = int(digest, 16)
        if value < limit:
            return value % total
        guard = guard + 1
    require(False, "随机数采样失败")


def select_winners(r, seed):
    """按票数加权、地址不可重复中奖的确定性无替换抽样。"""
    addresses = sorted(r["buyers"])
    weights = [int(r["tickets"][addr]) for addr in addresses]
    tree = build_weight_tree(weights)
    remaining = int(r["sold"])
    winner_count = min(int(r["winner_count"]), len(addresses))
    winners = []
    slot = 0
    while slot < winner_count:
        rank = uniform_index(remaining, seed, slot) + 1
        lo = 1
        hi = len(addresses)
        while lo < hi:
            mid = (lo + hi) // 2
            if fenwick_prefix(tree, mid) >= rank:
                hi = mid
            else:
                lo = mid + 1
        chosen_index = lo - 1
        winners.append(addresses[chosen_index])
        fenwick_add(tree, lo, -weights[chosen_index])
        remaining = remaining - weights[chosen_index]
        slot = slot + 1
    return winners


def compute_seed(r):
    require(len(str(r.get("operator_salt", ""))) > 0, "运营方尚未 reveal")
    require(len(r.get("revealed", {})) > 0, "没有购票者 reveal")
    seed_hash = block_hash(int(r["seed_block"]))
    require(len(seed_hash) == 64, "种子区块哈希尚不可用")
    material = [LOTTERY_VERSION, msg.address, str(r["id"]),
                "operator:" + str(r["operator_salt"])]
    for addr in sorted(r["revealed"].keys()):
        material.append(str(addr) + ":" + str(r["revealed"][addr]))
    material.append("block:" + seed_hash)
    return sha256_hex("\\x1f".join(material))


def _cancel_round(r, reason):
    """失败开奖：全额退票，原滚存奖金仍保留下一轮使用。"""
    for addr in sorted(r["buyers"]):
        refund = int(r["tickets"][addr]) * int(r["ticket_price"])
        transfer(addr, refund)
    state["reserve"] = int(state.get("reserve", 0)) + int(r["reserve_contribution"])
    r["status"] = "cancelled"
    state["active_round"] = 0
    emit("RoundCancelled", round_id=r["id"], reason=reason,
         refunded=int(r["sold"]) * int(r["ticket_price"]),
         reserve_kept=int(r["reserve_contribution"]))


def draw():
    r = current_round()
    require(r["status"] == "open" or r["status"] == "revealing", "本轮已开奖或已结算")
    require(block_height > int(r["reveal_end"]) + SEED_CONFIRMATIONS,
            "种子区块尚未得到足够确认")
    require(msg.value == 0, "开奖不需要转账")

    if len(str(r.get("operator_salt", ""))) == 0:
        _cancel_round(r, "operator_not_revealed")
        return {"status": "cancelled", "reason": "operator_not_revealed"}
    if len(r.get("revealed", {})) == 0:
        _cancel_round(r, "no_buyer_reveal")
        return {"status": "cancelled", "reason": "no_buyer_reveal"}
    if len(r["buyers"]) < int(r["winner_count"]):
        _cancel_round(r, "not_enough_participants")
        return {"status": "cancelled", "reason": "not_enough_participants"}

    seed = compute_seed(r)
    winners = select_winners(r, seed)
    prize_pool = int(r["prize_pool"])
    share = prize_pool // len(winners)
    require(share > 0, "每份奖金必须为正")

    r["seed"] = seed
    r["winners"] = winners
    r["winner_share"] = share
    r["drawn_height"] = block_height
    r["status"] = "drawn"
    for addr in winners:
        r["claimed"][addr] = False

    emit("DrawCompleted", round_id=r["id"], seed=seed,
         seed_block=int(r["seed_block"]),
         seed_block_hash=block_hash(int(r["seed_block"])),
         winners=winners, winner_share=share, prize_pool=prize_pool,
         algorithm="weighted_fenwick_without_replacement;sha256_rejection_sampling")
    return {"status": "drawn", "seed": seed, "winners": winners,
            "winner_share": share}


def claim():
    r = current_round()
    require(r["status"] == "drawn", "本轮不在领奖阶段")
    require(block_height <= int(r["claim_deadline"]), "领奖期限已过")
    require(r["claimed"].get(msg.sender, None) is False, "不是未领奖的中奖者")
    share = int(r["winner_share"])
    r["claimed"][msg.sender] = True
    transfer(msg.sender, share)
    emit("PrizeClaimed", round_id=r["id"], winner=msg.sender, amount=share,
         height=block_height)
    return share


def finalize_round():
    r = current_round()
    require(r["status"] == "drawn", "本轮尚未开奖")
    require(block_height > int(r["claim_deadline"]), "领奖期限尚未结束")
    require(msg.value == 0, "结算不需要转账")

    unclaimed = 0
    for addr in r["winners"]:
        if r["claimed"].get(addr, False) is False:
            unclaimed = unclaimed + int(r["winner_share"])

    refund_count = 0
    if r["unclaimed_mode"] == MODE_REFUND:
        winner_set = set(r["winners"])
        losing_tickets = 0
        for addr in r["buyers"]:
            if addr not in winner_set:
                losing_tickets = losing_tickets + int(r["tickets"][addr])
        if losing_tickets > 0:
            distributable = int(this_balance())
            for addr in sorted(r["buyers"]):
                if addr not in winner_set:
                    payout = (distributable * int(r["tickets"][addr])) // losing_tickets
                    if payout > 0:
                        transfer(addr, payout)
                        refund_count = refund_count + 1

    state["reserve"] = int(this_balance())
    r["status"] = "finalized"
    state["active_round"] = 0
    emit("RoundFinalized", round_id=r["id"], unclaimed=unclaimed,
         unclaimed_mode=r["unclaimed_mode"], refund_transfers=refund_count,
         reserve=int(state["reserve"]))
    return {"status": "finalized", "unclaimed": unclaimed,
            "reserve": int(state["reserve"])}


def ticket_count(round_id, address):
    r = get_round(round_id)
    return int(r["tickets"].get(address, 0))


def winners(round_id):
    return get_round(round_id).get("winners", [])


def replay_winners(round_id, seed_override=None):
    """离线复算入口：不传 seed 时按链上 reveal 记录重新构造。"""
    r = get_round(round_id)
    seed = str(seed_override) if seed_override is not None else compute_seed(r)
    return select_winners(r, seed)


def verification_record(round_id):
    r = get_round(round_id)
    seed_block_hash = block_hash(int(r["seed_block"]))
    return {
        "version": LOTTERY_VERSION,
        "round_id": r["id"],
        "ticket_price": r["ticket_price"],
        "winner_count": r["winner_count"],
        "purchase_end": r["purchase_end"],
        "reveal_end": r["reveal_end"],
        "claim_deadline": r["claim_deadline"],
        "unclaimed_mode": r["unclaimed_mode"],
        "status": r["status"],
        "buyers": sorted(r["buyers"]),
        "tickets": {addr: int(r["tickets"][addr]) for addr in sorted(r["buyers"])},
        "commitments": {addr: r["commitments"][addr] for addr in sorted(r["commitments"])},
        "operator": state["owner"],
        "operator_commitment": r["operator_commitment"],
        "operator_salt": r["operator_salt"],
        "revealed": {addr: r["revealed"][addr] for addr in sorted(r["revealed"])},
        "seed_block": r["seed_block"],
        "seed_block_hash": seed_block_hash,
        "seed_confirmations": SEED_CONFIRMATIONS,
        "seed": r["seed"],
        "winners": r["winners"],
        "winner_share": r["winner_share"],
        "claimed": r["claimed"],
        "algorithm": "sha256(commit-reveal salts + finalized block hash); weighted sampling without replacement",
    }
''',
    },
    {
        "name": "counter",
        "title": "计数器",
        "category": "基础",
        "description": "最简单的合约，演示状态持久化与事件。",
        "constructor": [],
        "functions": [
            {"name": "increment", "desc": "计数 +1", "params": []},
            {"name": "get", "desc": "查询当前计数", "params": []},
        ],
        "source": '''# 计数器模板
def init():
    state["count"] = 0
    emit("Created", by=msg.sender)

def increment():
    state["count"] = state.get("count", 0) + 1
    emit("Incremented", value=state["count"])

def get():
    return state.get("count", 0)
''',
    },
]


def get_templates():
    return TEMPLATES


def get_template(name):
    for t in TEMPLATES:
        if t["name"] == name:
            return t
    return None


def template_catalog():
    """Return templates without their source (for the list view)."""
    return [
        {
            "name": t["name"],
            "title": t["title"],
            "category": t["category"],
            "description": t["description"],
            "constructor": t["constructor"],
            "functions": t["functions"],
        }
        for t in TEMPLATES
    ]
