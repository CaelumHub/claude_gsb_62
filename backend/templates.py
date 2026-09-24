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
    {
        "name": "lottery",
        "title": "公平抽奖（多名额 · 可复算 · 领奖期限）",
        "category": "应用",
        "description": (
            "多轮公平抽奖：统一票价、一个地址可买多张（买得多概率大）、每轮可产生多个中奖名额。"
            "平台方开轮时提交 sha256(秘密值) 承诺，售票截止后揭示秘密值开奖，"
            "结果由公开规则唯一确定，任何人可用 verify() 复算验证；"
            "中奖者须在领奖期限内领奖，逾期奖金按部署参数滚入下一轮或退回平台方；"
            "平台方逾期未揭示则本轮取消，购票者全额退票。"
        ),
        "constructor": [
            {"name": "ticket_price", "type": "int", "desc": "每张奖券价格（统一票价）"},
            {"name": "num_winners", "type": "int", "desc": "每轮中奖名额数"},
            {"name": "sale_blocks", "type": "int", "desc": "售票时长（区块数）"},
            {"name": "reveal_blocks", "type": "int", "desc": "售票截止后平台方揭示秘密值的期限（区块数）"},
            {"name": "claim_blocks", "type": "int", "desc": "开奖后领奖期限（区块数）"},
            {"name": "rollover", "type": "int", "desc": "逾期未领奖金处理：1=滚入下一轮奖池，0=退回平台方"},
        ],
        "functions": [
            {"name": "start_round", "desc": "平台方开启新一轮（提交开奖承诺）", "params": ["commit_hash"]},
            {"name": "buy", "desc": "购票（附带 value = 票价×张数）", "params": ["count"]},
            {"name": "draw", "desc": "售票截止后揭示秘密值开奖", "params": ["secret"]},
            {"name": "claim", "desc": "中奖者在领奖期限内领奖", "params": []},
            {"name": "settle", "desc": "领奖期结束后结算未领奖金", "params": []},
            {"name": "cancel_round", "desc": "平台方逾期未揭示时取消本轮", "params": []},
            {"name": "refund", "desc": "本轮取消后购票者退票退款", "params": ["rnd"]},
            {"name": "verify", "desc": "用公开规则复算中奖名单并与链上结果比对", "params": ["rnd"]},
            {"name": "round_info", "desc": "查询某轮全部公开数据", "params": ["rnd"]},
            {"name": "current_round", "desc": "查询当前轮次与阶段", "params": []},
        ],
        "source": '''# 公平抽奖合约（多名额 · 多张购票 · 可复算验证 · 领奖期限 · 多轮）
#
# 公平性设计（承诺-揭示 commit-reveal）：
#   1. 平台方开轮时只提交 commit = sha256(secret)，秘密值 secret 在开奖前不公开，
#      因此购票者无法预测中奖结果（任何人无法定向购票）。
#   2. 承诺上链后平台方无法更换种子：开奖时揭示的 secret 必须满足
#      sha256(secret) == commit，否则开奖交易直接失败。
#   3. 开奖种子同时绑定轮次号与截止时的完整票本哈希：
#          seed = 轮次 | secret | sha256(票本)
#      中奖下标由 seed 经 sha256 逐个导出（碰撞时递增 attempt 重取，
#      保证名额落在不同奖券上）。全部输入都是链上公开数据，
#      任何人可用 verify() 或离线复算，结果唯一、不可抵赖。
#   4. 平台方若在揭示期内拒不揭示，任何人可取消本轮，购票者全额退票——
#      平台方无法通过"不开奖"侵吞票款。
#
# 轮次状态机：open(售票) → drawn(已开奖，领奖中) → settled(已结算)
#                    open → cancelled(逾期未揭示，可退票)
# 上一轮 settled / cancelled 后才能开启下一轮。

def init(ticket_price, num_winners, sale_blocks, reveal_blocks, claim_blocks, rollover):
    require(state.get("owner") is None, "已初始化")
    ticket_price = float(ticket_price)
    num_winners = int(num_winners)
    sale_blocks = int(sale_blocks)
    reveal_blocks = int(reveal_blocks)
    claim_blocks = int(claim_blocks)
    require(ticket_price > 0, "票价必须为正")
    require(num_winners >= 1, "中奖名额至少为 1")
    require(sale_blocks >= 1, "售票期至少 1 个区块")
    require(reveal_blocks >= 1, "揭示期至少 1 个区块")
    require(claim_blocks >= 1, "领奖期至少 1 个区块")
    state["owner"] = msg.sender
    state["ticket_price"] = ticket_price
    state["num_winners"] = num_winners
    state["sale_blocks"] = sale_blocks
    state["reveal_blocks"] = reveal_blocks
    state["claim_blocks"] = claim_blocks
    state["rollover"] = 1 if int(rollover) != 0 else 0
    state["round"] = 0          # 当前轮次号，0 表示尚未开轮
    state["carry"] = 0          # 滚存：上一轮未领、进入下一轮奖池的奖金
    emit("Created", owner=msg.sender, ticket_price=ticket_price,
         num_winners=num_winners, rollover=state["rollover"])

# ------------------------------------------------------------------ #
# 内部工具
# ------------------------------------------------------------------ #
def _rkey(rnd):
    return "r" + str(rnd)

def _round(rnd):
    return state.get(_rkey(rnd))

def _save(rnd, r):
    state[_rkey(rnd)] = r

def _draw_indices(seed, n, k):
    """由种子确定性地导出 k 个互不相同的奖券下标（任何人可复算）。"""
    idxs = []
    i = 0
    while len(idxs) < k:
        attempt = 0
        while True:
            h = sha256(seed + "|" + str(i) + "|" + str(attempt))
            idx = int(h, 16) % n
            if idx not in idxs:
                idxs.append(idx)
                break
            attempt = attempt + 1
        i = i + 1
    return idxs

# ------------------------------------------------------------------ #
# 轮次管理
# ------------------------------------------------------------------ #
def start_round(commit_hash):
    """平台方开启新一轮；commit_hash = sha256(秘密值) 的十六进制。"""
    require(msg.sender == state["owner"], "只有平台方能开新轮")
    rnd = state.get("round", 0)
    if rnd >= 1:
        prev = _round(rnd)
        require(prev["status"] in ("settled", "cancelled"),
                "上一轮尚未结束（请先开奖/结算或取消）")
    commit_hash = str(commit_hash)
    ok = len(commit_hash) == 64
    if ok:
        try:
            int(commit_hash, 16)
        except:
            ok = False
    require(ok, "承诺必须是 64 位十六进制的 sha256 哈希")
    new = rnd + 1
    pot = state.get("carry", 0)   # 上一轮的滚存进入本轮奖池
    state["carry"] = 0
    sale_end = block_height + state["sale_blocks"]
    state[_rkey(new)] = {
        "commit": commit_hash, "secret": None, "seed": None,
        "status": "open",
        "sale_end": sale_end,
        "reveal_end": sale_end + state["reveal_blocks"],
        "claim_end": None,
        "tickets": [], "buyers": {},
        "pot": pot, "revenue": 0,
        "winners": [], "winning_indices": [], "claimed": [],
        "prize": 0, "unclaimed": 0,
    }
    state["round"] = new
    emit("RoundStarted", round=new, commit=commit_hash,
         pot=pot, sale_end=sale_end)

def buy(count):
    """购买 count 张奖券；附带 value 必须恰好等于 票价×张数。"""
    count = int(count)
    require(count >= 1, "至少购买 1 张")
    rnd = state.get("round", 0)
    require(rnd >= 1, "当前没有开放中的轮次")
    r = _round(rnd)
    require(r["status"] == "open", "当前不在售票阶段")
    require(block_height < r["sale_end"], "售票已截止")
    price = state["ticket_price"]
    require(abs(msg.value - price * count) < 1e-9,
            "支付金额须恰好等于 票价×张数")
    tickets = r["tickets"]
    for _ in range(count):
        tickets.append(msg.sender)
    buyers = r["buyers"]
    buyers[msg.sender] = buyers.get(msg.sender, 0) + count
    r["tickets"] = tickets
    r["buyers"] = buyers
    r["revenue"] = r["revenue"] + msg.value
    _save(rnd, r)
    emit("TicketBought", round=rnd, buyer=msg.sender, count=count,
         total_tickets=len(tickets))

def draw(secret):
    """售票截止后揭示秘密值开奖。任何人拿到 secret 都可调用（便于公示）。"""
    rnd = state.get("round", 0)
    require(rnd >= 1, "尚未开始任何轮次")
    r = _round(rnd)
    require(r["status"] == "open", "本轮已开奖或已取消")
    require(block_height >= r["sale_end"], "售票尚未截止")
    require(block_height <= r["reveal_end"], "已超过揭示期限，应取消本轮并退票")
    secret = str(secret)
    require(sha256(secret) == r["commit"], "揭示值与开轮承诺不匹配")
    tickets = r["tickets"]
    n = len(tickets)
    if n == 0:
        # 无人购票：直接结算，滚存退回 carry 进入下一轮
        r["status"] = "settled"
        state["carry"] = state.get("carry", 0) + r["pot"]
        r["pot"] = 0
        _save(rnd, r)
        emit("Settled", round=rnd, note="无人购票，本轮流局")
        return
    k = state["num_winners"]
    if k > n:
        k = n
    seed = str(rnd) + "|" + secret + "|" + sha256(",".join(tickets))
    idxs = _draw_indices(seed, n, k)
    winners = [tickets[i] for i in idxs]
    pool = r["pot"] + r["revenue"]
    prize = pool / k
    r["secret"] = secret
    r["seed"] = seed
    r["winners"] = winners
    r["winning_indices"] = idxs
    r["claimed"] = [False] * k
    r["prize"] = prize
    r["claim_end"] = block_height + state["claim_blocks"]
    r["status"] = "drawn"
    _save(rnd, r)
    emit("Drawn", round=rnd, winners=winners, winning_indices=idxs,
         prize=prize, seed=seed)

def claim():
    """中奖者在领奖期限内领取自己全部未领名额的奖金。"""
    rnd = state.get("round", 0)
    require(rnd >= 1, "尚未开始任何轮次")
    r = _round(rnd)
    require(r["status"] == "drawn", "当前不在领奖阶段")
    require(block_height <= r["claim_end"], "领奖期限已过")
    winners = r["winners"]
    claimed = r["claimed"]
    slots = 0
    for i in range(len(winners)):
        if winners[i] == msg.sender and not claimed[i]:
            claimed[i] = True
            slots = slots + 1
    require(slots > 0, "您没有可领取的中奖名额")
    amount = r["prize"] * slots
    r["claimed"] = claimed
    _save(rnd, r)
    transfer(msg.sender, amount)
    emit("Claimed", round=rnd, winner=msg.sender, slots=slots, amount=amount)

def settle():
    """领奖期结束后结算：未领奖金按参数滚入下一轮或退回平台方。任何人可调用。"""
    rnd = state.get("round", 0)
    require(rnd >= 1, "尚未开始任何轮次")
    r = _round(rnd)
    require(r["status"] == "drawn", "本轮不在待结算状态")
    require(block_height > r["claim_end"], "领奖期尚未结束")
    unclaimed_slots = 0
    for c in r["claimed"]:
        if not c:
            unclaimed_slots = unclaimed_slots + 1
    unclaimed = r["prize"] * unclaimed_slots
    r["status"] = "settled"
    r["unclaimed"] = unclaimed
    _save(rnd, r)
    if unclaimed > 0:
        if state["rollover"] == 1:
            state["carry"] = state.get("carry", 0) + unclaimed
        else:
            transfer(state["owner"], unclaimed)
    emit("Settled", round=rnd, unclaimed=unclaimed,
         rollover=state["rollover"])

def cancel_round():
    """平台方超过揭示期限仍未揭示时，任何人可取消本轮（购票者可退票）。"""
    rnd = state.get("round", 0)
    require(rnd >= 1, "尚未开始任何轮次")
    r = _round(rnd)
    require(r["status"] == "open", "本轮不在售票/待揭示状态")
    require(block_height > r["reveal_end"], "仍在售票或揭示期内，不能取消")
    r["status"] = "cancelled"
    state["carry"] = state.get("carry", 0) + r["pot"]  # 滚存退回，进入下一轮
    r["pot"] = 0
    _save(rnd, r)
    emit("Cancelled", round=rnd)

def refund(rnd):
    """本轮取消后，购票者取回全部票款。"""
    rnd = int(rnd)
    r = _round(rnd)
    require(r is not None, "轮次不存在")
    require(r["status"] == "cancelled", "该轮未取消，不能退票")
    buyers = r["buyers"]
    count = buyers.get(msg.sender, 0)
    require(count > 0, "没有可退的奖券")
    buyers[msg.sender] = 0
    r["buyers"] = buyers
    _save(rnd, r)
    amount = state["ticket_price"] * count
    transfer(msg.sender, amount)
    emit("Refunded", round=rnd, buyer=msg.sender, tickets=count, amount=amount)

# ------------------------------------------------------------------ #
# 公开验证 / 查询（只读，任何人可复算）
# ------------------------------------------------------------------ #
def verify(rnd):
    """用公开规则复算第 rnd 轮中奖名单，并与链上保存的结果比对。"""
    rnd = int(rnd)
    r = _round(rnd)
    require(r is not None, "轮次不存在")
    require(r.get("secret") is not None, "该轮尚未揭示，暂无法复算")
    idxs = _draw_indices(r["seed"], len(r["tickets"]), len(r["winners"]))
    winners = [r["tickets"][i] for i in idxs]
    return {"round": rnd, "seed": r["seed"],
            "commit_ok": sha256(str(r["secret"])) == r["commit"],
            "recomputed_indices": idxs, "recomputed_winners": winners,
            "onchain_winners": r["winners"],
            "match": winners == r["winners"] and idxs == r["winning_indices"]}

def round_info(rnd):
    """返回某轮的全部公开数据（票本、承诺、种子、中奖名单等）。"""
    rnd = int(rnd)
    r = _round(rnd)
    require(r is not None, "轮次不存在")
    out = dict(r)
    out["round"] = rnd
    return out

def current_round():
    rnd = state.get("round", 0)
    if rnd == 0:
        return {"round": 0, "status": "idle", "carry": state.get("carry", 0)}
    r = _round(rnd)
    return {"round": rnd, "status": r["status"],
            "sale_end": r["sale_end"], "reveal_end": r["reveal_end"],
            "claim_end": r["claim_end"], "tickets": len(r["tickets"]),
            "pool": r["pot"] + r["revenue"],
            "carry": state.get("carry", 0), "height": block_height}
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
