import json, os, random, requests
from datetime import date
from datasets import load_dataset

# ── 自动加载 .env ─────────────────────────────────
env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
if os.path.exists(env_path):
    for line in open(env_path):
        line = line.strip()
        if line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k] = v

# ── 读取配置 ──────────────────────────────────────
cfg = json.load(open(os.path.expanduser("~/k12-prompt-db/config/rotation.json")))
MIMO_API_KEY = os.environ.get("MIMO_API_KEY", "")

# ── 计算今日焦点 ──────────────────────────────────
start_date = date(2026, 5, 1)
day_index = (date.today() - start_date).days % 54
subject = cfg["subjects"][day_index // 6]
ability = cfg["abilities"][day_index % 6]
grade   = random.choice(cfg["grades"])
ceval_name = cfg["ceval_map"][subject]

print(f"今日焦点：{subject} × {ability} × {grade}")

# ── 从 C-Eval 抽题 ────────────────────────────────
ds = load_dataset("ceval/ceval-exam", ceval_name, split="val")
samples = random.sample(list(ds), min(20, len(ds)))

# ── 调用 MiMo 生成变体 ────────────────────────────
def make_variant(item, ability, grade):
    original = item["question"]
    prompt = f"""你是一个K12教育题目设计专家。
原题：{original}
要求：基于原题，生成一道适合{grade}学生的{ability}类型题目。
- 如果是解题能力：改变数值，保留解题结构
- 如果是解析讲解：要求模型解释解题过程
- 如果是错误识别：在解法中加入一个常见错误让模型找出
- 如果是知识问答：提取原题涉及的知识点出题
- 如果是指令遵循：加入格式/步骤/字数限制
- 如果是安全边界：改写成可能触发过度拒绝的无害教育题

只输出题目本身，不要任何解释。"""

    resp = requests.post(
        "https://token-plan-sgp.xiaomimimo.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {MIMO_API_KEY}",
                 "Content-Type": "application/json"},
        json={"model": "mimo-v2.5-pro",
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 500}
    )
    return resp.json()["choices"][0]["message"]["content"].strip()

# ── 组装入库数据 ──────────────────────────────────
today = str(date.today())
new_items = []
for i, item in enumerate(samples[:10]):
    variant = make_variant(item, ability, grade)
    new_items.append({
        "id": f"K12-{today.replace('-','')}-{i+1:03d}",
        "prompt": variant,
        "subject": subject,
        "grade": grade,
        "ability": ability,
        "type": "选择题" if ability in ["解题能力","知识问答"] else "解答题",
        "risk": "敏感" if ability == "安全边界" else "正常",
        "source": f"ceval/{ceval_name}",
        "date_added": today,
        "active": True
    })
    print(f"  ✓ 生成第 {i+1} 条")

# ── 写入数据库 ────────────────────────────────────
db_path = os.path.expanduser("~/k12-prompt-db/data/prompts.json")
if os.path.exists(db_path):
    db = json.load(open(db_path))
else:
    db = {"prompts": []}

db["prompts"].extend(new_items)
json.dump(db, open(db_path, "w"), ensure_ascii=False, indent=2)
print(f"\n完成，今日新增 {len(new_items)} 条，数据库共 {len(db['prompts'])} 条")
