# 每日 arXiv 工业推荐系统论文筛选

每天自动抓 arXiv 的 cs.IR / cs.LG 新论文，按「工业界 + 线上验证 + 序列建模/排序」的规则打分，
筛出几篇值得读的，渲染成网页和 RSS，托管在 GitHub Pages 上，手机随时打开。

全程免费，不需要服务器，你的电脑关机也照跑。

---

## 一次性配置（大约十分钟）

### 1. 建仓库

在 GitHub 右上角点 `+` → `New repository`。

- 仓库名：`arxiv-recsys-daily`（随便取，但后面的网址会用到它）
- 选 **Public**。选 Private 的话 GitHub Pages 需要付费套餐，先用 Public 跑通再说，
  想改成私有看本文最后一节。
- 不要勾选 "Add a README file"，因为我们马上要上传自己的。
- 点 `Create repository`。

### 2. 上传文件

在新建好的空仓库页面上，点 `uploading an existing file` 那个链接，
把这个压缩包解压后的**所有内容**拖进去（是里面的文件，不是最外层那个文件夹）。

> **macOS 用户注意**：`.github` 这个文件夹以点开头，Finder 默认是隐藏的，
> 直接拖会漏掉它，漏掉之后定时任务不会跑。在 Finder 里按 `Command + Shift + .`
> 可以显示隐藏文件，确认 `.github` 出现之后再一起拖。

拖完之后页面下方点 `Commit changes`。

### 3. 打开 Pages

仓库页面顶部 `Settings` → 左侧边栏找到 `Pages`。

- `Source` 选 `Deploy from a branch`
- `Branch` 选 `main`，右边的文件夹选 **`/docs`**
- 点 `Save`

它会显示你的网址，形如 `https://<你的用户名>.github.io/arxiv-recsys-daily/`。
现在打开还是 404，因为还没生成内容。

### 4. 确认 Actions 有写权限

`Settings` → 左侧 `Actions` → `General` → 拉到最下面的 `Workflow permissions`。

选 **`Read and write permissions`**，点 `Save`。

这一步很容易漏。新仓库默认是只读的，漏了的话脚本能跑完但提交不上去，
日志里会看到 `403` 错误。

### 5. 配置 Claude API key（可选）

不配也能跑，只是少了中文摘要和 LLM 二次筛选，纯靠关键词规则。

`Settings` → `Secrets and variables` → `Actions` → `New repository secret`

- Name 填 `ANTHROPIC_API_KEY`
- Secret 填你的 key
- 点 `Add secret`

key 存在这里不会出现在日志或页面上。

### 6. 手动跑一次验证

仓库顶部 `Actions` 标签 → 左侧点 `每日论文筛选` → 右边 `Run workflow` 按钮 → 再点绿色的 `Run workflow`。

等一两分钟刷新，点进那次运行可以看日志。正常的话会看到类似：

```
arXiv 返回 187 篇
硬过滤：已见 0，修订版 41，分类不符 62，超出时间窗 3，保留 81
达到阈值 6 篇，其中必读 2 篇
已写入 docs/index.html
```

然后打开第 3 步给的网址，应该能看到今天的论文了。

### 7. 填上网址

打开仓库里的 `config.yaml`，点铅笔图标编辑，把 `site.base_url` 改成你的实际网址：

```yaml
site:
  base_url: "https://你的用户名.github.io/arxiv-recsys-daily"
```

提交。这一步只影响 RSS 里的链接，不填也不影响网页。

配置到此结束。之后每个工作日它会自己跑。

---

## 日常使用

- **网页**：直接打开那个网址。手机上可以用浏览器的「添加到主屏幕」，用起来跟 App 一样。
- **RSS**：订阅 `你的网址/feed.xml`，用手机上任何 RSS 阅读器。比记得去开网页靠谱得多。
- **历史**：页面底部有「历史」链接，按日期翻。

---

## 调权重

所有阈值和关键词都在 `config.yaml`，直接在 GitHub 网页上编辑提交就生效。

跑上一两周之后大概率要调。判断标准：

- **每天都是空的** → `thresholds.must_read` 和 `maybe` 调低，或者 `fetch.window_days` 调大。
- **上榜的一堆不想读的** → 阈值调高，或者给那些论文共有的特征加负向规则。
- **明显想读的被漏了** → 打开那篇的 arXiv 摘要，找几个规则没覆盖的词，加进 `scoring.topics`。

页面上每篇论文下面都列了它命中了哪些关键词，这就是给你调权重用的——
能一眼看出某篇是靠什么进来的。

调完之后不用等第二天，可以拿存档重跑验证：

```bash
python src/main.py --rescore 2026-09-11
```

这条不访问 arXiv，直接读 `data/archive/2026-09-11.json` 重新打分。

---

## 本地跑（可选）

```bash
pip install -r requirements.txt
python src/main.py --dry-run     # 抓取打分但不写文件
python tests/smoke_test.py       # 离线测试，不联网
```

---

## 常见问题

**Actions 日志里 403 / 推送失败**
第 4 步没做，去把 Workflow permissions 改成读写。

**网页一直 404**
Pages 第一次部署要等一两分钟。另外确认第 3 步的文件夹选的是 `/docs` 不是 `/(root)`。

**周末页面是空的**
正常。arXiv 周末不发新论文，周一的页面也常常很薄。

**定时没有准点跑**
GitHub 的 cron 不精确，高峰期延迟十几分钟很常见，偶尔会跳过。这是 GitHub 的已知行为，
不是配置问题。急着看就去 Actions 手动点一次。

**第一天上榜特别多**
因为 `seen.json` 是空的，三天窗口内的论文全是新的。第二天开始就正常了。

---

## 想让它私有

Public 仓库的 Pages 网页是公开的，任何人拿到网址都能看（包括你的关键词清单）。三个选择：

1. **仓库转 Private**：GitHub Pages 对 private 仓库需要付费套餐。
2. **Cloudflare Pages + Access**：仓库保持 private，用 Cloudflare 拉取构建产物并加一层登录，免费额度够用，但要多配一套东西。
3. **随机网址**：仓库 private，另外建一个 public 仓库专门放渲染产物，名字取成一串随机字符。
   不算严格的安全，但拦得住随手搜索。

日常自用的话，先 Public 跑通，觉得关键词清单敏感了再迁。
