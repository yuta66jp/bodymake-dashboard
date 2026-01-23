# ⚡ Body Composition Tracker (AI-Powered)

Notionをバックエンドデータベースとして活用し、機械学習（Prophet）を用いた体重予測とTDEE（総消費カロリー）の逆算分析を行う、ボディメイク最適化ダッシュボードです。

減量（Cut）や増量（Bulk）の進捗を可視化し、**「いつ目標を達成できるか」**を論理的にシミュレーションします。

## 🚀 Key Features

### 1. 🔮 AI & Statistical Forecasting
* **Prophet (Meta社製AI):** 過去の体重変動トレンドや周期性を学習し、現実的な未来の体重推移を予測。
* **Linear Regression:** 単純な線形回帰トレンドも併記し、AI予測との乖離を確認可能。
* **Simulated Projection:** 「もし毎日2000kcalで過ごしたら？」という理論値を計算し、AI予測（現実）と比較することで、計画の実行可能性を評価。

### 2. 📊 TDEE Reverse Engineering
* **Logic:** 毎日の「摂取カロリー」と「体重変動（7日移動平均）」から、実質的なメンテナンスカロリー（TDEE）を逆算。
* **Formula:** $TDEE = Intake - (\Delta Weight \times 7200kcal)$
* これにより、計算上のTDEEではなく、**「今の自分の代謝実測値」**に基づいたカロリー設定が可能。

### 3. 🍱 Notion-Integrated Food Log
* **Daily Log:** 食品マスタから選択、またはクイック入力で食事を記録。Notionデータベースへリアルタイム同期。
* **Menu Master:** 「朝食Aセット」のような定型セットメニューをJSON形式でNotionに保存し、ワンクリックで展開・登録可能。
* **Macro Analytics:** PFCバランス（タンパク質・脂質・炭水化物）の比率を可視化。

### 4. 📱 Mobile First Design
* スマホでの操作に最適化。ホーム画面に追加することで、ネイティブアプリのような全画面UXを提供。

## 🛠 Tech Stack

| Category | Technology |
| --- | --- |
| **Frontend** | [Streamlit](https://streamlit.io/) |
| **Visualization** | [Plotly](https://plotly.com/) |
| **Backend / DB** | [Notion API](https://developers.notion.com/) |
| **Data Analysis** | [Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/) |
| **Machine Learning** | [Prophet](https://facebook.github.io/prophet/), [Scikit-learn](https://scikit-learn.org/) |
| **Environment** | Python 3.11 |

## 📂 Project Structure

```text
├── app.py                # Main Application (UI)
├── logic.py              # Data Analysis & AI Logic
├── notion_db.py          # Notion API Wrapper (CRUD)
├── import_data.py        # CSV Import Utility
├── requirements.txt      # Dependencies
└── .streamlit/
    └── secrets.toml      # API Keys (Git-ignored)
```

## 🗄️ Database Schema (Notion)

本アプリはNotion上に以下の4つのデータベースを必要とします。

1.  **Daily Log DB** (日々の記録)
    * `Date` (Date)
    * `Weight` (Number)
    * `Calories` (Number)
    * `Protein`, `Fat`, `Carbs` (Number)
    * `Note` (Text)

2.  **Food Master DB** (食品マスタ)
    * `Name` (Title)
    * `Calories` (Number)
    * `Protein`, `Fat`, `Carbs` (Number)

3.  **Menu Master DB** (セットメニュー保存)
    * `Name` (Title)
    * `Recipe` (Text/JSON) - ※セット内容をJSON形式で格納

4.  **Settings DB** (設定値管理)
    * `Key` (Title) - 例: "target_weight", "current_phase"
    * `Value` (Number)
    * `ValueStr` (Text)

## 🚀 Installation

推奨環境: Python 3.11 (Prophetの互換性維持のため)

```bash
# 1. Clone the repository
git clone [https://github.com/yuuta66jp/bodymake-dashboard.git](hhttps://github.com/yuuta66jp/bodymake-dashboard.git)
cd bodymake-dashboard
```

# 2. Create virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Mac/Linux
# venv\Scripts\activate   # Windows
```

# 3. Install dependencies
```bash
pip install -r requirements.txt
```

### Configuration
ルートディレクトリに `.streamlit/secrets.toml` を作成し、APIキーを設定してください。

```toml
NOTION_TOKEN = "secret_xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
DATABASE_ID = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"       # Daily Log
FOOD_DATABASE_ID = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # Food Master
MENU_DATABASE_ID = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx"  # Menu Master
SETTINGS_DATABASE_ID = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxx" # Settings
```

### Run
ローカル環境でアプリを起動します。

```bash
streamlit run app.py
```

## 🔄 Deployment

本アプリは **Streamlit Cloud** に連携済みです。
GitHubの `main` ブランチへプッシュすると、自動的にビルドとデプロイが実行されます。

1. **Push to GitHub:**
   ```bash
   git add .
   git commit -m "Update app"
   git push origin main
   ```

2. **Streamlit Cloud:**
GitHubへのプッシュを自動検知し、数分で最新版が本番環境に反映されます。
デプロイ状況は Streamlit Cloud 管理画面の "Manage app" から確認できます。

## 👤 Author

* **Created by:** `yuuta66jp`
* **Goal:** 2027 Japan Class-Specific Bodybuilding Championship 🥇

---
*Happy Training!* 🏋️‍♂️
