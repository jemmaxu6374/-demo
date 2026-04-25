# Streamlit Cloud 部署操作手册

本文档说明如何把本项目从本地推到 **Streamlit Community Cloud**，拿到一个公网可访问的永久 URL。

---

## 一、前置检查

本仓库已为 Cloud 部署做好准备：

| 文件 | 作用 |
| --- | --- |
| `.streamlit/config.toml` | 主题色、隐藏水印、关闭遥测 |
| `requirements.txt` | **精简** 部署依赖（仅 7 个包，build <3 min） |
| `requirements-dev.txt` | 本地开发完整依赖（含 chromadb / sentence-transformers） |
| `packages.txt` | 系统级 apt 依赖占位（目前空） |
| `.python-version` | 锁定 Python 3.11 |
| `.gitignore` | 排除 `db/*.sqlite` / `data/vector_store/` / `.env` |
| `app/_bootstrap.py` | **关键**：冷启动自动生成数据（~45s） |

---

## 二、操作步骤

### Step 1：创建 GitHub 仓库

前提：已有 GitHub 账号。

```bash
# 在本地仓库根（employee-empowerment-demo/）
cd /Users/jemmaxu/WorkBuddy/20260423234207/employee-empowerment-demo

git init
git add .
git commit -m "feat: initial Streamlit Cloud deployable demo"

# 在 GitHub 网页新建一个仓库，假设叫 employee-empowerment-demo
# 然后回到本地：
git remote add origin https://github.com/<你的用户名>/employee-empowerment-demo.git
git branch -M main
git push -u origin main
```

**⚠️ 注意**：Streamlit Community Cloud 免费版要求仓库 **Public**。若内容敏感，使用 Pro 版或自建部署。

### Step 2：绑定 Streamlit Cloud

1. 访问 <https://share.streamlit.io>
2. 用 GitHub 账号登录（授权读取 public 仓库）
3. 点击 **"New app"**
4. 填表单：
   - **Repository**：`<你的用户名>/employee-empowerment-demo`
   - **Branch**：`main`
   - **Main file path**：`app/streamlit_app.py`
   - **App URL**（可选）：自定义子域名，如 `emp-empower-demo.streamlit.app`
5. 点击 **Advanced settings**：
   - **Python version**：`3.11`（匹配 `.python-version`）
   - **Secrets**（可选）：若要启用真 LLM，填
     ```toml
     LLM_PROVIDER = "openai"
     LLM_API_KEY = "sk-xxx"
     LLM_MODEL = "gpt-4o-mini"
     ```
     默认不填走 mock 模式，零成本。
6. 点击 **Deploy!**

### Step 3：等待构建

首次部署会经历三个阶段：

| 阶段 | 日志提示 | 时长 |
| --- | --- | --- |
| 1. clone repo | `Cloning repository...` | ~10s |
| 2. pip install | `Installing requirements...` | ~60-120s |
| 3. app 首次启动 + bootstrap | `🔧 首次启动需要准备数据...` | ~45-60s |

**总时长预估 3-5 分钟**。之后每次 push 会触发重新构建。

### Step 4：验证

构建完成后：

1. 访问分配的 URL（如 `https://emp-empower-demo.streamlit.app`）
2. 首次访问会卡在首页约 45 秒（bootstrap 正在建数据库），这是**正常的**
3. 之后切换侧边栏员工/JD → 访问 5 个页面应均无错误

**debug 模式**：在 URL 后加 `?debug=1` 可看到 bootstrap 状态条，便于排查。

---

## 三、常见问题

### Q1：build 超时（15 分钟）

**原因**：`requirements.txt` 装了 chromadb / sentence-transformers 等大包。

**方案**：确认提交的是精简版 `requirements.txt`（7 个包），不是 `requirements-dev.txt`。

### Q2：启动后首页一片空白 / 报 no such table

**原因**：bootstrap 没跑（可能 `app/__init__.py` 或 `scripts/__init__.py` 没提交）。

**方案**：确认以下文件已提交到仓库：
```
app/__init__.py
app/_bootstrap.py
scripts/__init__.py
```

### Q3：双视图页时间轴滑动卡顿

**原因**：Streamlit Cloud 免费版单 app 内存仅 1GB，每次 rerun 都重新查询 snapshot。

**方案**：接受现状（Demo 目的已达）或升级付费版。

### Q4：想接入真 LLM

在 Streamlit Cloud 的 app → Settings → **Secrets** 填：
```toml
LLM_PROVIDER = "openai"
LLM_API_KEY = "sk-xxx"
LLM_MODEL = "gpt-4o-mini"
```
保存后自动重启。`config.py` 会读取 Secrets。

### Q5：如何更新代码

```bash
git add <改动文件>
git commit -m "..."
git push
```
Streamlit Cloud 会自动检测 push 并重新部署（3-5 分钟）。

### Q6：如何删除 app

Streamlit Cloud Dashboard → app → Settings → Delete app。仓库不受影响。

---

## 四、部署后推荐做的事

1. **自定义域名**：在 Cloud 的 Advanced settings 里把子域名改成语义化，如 `empower-demo.streamlit.app`
2. **加访问日志**：Cloud 免费版已内置简单访问统计，Dashboard 可见
3. **加入 README 徽章**：给仓库加一个 "Open in Streamlit" 按钮
   ```markdown
   [![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://<你的子域名>.streamlit.app)
   ```
4. **分享给同事**：直接把公网 URL 贴到企业微信/邮件即可访问，无需登录

---

## 五、成本

- **Streamlit Community Cloud 免费版**：
  - 每个 GitHub 账号最多 **3** 个 public app
  - 单 app 内存 1 GB、存储 1 GB
  - 休眠策略：7 天无访问自动休眠（下次访问重新唤醒，约 10 秒）
  - **完全免费**
- **Streamlit Cloud 付费版**：无休眠 + 私有仓库支持，按月订阅

对本 Demo 完全够用。

---

## 六、仓库里的其他可选入口

如果未来想迁移到别的托管（如 Hugging Face Spaces / 腾讯云 Lighthouse / 自建 k8s）：

- `requirements.txt` 精简版对所有平台都友好
- `app/_bootstrap.py` 的逻辑是平台无关的
- `.streamlit/config.toml` 在所有 Streamlit 宿主上通用
- 只需把启动命令设为 `streamlit run app/streamlit_app.py` 即可
