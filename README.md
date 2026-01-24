# ⚡ Body Composition Tracker (Supabase Edition)

**Supabase (PostgreSQL)** をバックエンドデータベースとして活用し、機械学習（Prophet）を用いた体重予測とTDEE（総消費カロリー）の逆算分析を行う、ボディメイク最適化ダッシュボードです。

以前のNotion版からアーキテクチャを刷新し、**RDBによる堅牢な型定義、高速なクエリ応答、およびスケーラビリティ**を実現しました。減量（Cut）や増量（Bulk）の進捗を可視化し、論理的なシミュレーションを提供します。

## 🚀 Key Features

### 1. 🔮 AI & Statistical Forecasting
* **Prophet (Meta社製AI):** 過去の体重変動トレンドや周期性を学習し、現実的な未来の体重推移を予測。
* **Linear Regression:** 単純な線形回帰トレンドも併記し、AI予測との乖離を確認可能。
* **Simulated Projection:** 「設定した摂取カロリーで生活した場合」の理論値を計算し、AI予測と比較することで計画の妥当性を評価。

### 2. 📊 TDEE Reverse Engineering (Real-time Metabolism)
* **Logic:** 毎日の「摂取カロリー」と「体重変動（10日移動平均）」から、実質的なメンテナンスカロリー（TDEE）を逆算。
* **Formula:** $TDEE = Intake - (\Delta Weight_{avg} \times 7200kcal)$
* 計算上の推定値ではなく、**「今の自分の代謝実測値」**に基づいたカロリー設定が可能。

### 3. 🍱 SQL-Based Food Log
* **Structured Data:** PostgreSQLの正規化されたテーブル構造により、データの整合性を担保。
* **Menu Master (JSONB):** セットメニューのレシピ構造を `JSONB` 型で保存。NoSQLのような柔軟性とSQLの検索性を両立。
* **Macro Analytics:** PFCバランスの比率や週次推移を高速に集計・可視化。

### 4. 📱 Mobile First & High Performance
* Streamlit × Supabase の構成により、旧来のAPI連携と比較してデータ読み込み速度が劇的に向上。ネイティブアプリのようなUXを提供。

## 🛠 Tech Stack

| Category | Technology |
| --- | --- |
| **Frontend** | [Streamlit](https://streamlit.io/) |
| **Visualization** | [Plotly](https://plotly.com/) |
| **Backend / DB** | [Supabase](https://supabase.com/) (PostgreSQL) |
| **Data Analysis** | [Pandas](https://pandas.pydata.org/), [NumPy](https://numpy.org/) |
| **Machine Learning** | [Prophet](https://facebook.github.io/prophet/), [Scikit-learn](https://scikit-learn.org/) |
| **Environment** | Python 3.11 |

## 📂 Project Structure

```text
├── app.py                # Main Application (UI / Controller)
├── logic.py              # Data Analysis & AI Logic (Model)
├── supabase_db.py        # Database Adapter (Supabase Client)
├── requirements.txt      # Dependencies
└── .streamlit/
    └── secrets.toml      # API Keys (Git-ignored)
```

## 🗄️ Database Schema (PostgreSQL)

本アプリはSupabase上に以下のテーブル構造を必要とします。

1.  **daily_logs** (日々の記録)
    * `log_date` (DATE, PK): 記録日
    * `weight` (NUMERIC): 体重
    * `calories`, `protein`, `fat`, `carbs` (NUMERIC): 栄養素
    * `note` (TEXT): メモ

2.  **food_master** (食品マスタ)
    * `id` (UUID, PK)
    * `name` (TEXT, Unique): 食品名
    * `calories`, `protein`, `fat`, `carbs`: 栄養成分

3.  **menu_master** (セットメニュー)
    * `id` (UUID, PK)
    * `name` (TEXT, Unique): セット名
    * `recipe` (**JSONB**): 食品IDと量のリスト構造

4.  **settings** (設定値 - Key-Value Store)
    * `key` (TEXT, PK): 設定キー ("target_weight" 等)
    * `value_num` (NUMERIC): 数値設定
    * `value_str` (TEXT): 文字列設定

## 🚀 Installation & Setup

### 1. Supabase Setup
Supabaseプロジェクトを作成し、SQL Editorで以下の初期化クエリを実行してテーブルを作成してください。

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Create Tables
CREATE TABLE daily_logs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    log_date DATE UNIQUE NOT NULL,
    weight NUMERIC(5, 2) NOT NULL,
    calories INTEGER DEFAULT 0,
    protein NUMERIC(5, 1) DEFAULT 0,
    fat NUMERIC(5, 1) DEFAULT 0,
    carbs NUMERIC(5, 1) DEFAULT 0,
    note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- (以下、food_master, menu_master, settings も同様に作成)
```

### 2. Local Environment
```bash
# Clone & Enter
git clone [https://github.com/yuuta66jp/bodymake-dashboard.git](https://github.com/yuuta66jp/bodymake-dashboard.git)
cd bodymake-dashboard

# Venv Setup
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install Dependencies
pip install -r requirements.txt
```
### 3. Configuration (Secrets)
ルートディレクトリに `.streamlit/secrets.toml` を作成し、Supabaseの接続情報を記述します。

```toml
[connections.supabase]
SUPABASE_URL = "[https://your-project-id.supabase.co](https://your-project-id.supabase.co)"
SUPABASE_KEY = "your-service-role-key-or-anon-key"
```

### 4. Run
```bash
streamlit run app.py
```

## 🔄 Deployment (Streamlit Community Cloud)

1. **Push to GitHub:**
   `requirements.txt` に `supabase` と `scikit-learn` が含まれていることを確認してプッシュします。

2. **Configure Secrets:**
   Streamlit CloudのDashboard設定画面（App Settings > Secrets）にて、ローカルの `secrets.toml` と同じ内容を設定してください。

## 👤 Author

* **Created by:** `yuuta66jp`
* **Goal:** 2027 Japan Class-Specific Bodybuilding Championship 🥇

---
*Happy Training!* 🏋️‍♂️
