# Paper → Markdown

使用 `paper-report` skill，由助理直接閱讀 PDF，產出繁體中文報告。

## 使用方式

1. 把 PDF 放進 `inbox/`。
2. 在本專案對話輸入：`$paper-report 處理 inbox 裡的 paper`。
3. 報告會保留在 `reports/`，並在完成後同步到 HackMD。

也可以直接從網路開始：

- `$paper-report 下載並分析 arXiv:2608.06791v1`
- `$paper-report 下載並分析 https://arxiv.org/abs/2608.06791`
- `$paper-report 找到並分析完整論文標題`
- `$paper-report 搜尋 LLM high-level synthesis 相關論文並分析前 5 篇`

skill 會把公開 PDF 下載到 `inbox/`，再接續改名、分析及 HackMD 同步。主題搜尋會優先使用可用的學術搜尋工具，預設依相關性取前 5 篇，可指定 1–10 篇；arXiv API 是備援。付費牆或需要登入的 PDF 不會繞過權限下載。

開始分析時，skill 會先讀取論文首頁，把 PDF 改成 `<論文主題>_vN.pdf`；例如 `2608.06791v1.pdf` 可改為 `HLSmith_v1.pdf`。報告使用相同檔名：`HLSmith_v1.md`。

## HackMD 一次性設定

1. 在 HackMD 建立 personal API token。
2. 複製 `.hackmd.env.example` 為 `.hackmd.env`。
3. 把 token 填入 `HACKMD_API_TOKEN=` 後方。不要把 token 貼到對話中或提交版本控制。

預設建立只有你能讀寫、關閉評論的私人 note。同一份報告更新時會更新原 note，不會重複建立。

如果當前對話沒有列出新 skill，可說：「讀取 skills/paper-report/SKILL.md，處理 inbox 裡的 paper」。不需要 OpenAI API key 或常駐程式，每次由對話發起處理。

## 規則位置

- `skills/paper-report/SKILL.md`：操作流程。
- `skills/paper-report/references/report-format.md`：完整問題、格式與證據要求。
- `AGENTS.md`：專案入口，指向上述 skill。
- `自動化paper流程.md`：原始需求。

報告包含背景動機、方法、實驗結果、結論、七項討論子題（含十項缺點與十項優化方向）及閱讀限制。

專案內的 skill 是原始版本；安裝至個人 skills 目錄後，修改時需同步副本。
