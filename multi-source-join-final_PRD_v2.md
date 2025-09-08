# 多源 Join + 去重 + 空值治理 + 时间/时区对齐 + 透视 PRD（最终版）

> 目标：在现有“拖拽式数据透视”工具基础上，新增**任意多源（Mongo/Excel/CSV）连接**、**字段筛选/重命名**、**源级去重（MD5 组合键）**、**空值治理**、**日期/时间键对齐（可选时区，默认 Asia/Shanghai）**、**缓存与性能护栏**，并与已有透视无缝衔接。

---

## 1. 背景与问题陈述

- 现状仅支持**单数据源**透视，无法跨表/跨源整合。
- 真实数据存在：**重复行**、**空值/占位值**、**时间格式/时区不一致**、**字段名冲突**、**文件大/行多**等问题，直接阻碍分析。
- 目标是先产出一个“**分析就绪宽表（AR Table）**”，再复用现有拖拽透视界面进行任意切片聚合。

---

## 2. 范围（In/Out of Scope）

**In Scope**
- 多源连接：Mongo 集合 ↔ 集合 / 集合 ↔ Excel / 集合 ↔ CSV / Excel ↔ Excel / Excel ↔ CSV / CSV ↔ CSV（最多 6 源/任务）。
- Join 类型：`INNER`、`LEFT`（默认）、`RIGHT`、`FULL OUTER`。
- 复合键与**时间键**（支持秒/毫秒时间戳、字符串时间、原生 date/datetime）。
- 源级**字段筛选/重命名**、**冲突消解**（自动前缀+手动别名）。
- 源级**去重（MD5 组合键）**：规范化→拼接→指纹→策略（保留/排序/聚合/报错）。
- **空值治理**：统一空值语义、Join 键空值策略、字段级填充与阈值预警。
- **时区与粒度对齐**：全局默认 `Asia/Shanghai`，支持源级/键级覆盖；粒度 `minute/hour/day/week/month`；可选窗口 Join。
- **性能与缓存**：Polars 引擎、分块/落地、Redis 缓存、资源与时限护栏。
- **交互**：数据源管理、连接向导、计划预览、质量报告、一键透视与 Preset 复用。

**Out of Scope（本期不做）**
- 其他数据库（MySQL/PG/BigQuery 等）接入。
- 自动“智能找键”（本期提供人工配置+质量报告提示）。
- 模型训练或高级异常检测。

---

## 3. 目标与成功标准（KPI）

- **功能性**：完成 6 源以内的 Join 配置→执行→产出 `resultId`→进入透视。
- **质量**：提供详尽的“连接质量报告”（重复/空值/时间解析/跨午夜/放大风险）。
- **性能**：3,000,000 行 / 文件 ≤ 4GB 的任务在默认 15 分钟内可完成（在合理硬件下）。
- **稳定性**：IO/网络异常自动重试，不致崩溃；“警告继续”为默认策略。
- **易用性**：保存/复用 Preset，二次运行命中 Redis 缓存可秒开。

---

## 4. 关键需求细化

### 4.1 连接方式与逻辑

- **键来源**：用户在向导中指定匹配字段（支持复合键），可跨源字段名映射；支持声明时间键 `kind=time`。
- **Join 类型**：`INNER`/`LEFT`（默认）/`RIGHT`/`FULL OUTER`。
- **字段冲突**：
  - 自动**源前缀**（如 `orders_`、`ads_`）+ `snake_case` 物理名；
  - UI 可手动重命名“显示名”；
  - 维护 `{display_name ↔ physical_name}` 映射，透视/导出可选其一。

### 4.2 时间/时区对齐（默认中国时区）

- **输入**：字符串（含 `YYYY-MM-DD HH:MM:SS.mmm`）、时间戳（秒/毫秒自动识别或指定）、原生 date/datetime。
- **时区**：三层覆盖——全局（默认 `Asia/Shanghai`）→ 源级 → 键级。
- **流程**：解析 → 按 `source_tz` 解释 → 转 `target_tz`（默认 `Asia/Shanghai`）→ 粒度对齐（默认 `truncate('day')`）→（可选）窗口匹配。
- **失败策略**：`on_parse_fail=as_null`，解析成功率 < 90% 触发**警告**。
- **窗口 Join**（可选，默认为关）：如 `±1h`，注意可能多对多，报告预警。

### 4.3 源级去重（MD5 组合键）

- **规范化**：`trim/collapse_spaces/upper/lower/replace/regex/to_int/to_float/to_date/epoch_ms/epoch_s`，空白→NULL，可选 `<NULL>` 占位。
- **指纹**：用不可见分隔符 `\u001F` 拼接规范化值，`md5`（可选 `sha1/sha256`）生成 `dedup_key`；报告碰撞率。
- **策略**：默认 `keep_last` by `update_ts desc`；可选 `keep_first/order_by/aggregate/error`。
- **报告**：输入/输出行数、去重率、重复组统计与样本。

### 4.4 空值治理

- **统一空值**：`""`、空格、`NBSP`、`"N/A"`、`"—"`、`"NULL"` → NULL（可配置列表）。
- **Join 键策略**（默认 `skip_if_null`）：`skip_if_null | use_placeholder | outer_keep_unmatched`。
- **字段级填充**：`fill_constant / fill_stat(mean|median|mode) / fill_from_other([col1,col2,...]) / drop_if_all_null([...])`。
- **阈值预警**：列级 NULL% 超阈（如 5%/10%）→ **警告继续**（默认），可改为 fail。
- **报告**：列级 NULL%，填充条数、未填充高风险列、未匹配 NULL 键行数。

### 4.5 性能与限制（最优默认）

| 项目 | 默认/上限 |
|---|---|
| 单文件大小 | ≤ **4 GB**（Excel/CSV） |
| 单结果集行数 | ≤ **3,000,000** |
| 同时数据源 | ≤ **6** |
| 单任务超时 | 默认 **15 分钟**（上限 60 分钟，后台任务） |
| 内存护栏 | 容器内存的 **60%** 且硬上限 **8 GB** |
| 分块大小 | `chunkSize = 200,000` 行 |
| 并发/队列 | 每用户并发 ≤ 2，队列 ≤ 5 |
| 缓存 | **Redis** 内存缓存，TTL=72h |

**实现取舍（后端）**
- 引擎：**Polars** + PyArrow/Arrow2。
- Mongo：尽量 `$project/$addFields/$dateTrunc` 下推；仅取所需列与时间规范化。
- 文件：CSV 走 `polars.read_csv`（低内存/忽略错误），Excel 通过 `xlsx2csv` 流式转 CSV 再读。
- Join 管线：驱动表在前（去重/裁剪/规范化），其余表按键建哈希索引分块匹配；大结果落地 Parquet 分片继续流水。

**实现取舍（前端）**
- 技术栈升级：**React + TypeScript**；JS 性能不足的地方用 TS + 虚拟滚动 + Worker 仅做微型预览；所有重计算后端化。
- 实时日志：SSE（Server-Sent Events）显示长任务进度与质量指标。

### 4.6 AR Table（分析就绪宽表）

- **结构**：连接后的宽表作为“虚拟表 `resultId`”，给透视 UI 使用。
- **命名**：物理列统一 `snake_case` + 源前缀；同名加序号后缀；显示名保留原文（中/多语言）。
- **类型**：统一到 `int64/float64/bool/utf8/date/datetime[tz]`；货币列配 `currency_code`。
- **时间列**：至少提供 `date_key`（按目标时区对齐到“天”）；如需小时/分钟分析，保留 `datetime_aligned`。
- **存储**：小结果留内存；大结果落地 Parquet（含字典/索引元数据）；Redis 缓存保存小结果或清单（manifest）。

---

## 5. 交互与用户流程

1) **数据源面板**
   - Mongo：选 `db/collection`，可设 `filter/project` 采样。
   - Excel/CSV：上传（分块）、显示 `fileId`，Excel 选 sheet/header 行；CSV 选分隔符/编码（自动探测可覆盖）。
   - 预览：前 N 行 + 随机 N 行；类型推断提示。

2) **连接向导**
   - 选择多源（≤6）→ 配置复合键与时间键 → 勾选字段/重命名/前缀 → 设置去重策略 → 查看计划摘要（估算行数/风险）→ 执行。

3) **质量报告**
   - 去重、空值、时间解析/时区对齐、跨午夜影响、重复键与笛卡尔风险、内存与耗时、是否命中缓存。

4) **一键透视 / 导出**
   - `resultId` 直接打开透视；导出 CSV/Parquet；保存 Preset（版本化/共享）。

---

## 6. API 与配置模型（草案）

### 6.1 上传与注册
- `POST /api/dataset/upload`：上传 Excel/CSV（分块），返回 `{fileId, sheets?, inferred_schema}`。
- `POST /api/dataset/register`：注册 Mongo 集合或上传文件的“逻辑表”。

### 6.2 预览与执行
- `POST /api/join/preview`：输入 Preset，返回计划摘要（字段/键/估算行数/预警）。
- `POST /api/join/execute`：执行 Join，返回 `{resultId, report, fields}`。
- `GET /api/join/result/:resultId`：分页/采样获取结果（供透视/预览）。

### 6.3 Preset（示例，精简）
```json
{
  "time_defaults": { "timezone": "Asia/Shanghai" },
  "limits": {
    "maxRows": 3000000,
    "maxFileSizeBytes": 4294967296,
    "maxSources": 6,
    "chunkSize": 200000,
    "timeoutSec": 900,
    "memoryGuardRatio": 0.6,
    "hardMemCapGB": 8
  },
  "cache": { "engine": "redis", "ttlHours": 72 },

  "datasets": {
    "orders": { "type":"mongo_collection","mongo":{"db":"biz","collection":"orders"},
      "time_rules": { "order_ts": {
        "parse":{"kind":"auto","epoch_unit":"ms","formats":["%Y-%m-%d %H:%M:%S%.3f","%Y-%m-%d %H:%M:%S"]},
        "source_tz":"Asia/Shanghai","target_tz":"Asia/Shanghai",
        "align":{"method":"truncate","unit":"day"},"on_parse_fail":"as_null"
      }}
    },
    "ads_csv": { "type":"csv_file","fileId":"f_ads","csv":{"delimiter":",","encoding":"utf-8","header_row":1},
      "time_rules": { "date": {
        "parse":{"kind":"string","formats":["%Y-%m-%d","%Y/%m/%d","%d.%m.%Y"]},
        "source_tz":"UTC","target_tz":"Asia/Shanghai",
        "align":{"method":"truncate","unit":"day"}
      }}
    },
    "cost_xlsx": { "type":"excel_sheet","fileId":"f_cost","sheet":"成本","header_row":1 }
  },

  "dedup": {
    "orders": { "keys":["sku","date_key","cluster"],"norm":["trim","upper","to_date"],
      "hash_algo":"md5","null_in_key":"skip",
      "on_conflict":{"strategy":"order_by","order":[{"field":"update_ts","dir":"desc"}]} },
    "ads_csv": { "keys":["sku","date"],"norm":["trim","to_date"],"hash_algo":"md5","null_in_key":"skip",
      "on_conflict":{"strategy":"keep_last","order":[{"field":"ingest_ts","dir":"desc"}]} },
    "cost_xlsx": { "keys":["商品编码"],"norm":["trim"],"hash_algo":"md5","null_in_key":"placeholder" }
  },

  "joins": [
    { "left":"orders","right":"ads_csv","type":"left",
      "keys":[
        { "leftKey":"order_ts","rightKey":"date","kind":"time",
          "time":{"left":{"use":"dataset_rule"},"right":{"use":"dataset_rule"}}},
        { "leftKey":"sku","rightKey":"sku" }
      ]},
    { "left":"orders","right":"cost_xlsx","type":"left",
      "keys":[ { "leftKey":"sku","rightKey":"商品编码","kind":"string","string":{"norm":["trim","upper"]} } ]}
  ],

  "select": {
    "orders":["date_key","sku","price","quantity","cluster"],
    "ads_csv":["mb_spent","op_spent","impressions","clicks"],
    "cost_xlsx":["商品编码","最新成本(руб)"]
  },

  "rename": { "最新成本(руб)":"cost_latest_rub","mb_spent":"mb_money_spent","op_spent":"op_money_spent" },
  "conflictPrefix": { "orders":"o_","ads_csv":"a_","cost_xlsx":"c_" },

  "nulls": {
    "treat_as_null":["",""," ","N/A","—","NULL"],
    "join_key_policy":"skip_if_null",
    "fills":{
      "cost_latest_rub":{"type":"fill_from_other","sources":["p_cost","a_cost","default:0"]},
      "price":{"type":"fill_stat","stat":"median"},
      "cluster":{"type":"fill_constant","value":"UNKNOWN"}
    },
    "thresholds":{"warn_if_null_pct_over":{"cost_latest_rub":0.05,"price":0.02}},
    "drop_rules":[{"if_all_null":["impressions","clicks","mb_money_spent","op_money_spent"]}]
  }
}
```

---

## 7. 质量报告（输出要求）

- **总体**：输入/输出行数、处理耗时、内存峰值、是否命中缓存。
- **去重**：源级输入/输出行、去重率、重复组统计、TopN 样本、hash 碰撞率。
- **时间**：解析成功率、使用格式分布、`source_tz→target_tz` 分布、`cross_midnight_shift`。
- **Join**：未匹配行数（含 NULL 键原因）、多对多/笛卡尔风险、样本。
- **空值**：列级 NULL%，填充条数、未填充高风险列。
- **导出**：报告 JSON 可下载；在 UI 中以“指标卡 + 表格 + 样本”展示。

---

## 8. 错误处理与恢复（默认：**警告继续**）

- **警告**（不中断）：时间解析失败率超阈、列 NULL% 超阈、重复键/放大风险、编码自动探测回退、窗口可能多对多。
- **失败**（中断）：内存/超时硬护栏、文件不可读（损坏/权限/编码无法解析且未覆盖）、非法时区/格式配置错误（`E_TZ_INVALID/E_FORMAT`）。
- **恢复**：Mongo 使用可恢复游标+指数退避（最多 3 次）；文件流式解析失败时截取样本行写入报告并建议参数覆盖。

---

## 9. 安全与权限

- 上传文件进行**扩展名/MIME/体积**校验；可选病毒扫描。
- 字段白名单；表达式/正则转义；服务端参数校验。
- 结果集与 Preset 绑定到工作区/用户权限模型；Redis Key 带租户前缀。

---

## 10. 非功能性与性能策略

- **后端**：Polars 懒执行 + 谓词下推；必要时落地 Parquet 分片（带字典/分区），按需再读。
- **内存控制**：分块流水；`rechunk` 合理使用；Guard 60% 或 8GB 硬上限。
- **缓存**：Redis 保存小结果或 manifest（大结果清单）；LRU+TTL=72h；Preset/源指纹变更立刻失效。
- **前端**：TS + 虚拟滚动；大结果分页/采样预览；SSE 实时日志；Worker 仅做轻量任务。

---

## 11. UAT 验收用例

1. **三源连接（集合↔CSV↔Excel）**：`orders(order_ts, sku)` ↔ `ads_csv(date, sku)` ↔ `cost_xlsx(商品编码)`；时间按 `Asia/Shanghai` 对齐到“天”，输出行 ≥ `orders`；质量报告各项完整。
2. **去重与冲突**：`orders` 以 `(sku,date_key,cluster)` 去重，策略 `keep_last by update_ts desc`，去重率与手工核对一致。
3. **空值策略**：`join_key_policy=skip_if_null` 时，NULL 键行不参与 Join；切为 `outer_keep_unmatched` 时，未匹配行保留并标记。
4. **文件大/多行**：CSV 2GB / 300 万行 + 集合 100 万行，分块 + 落地 Parquet，15 分钟内完成（参考环境），内存峰值受控。
5. **编码/格式混用**：CSV 存在 `utf-8` 与 `gbk` 混杂；通过手动指定编码覆盖后通过；报告保留失败样本。
6. **缓存命中**：相同 Preset 与源指纹命中 Redis，直接返回已存在 `resultId`，秒开透视。
7. **窗口 Join（±1h）**：小时级差异触发窗口匹配，报告多对多预警与建议（增加复合键/缩小窗口）。

---

## 12. 里程碑与交付

- **M1（后端）**：Polars 管线（去重/时间对齐/Join/落地/Redis 缓存）+ API（上传/预览/执行/结果）+ 质量报告（JSON）。
- **M2（前端）**：TS 化 + 数据源面板 + 连接向导 + 报告可视化 + SSE 日志 + 一键透视。
- **M3（优化）**：缓存/TTL 管理、Preset 版本与共享、导出增强、更多可观测性指标。

---

## 13. 迁移与实现提示（pandas → polars）

- **CSV**：`pl.read_csv(..., low_memory=True, ignore_errors=True, infer_schema_length=2000)`
- **Excel**：`xlsx2csv` → stdout → `pl.read_csv(p.stdout, ...)`
- **时间解析与时区**：`strptime` → `.dt.replace_time_zone(source_tz).dt.convert_time_zone(target_tz).dt.truncate('1d')`
- **MD5 组合键**：规范化后 `concat_str` + 自定义 `map_elements(md5)`；`unique(subset=key, keep='first')`
- **Join**：`df_left.join(df_right, on=[...], how='left')`；大表需分块+索引思想（按键分桶）

---

## 14. 最终选项（可配置但默认生效）

> 下列为第 14 节“待确认/可配置项”的**最优方案定稿**，已作为系统默认；仍支持租户级/任务级覆盖。

### 14.1 Excel 解析方式
- **选择**：允许在后端安装 `xlsx2csv`，走**流式 CSV 转换 → Polars 读取**（最低内存、最高稳定性）。  
- **文件类型策略**：  
  - `.xlsx/.xlsm`：优先 `xlsx2csv`（流式）；  
  - `.xls`（97-2003）：优先 `libreoffice --headless` 转 CSV；不可用时提示改为本地转存后再上传；  
  - 任何 Excel 工具不可用时：**fallback 到“先转 Parquet 再读”**（arrow/pyxlsb 可选）。  
- **失败处理**：解析异常保留样本行；给出“指定 sheet / header_row / encoding”的修复建议；**警告继续**。

### 14.2 资源配额与自适应
- **选择**：采用**环境感知 + 安全默认 + 自适应调优**的组合策略。  
- **默认护栏**（可通过环境变量覆盖）：  
  - 内存护栏：`MEM_GUARD_RATIO=0.60`；硬上限 `HARD_MEM_CAP_GB=8`  
  - 超时：`TIMEOUT_SEC=900`（15 分钟）；后台任务上限 60 分钟  
  - 并发/队列：`MAX_CONCURRENCY=2`、`QUEUE_DEPTH=5`  
  - 分块：`CHUNK_SIZE=200000`（行）  
- **自适应规则**：按数据规模自动调参（仍不突破护栏）  
  - `rows > 2,000,000` → `chunk_size = 300k` 且启用落地 Parquet 分片  
  - `rows > 1,000,000` → `chunk_size = 200k`（默认）  
  - `file > 2GB` → 强制流式解析 + 类型推断窗口缩小（如 `infer_schema_length=1000`）  
- **覆盖方式**：支持租户级/任务级 JSON 覆盖与环境变量（两者取更严）。

### 14.3 质量报告阈值与告警级别（保持“警告继续”）
- **时间解析成功率**：  
  - `≥98%`：✅ 正常  
  - `90%–98%`：⚠️ **警告**（提示完善 `formats/epoch_unit/source_tz`）  
  - `<90%`：🚩 **高优先级警告**（建议改规则或先修数）  
- **列空值占比（列级 NULL%）**：  
  - `≥0% & <5%`：✅ 正常  
  - `5%–10%`：⚠️ 警告（建议 `fill_*` 或回填）  
  - `>10%`：🚩 高优先级警告（默认不停，但在报告首页红牌提示）  
- **Join 未匹配率（相对驱动表）**：  
  - `≤3%`：✅ 正常  
  - `3%–10%`：⚠️ 警告（检查键规范化/时区/粒度/窗口）  
  - `>10%`：🚩 高优先级警告（建议切 `outer_keep_unmatched` 或调键）  
- **重复键/去重影响**（驱动表组合键）：  
  - 重复组比例 `>2%` 或最大重复组大小 `>10`：⚠️ 警告（建议先去重/聚合）  
- **笛卡尔放大风险**：检测到多对多匹配时一律 🚩 高优先级警告，并给出“增加复合键/先聚合/窗口缩小”的处方。  
- **注**：以上全部为**不中断**策略；仅资源越界/文件不可读/非法配置触发“失败中断”。
