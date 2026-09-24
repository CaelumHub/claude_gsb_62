# 多名额公平抽奖合约（fair_lottery）

内置模板 `fair_lottery`（模板库 → “多名额公平抽奖”）实现了一个**公开可验证、
任何人无法作弊**的多轮抽奖模块：

- **多名额**：每轮可配置 `winner_count` 个中奖名额，同一地址一轮最多中一个名额；
- **多张购票**：票价统一（`ticket_price`），一个地址可多次、多张购买，
  中奖概率与持票数量严格成正比（按票加权、无替换抽样）；
- **可复算验证**：开奖种子、全部 reveal 记录、区块哈希与抽样算法全部在链上公开，
  任何人可用 `verification_record()` 导出记录，并用 `replay_winners()` 或
  链下脚本重新算出完全相同的中奖名单；
- **领奖期限**：中奖者必须在 `claim_deadline` 前调用 `claim()` 领奖；
  逾期奖金按每轮配置处理——`rollover`（滚入下一轮奖池）或
  `refund`（按票数比例退还给本轮未中奖的购票者）；
- **多轮运行**：一轮结算（finalize）或取消（cancel）后可立即开启新一轮，
  滚存奖金自动注入下一轮奖池。

## 公平性设计（为什么无法作弊）

随机数种子由三类公开输入共同决定，任何单一角色都无法控制：

```
seed = SHA256( "fair-lottery-v1" ‖ 合约地址 ‖ 轮次
             ‖ "operator:" + 运营方盐值
             ‖ 每个购票者的 "地址:盐值"（按地址排序）
             ‖ "block:" + 揭示截止高度(reveal_end)的区块哈希 )
```

1. **运营方 commit–reveal**：创建轮次时必须提交
   `operator_commitment = SHA256("fair-lottery-v1-commit|轮次|运营方地址|盐值")`，
   售票结束后才能公开盐值。运营方无法在看到购票情况后更改盐值；
   若拒不 reveal，本轮自动取消并**全额退票**。
2. **购票者 commit–reveal**：购票时必须提交自己的承诺（同样格式），
   揭示期内公开盐值。至少一名购票者 reveal 才能开奖，否则取消并退票。
3. **未来区块哈希**：所有盐值必须在“种子区块”（`reveal_end` 高度）**之前**公开，
   随后才使用该区块哈希。矿工无法提前知道盐值组合，购票者也无法在看到
   区块哈希后选择性 reveal。开奖还要求种子区块再经过
   `SEED_CONFIRMATIONS = 2` 个确认，降低短重组影响。

抽样算法：**按票加权、地址不可重复的无替换抽样**（Fenwick 树 + SHA-256
拒绝采样，拒绝采样消除取模偏差）。算法完全确定：相同种子与票仓必然得到
相同名单，这正是“可复算”的基础。

## 一轮的生命周期

```
create_round ──► open(售票) ──► revealing(揭示) ──► drawn(已开奖) ──► finalized
                     │                                    │
                     └── 运营方未reveal/无人reveal/人数不足 ──► cancelled(全额退票)
```

| 阶段 | 触发条件 | 可调用函数 |
| --- | --- | --- |
| 售票 `open` | `block_height < purchase_end` | `buy_tickets(count, commitment)`（附票款） |
| 揭示 `revealing` | `purchase_end ≤ height < reveal_end` | `reveal(salt)`、`operator_reveal(salt)` |
| 开奖 | `height > reveal_end + 2` | `draw()`（任何人可触发） |
| 领奖 `drawn` | `height ≤ claim_deadline` | `claim()`（仅中奖者） |
| 结算 | `height > claim_deadline` | `finalize_round()`（任何人可触发） |

### `create_round` 参数

| 参数 | 含义 |
| --- | --- |
| `ticket_price` | 单张票价（正整数，全轮统一） |
| `winner_count` | 中奖名额数 |
| `purchase_end` | 售票截止区块高度（不含） |
| `reveal_end` | 揭示截止高度，同时是种子区块高度 |
| `claim_deadline` | 领奖截止高度 |
| `unclaimed_mode` | `"rollover"` 滚入下一轮 / `"refund"` 退还未中奖者 |
| `operator_commitment` | 运营方盐值承诺（64 位十六进制） |

要求 `当前高度 < purchase_end < reveal_end < claim_deadline`；
参与地址数少于名额数时本轮取消并全额退票。

## 链下准备：计算承诺

承诺公式（可用合约的只读函数 `commitment(round_id, participant, salt)`
在链上模拟计算，或自行计算）：

```python
import hashlib
def commitment(round_id, participant, salt):
    return hashlib.sha256(
        f"fair-lottery-v1-commit|{round_id}|{participant}|{salt}".encode()
    ).hexdigest()
```

盐值应使用足够随机且保密的字符串，reveal 之前不要泄露。

## 典型调用流程（REST API）

```bash
# 1. 部署（模板库一键部署，或）
POST /api/contract/deploy  {"sender": OWNER, "code": <模板源码>, "constructor": []}

# 2. 运营方创建轮次（先链下算好 operator_commitment）
POST /api/contract/<addr>/invoke
     {"sender": OWNER, "function": "create_round",
      "args": [10, 2, 200, 250, 400, "rollover", "<commitment>"]}

# 3. 购票者购票（value = 票数 × 票价）
POST /api/contract/<addr>/invoke
     {"sender": BUYER, "function": "buy_tickets",
      "args": [3, "<buyer_commitment>"], "value": 30}

# 4. 揭示期内公开盐值
... {"function": "reveal", "args": ["<buyer_salt>"]}
... {"function": "operator_reveal", "args": ["<operator_salt>"]}

# 5. 种子区块确认后任何人触发开奖
... {"function": "draw", "args": []}

# 6. 中奖者领奖 / 逾期后结算
... {"function": "claim", "args": []}
... {"function": "finalize_round", "args": []}
```

## 事后验证（任何人都可以）

```bash
# 只读调用，返回复算所需的全部公开记录
POST /api/contract/<addr>/call
     {"function": "verification_record", "args": [1]}

# 用链上记录重算中奖名单（应与 record.winners 完全一致）
POST /api/contract/<addr>/call
     {"function": "replay_winners", "args": [1]}
```

链下复算步骤：

1. 校验每个 `commitments[addr] == commitment(round_id, addr, revealed[addr])`
   以及运营方承诺；
2. 按上文公式从 reveal 记录与 `seed_block_hash` 重建 `seed`，
   断言等于 `record.seed`；
3. 对票仓（`tickets`）执行“Fenwick 加权无替换抽样”：
   第 `slot` 个名额取 `u = SHA256(seed|u|slot|guard)`（拒绝采样至
   `u < 2^256 - (2^256 mod 总票数)`），`rank = u mod 剩余票数 + 1`，
   在按地址排序的累计票权数组中找到 `rank` 所在地址，中奖后将其票权移除；
4. 得到的名单应与链上 `winners` 完全一致。

## 资金规则

- 票款全部进入本轮奖池，合约没有任何“ owner 提现”函数；
- 每名额奖金 = 奖池 ÷ 实际中奖人数（整除），除不尽的余数滚存；
- 逾期未领：`rollover` 滚入下一轮奖池；`refund` 按票数比例退给未中奖者
  （整除余数作为滚存保留）；
- 轮次取消（运营方未 reveal / 无购票者 reveal / 人数不足）：
  票款全额退回，原有滚存保留到下一轮。

## 规模与限制

- 购票、领奖、reveal 均为 O(1)；开奖为 O(名额 × log 购票人数)，
  结算退款为 O(购票人数)，均受沙箱指令预算保护；
- 状态键上限 `CONTRACT_MAX_STATE_KEYS`（默认 2000），每轮仅占一个键，
  购票人数受单轮状态值大小与指令预算限制，实际可支持数百至数千参与者；
- 事件日志（`RoundCreated` / `TicketsPurchased` / `SaltRevealed` /
  `DrawCompleted` / `PrizeClaimed` / `RoundFinalized` / `RoundCancelled`）
  可通过 `/api/contract/<addr>/events` 查询，用于审计与前端展示。
