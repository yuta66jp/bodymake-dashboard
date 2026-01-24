import datetime
from datetime import date, timedelta

# 自作モジュールのインポート
import logic
import notion_db
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# ==========================================
# 1. 初期設定 & シークレット読込
# ==========================================
st.set_page_config(page_title="Body Composition Tracker", page_icon="⚡", layout="wide")
FAT_CALORIES_PER_KG = 7200  # 脂肪1kgあたりのカロリー (7200kcal)

# Secretsの読み込み (.streamlit/secrets.toml)
try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
    DATABASE_ID = st.secrets["DATABASE_ID"]  # Daily Log DB
    FOOD_DATABASE_ID = st.secrets["FOOD_DATABASE_ID"]  # Food Master DB
    SETTINGS_DATABASE_ID = st.secrets["SETTINGS_DATABASE_ID"]  # Settings DB
    MENU_DATABASE_ID = st.secrets["MENU_DATABASE_ID"]  # Menu Master DB (New!)
except:
    st.error("Secrets not found. Please configure .streamlit/secrets.toml")
    st.stop()

# ==========================================
# 2. カスタムCSS (UI調整)
# ==========================================
st.markdown(
    """<style>
.block-container { padding-top: 1rem; }

/* KPIカード（Metric）のガラスモーフィズム風スタイル */
[data-testid="stMetric"] {
    background-color: rgba(255, 255, 255, 0.03);
    border-radius: 12px;
    border: 1px solid rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
    padding: 15px;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    min-height: 120px;
    display: flex;
    flex-direction: column;
    justify-content: center;
    transition: all 0.3s ease;
}

[data-testid="stMetric"]:hover {
    transform: translateY(-5px);
    box-shadow: 0 10px 20px rgba(0, 0, 0, 0.2);
    border-color: #F59E0B;
}

/* ボタンのグラデーションスタイル */
div.stButton > button {
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%);
    color: white;
    width: 100%;
    border: none;
    border-radius: 8px;
    font-weight: 600;
}
</style>""",
    unsafe_allow_html=True,
)


def main():
    # ==========================================
    # 3. グローバル設定のロード (Start-up Load)
    # ==========================================
    # サイドバーではなく、アプリ起動時にDBから設定値を読み込んでおく
    # これにより、Tab1(Simulator)などがサイドバーに依存せずに描画できる
    try:
        settings_data = notion_db.fetch_settings(SETTINGS_DATABASE_ID, NOTION_TOKEN)
    except:
        settings_data = {}

    # --- デフォルト値と設定値の展開 ---
    # A. Goal Date
    cfg_goal_date_str = settings_data.get("target_date", "2026-05-30")
    try:
        cfg_goal_date = datetime.datetime.strptime(
            str(cfg_goal_date_str), "%Y-%m-%d"
        ).date()
    except:
        cfg_goal_date = date(2026, 5, 30)

    # B. Phase (Cut / Bulk)
    cfg_phase_str = settings_data.get("current_phase", "Cut")
    cfg_is_cut = "Cut" in cfg_phase_str

    # C. Goal Weight
    cfg_goal_weight = float(settings_data.get("target_weight", 58.5))

    # D. Monthly Target
    cfg_monthly_target = float(settings_data.get("monthly_target", 68.0))

    # ==========================================
    # 4. サイドバー (入力専用)
    # ==========================================
    with st.sidebar:
        # 設定項目を削除し、Daily Logのみにする
        st.header("📝 Daily Log")
        st.caption("食品を選んでカートに追加 → 保存")

        # --- データ取得 (食品マスタ & セットメニュー) ---
        try:
            food_dict = notion_db.fetch_food_list(FOOD_DATABASE_ID, NOTION_TOKEN)
            set_dict = notion_db.fetch_menu_list(
                MENU_DATABASE_ID, NOTION_TOKEN
            )  # Menu DBから取得

            food_list = sorted(list(food_dict.keys()))
            set_list = [f"[SET] {k}" for k in set_dict.keys()]  # セットには目印をつける
            menu_options = set_list + food_list
        except:
            menu_options = []
            food_dict = {}
            set_dict = {}

        # --- カートシステム (Session State管理) ---
        if "meal_cart" not in st.session_state:
            st.session_state.meal_cart = []

        def remove_from_cart(idx):
            """カートから指定インデックスのアイテムを削除"""
            st.session_state.meal_cart.pop(idx)

        def clear_cart():
            """カートを全消去"""
            st.session_state.meal_cart = []

        def add_to_cart():
            """選択された食品/セットを計算してカートに追加"""
            selected = st.session_state.picker_menu
            input_amount = st.session_state.picker_amount

            # Pattern A: セットメニューが選択された場合
            if selected.startswith("[SET] "):
                real_name = selected.replace("[SET] ", "")
                if real_name in set_dict:
                    recipe = set_dict[real_name]  # レシピ(リスト)を取得
                    # レシピ内のアイテムを1つずつ展開してカートに入れる
                    for item in recipe:
                        fname = item["name"]
                        famt = item["amount"]  # レシピで定義された量(g)を使用

                        if fname in food_dict:
                            base = food_dict[fname]
                            ratio = famt / 100.0
                            st.session_state.meal_cart.append(
                                {
                                    "name": fname,
                                    "amount": famt,
                                    "kcal": int(base["cal"] * ratio),
                                    "p": float(base["p"] * ratio),
                                    "f": float(base["f"] * ratio),
                                    "c": float(base["c"] * ratio),
                                }
                            )

            # Pattern B: 単品食品が選択された場合
            elif selected in food_dict:
                base = food_dict[selected]
                ratio = input_amount / 100.0
                st.session_state.meal_cart.append(
                    {
                        "name": selected,
                        "amount": input_amount,
                        "kcal": int(base["cal"] * ratio),
                        "p": float(base["p"] * ratio),
                        "f": float(base["f"] * ratio),
                        "c": float(base["c"] * ratio),
                    }
                )

        # --- UI: 食品ピッカー ---
        with st.container(border=True):
            st.caption("① Select Food / Set")
            st.selectbox("Menu", menu_options, key="picker_menu")
            st.number_input(
                "Amount (g)",
                0,
                2000,
                100,
                10,
                key="picker_amount",
                help="単品選択時のみ有効。セット選択時は無視されます(レシピ通りの量が入ります)",
            )
            if st.button("➕ Add to List"):
                add_to_cart()

        # --- UI: カート内容表示 ---
        total_k, total_p, total_f, total_c = 0, 0, 0, 0
        if st.session_state.meal_cart:
            st.caption("② Current List")
            st.markdown("---")

            # 各アイテムを表示＆削除ボタン配置
            for i, item in enumerate(st.session_state.meal_cart):
                total_k += item["kcal"]
                total_p += item["p"]
                total_f += item["f"]
                total_c += item["c"]

                c_text, c_btn = st.columns([4, 1])
                with c_text:
                    st.text(f"{item['name']} ({item['amount']}g)\n{item['kcal']}kcal")
                with c_btn:
                    st.button(
                        "🗑️",
                        key=f"del_{i}",
                        on_click=remove_from_cart,
                        args=(i,),
                        help="Remove item",
                    )

            st.markdown("---")
            if st.button("🗑️ Clear All"):
                clear_cart()
                st.rerun()

        # --- UI: 保存フォーム ---
        st.caption("③ Confirm & Save")
        with st.form("daily_log_form", clear_on_submit=True):
            d_in = st.date_input("Date", date.today())
            w_in = st.number_input("Weight (kg)", 0.0, 150.0, step=0.1, format="%.1f")

            st.markdown(f"**Total: {int(total_k)} kcal**")

            # カートの合計値を初期値としてセット (手動微調整も可能)
            c1, c2 = st.columns(2)
            fk = c1.number_input("Kcal", 0, 10000, int(total_k), step=10)
            fp = c2.number_input(
                "P (g)", 0.0, 500.0, float(total_p), step=1.0, format="%.1f"
            )
            ff = c1.number_input(
                "F (g)", 0.0, 500.0, float(total_f), step=1.0, format="%.1f"
            )
            fc = c2.number_input(
                "C (g)", 0.0, 1000.0, float(total_c), step=1.0, format="%.1f"
            )
            note = st.text_input("Memo", placeholder="Training content, mood, etc.")

            if st.form_submit_button("💾 Save Log", type="primary"):
                notion_db.add_daily_log(
                    DATABASE_ID,
                    NOTION_TOKEN,
                    d_in,
                    w_in,
                    note,
                    kcal=fk,
                    p=round(fp, 1),
                    f=round(ff, 1),
                    c=round(fc, 1),
                )
                st.success("Saved successfully!")
                st.session_state.meal_cart = []  # 保存成功時にカートを空にする
                st.rerun()

    # ==========================================
    # 5. メインダッシュボード (KPI)
    # ==========================================
    st.title("⚡ Body Composition Tracker")

    # Notionから体重データを取得
    raw_df = notion_db.fetch_raw_data(DATABASE_ID, NOTION_TOKEN)
    if raw_df.empty:
        st.warning("No data found in Notion.")
        st.stop()

    # 分析ロジック実行 (Prophet等)
    # ※ サイドバーではなく、冒頭でロードした cfg_goal_date を使用
    df = logic.enrich_data(raw_df, cfg_goal_date)
    hist_df = notion_db.fetch_history_csv()

    with st.spinner("Analyzing..."):
        p_val, p_fore = logic.run_prophet_model(df, cfg_goal_date)
        l_val = logic.run_linear_model(df, cfg_goal_date)

    # KPI 計算
    curr = df["y"].iloc[-1]
    days = (cfg_goal_date - date.today()).days
    days = 1 if days < 1 else days
    gap = p_val - cfg_goal_weight  # 予測値 - 目標値

    # KPI 表示
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Weight", f"{curr:.1f} kg", f"{(curr - cfg_goal_weight):+.1f}")
    c2.metric("Days Left", f"{days}")

    # Forecast アラート判定
    is_bad_forecast = False
    if cfg_is_cut:
        is_bad_forecast = gap > 0.1  # 減量なのに目標より重い
    else:
        is_bad_forecast = (gap < -0.2) or (gap > 0.5)  # 増量なのに軽すぎる or 増えすぎ

    c3.metric(
        "Forecast",
        f"{p_val:.1f} kg",
        f"{gap:+.1f}",
        delta_color="inverse" if is_bad_forecast else "normal",
    )

    c4.metric("Trend (Lin)", f"{l_val:.1f} kg")

    # Action (カロリー調整提案)
    adj = int((abs(gap) * FAT_CALORIES_PER_KG) / days)
    action_label = "Keep"
    status_label = "On Track"
    alert_color = "off"

    if cfg_is_cut:
        if gap > 0.2:
            action_label = f"-{adj} kcal"
            status_label = "Cut Needed"
            alert_color = "inverse"
    else:
        if gap < -0.2:
            action_label = f"+{adj} kcal"
            status_label = "Push Harder"
            alert_color = "inverse"
        elif gap > 0.5:
            action_label = f"-{adj} kcal"
            status_label = "Slow Down"
            alert_color = "inverse"

    c5.metric("Action", action_label, status_label, delta_color=alert_color)

    # ==========================================
    # 6. タブ構成
    # ==========================================
    # Tab 7 (Settings) を追加
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        [
            "📉 Simulator",
            "📜 History",
            "🏆 Comp History",
            "📊 Stats",
            "🔥 Metabolism",
            "🍱 Database",
            "⚙️ Settings",  # New!
        ]
    )

    # --- Tab 1: Simulator ---
    with tab1:
        st.markdown("### 📉 Simulator")

        # TDEE推定値 (データがない場合は2400)
        base_tdee = (
            int(df["real_tdee_smooth"].iloc[-1])
            if pd.notna(df.get("real_tdee_smooth", pd.Series([np.nan])).iloc[-1])
            else 2400
        )

        sc1, sc2, sc3 = st.columns([2, 2, 1])
        p_in = sc1.slider("Plan Intake", 1000, 4000, 2000, 50)
        p_out = sc2.slider("Extra Burn", 0, 1000, 0, 50)

        sim_d = (p_in - (base_tdee + p_out)) / FAT_CALORIES_PER_KG

        # AI着地日予測
        est_date_str = "Unknown"
        future_hit = p_fore[
            (p_fore["ds"] > pd.to_datetime(date.today()))
            & (p_fore["yhat"] <= cfg_goal_weight)
        ]

        if not future_hit.empty:
            hit_date = future_hit["ds"].iloc[0]
            est_date_str = hit_date.strftime("%m/%d")
        else:
            if curr > cfg_goal_weight and sim_d < 0:
                est_days = int((curr - cfg_goal_weight) / abs(sim_d))
                est_date_str = (date.today() + timedelta(days=est_days)).strftime(
                    "%m/%d"
                )
            else:
                est_date_str = "∞"

        with sc3:
            st.markdown(
                f"""
                <div style="
                    background-color: rgba(255, 255, 255, 0.05);
                    padding: 10px 20px;
                    border-radius: 10px;
                    border-left: 5px solid #F59E0B;
                    margin-bottom: 20px;">
                    <p style="margin: 0; font-size: 0.8rem; color: #888;">AI Est. Date</p>
                    <p style="margin: 0; font-size: 1.5rem; font-weight: bold; color: #FFF;">
                        {est_date_str} <span style="font-size: 1rem; font-weight: normal;">(Sim)</span>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # グラフ描画
        fig = go.Figure()

        # 1. Sim Plan (参考: 白点線)
        sim_days = (cfg_goal_date - date.today()).days + 14
        d_ls = [date.today() + timedelta(days=x) for x in range(sim_days)]
        w_ls = [curr + (sim_d * x) for x in range(sim_days)]

        fig.add_trace(
            go.Scatter(
                x=d_ls,
                y=w_ls,
                mode="lines",
                name="Sim Plan (Ref)",
                line=dict(color="rgba(255, 255, 255, 0.5)", width=2, dash="dot"),
                hovertemplate="%{x|%Y/%m/%d}<br>Plan: %{y:.1f}kg<extra></extra>",
            )
        )

        # 2. Forecast (AI: オレンジ線)
        fig.add_trace(
            go.Scatter(
                x=p_fore["ds"],
                y=p_fore["yhat"],
                mode="lines",
                name="Forecast (AI)",
                line=dict(color="rgba(255, 136, 0, 0.7)", width=4),
                hovertemplate="%{x|%Y/%m/%d}<br>Weight: %{y:.1f}kg<extra></extra>",
            )
        )

        # 3. SMA7 (実績: 水色線)
        if pd.notna(df["SMA_7"].iloc[-1]):
            fig.add_trace(
                go.Scatter(
                    x=df["ds"],
                    y=df["SMA_7"],
                    mode="lines",
                    name="SMA7",
                    line=dict(color="#00BFFF", width=3),
                    hovertemplate="%{x|%Y/%m/%d}<br>Avg: %{y:.1f}kg<extra></extra>",
                )
            )

        # 4. Raw Data (実績: 点)
        fig.add_trace(
            go.Scatter(
                x=df["ds"],
                y=df["y"],
                mode="markers",
                name="Raw",
                marker=dict(color="rgba(0, 191, 255, 0.4)", size=6),
                hovertemplate="%{x|%Y-%m-%d}<br>Raw: %{y:.1f}kg<extra></extra>",
            )
        )

        # 補助線 (月区切り線 & 目標ライン)
        min_date = df["ds"].min()
        max_date = d_ls[-1]
        month_starts = pd.date_range(start=min_date, end=max_date, freq="MS")

        for d in month_starts:
            fig.add_vline(
                x=d,
                line_width=1,
                line_dash="dot",
                line_color="rgba(255, 255, 255, 0.15)",
            )

        fig.add_hline(
            y=cfg_goal_weight, line_dash="dot", line_color="red", annotation_text="Goal"
        )

        if cfg_monthly_target > 0:
            fig.add_hline(
                y=cfg_monthly_target,
                line_dash="dashdot",
                line_color="orange",
                annotation_text="Monthly Target",
            )

        # 1. 基準となる日付の取得（すでにmain内で定義済みの変数を使用）
        # cfg_goal_date は datetime.date型なので、計算のためにTimestamp型に変換します
        target_date_ts = pd.to_datetime(cfg_goal_date)

        # 2. 表示範囲の計算
        # 開始点：最新データから1ヶ月前（直近の進捗をズーム）
        latest_data_date = df["ds"].max()
        start_date = latest_data_date - pd.DateOffset(months=1)

        # 終端点：大会当日の「15日後」に設定
        # これにより、大会当日を過ぎた後の推移予測や、当日の達成感を視覚的に確保します
        graph_end_date = target_date_ts + pd.DateOffset(days=15)

        # --- 1. Y軸の表示範囲を動的に計算 ---
        # 目標体重（例: 58.0kg）から2kg引いた値を下限に設定
        yaxis_min = float(cfg_goal_weight) - 2.0
        # データ内の最大値に少し余白（2.5kg）を足して上限に設定
        yaxis_max = df["y"].max() + 2.5

        fig.update_layout(
            height=500,
            template="plotly_dark",
            margin=dict(l=20, r=20, t=20, b=20),
            legend=dict(orientation="h", y=1.05),
            xaxis=dict(
                range=[start_date, graph_end_date],  # 初期ズーム
                type="date",
                rangeslider=dict(visible=True),  # ナビゲーションを確保
                showgrid=True,  # グリッドを表示
                gridcolor="rgba(128,128,128, 0.2)",  # 視覚的なノイズを抑制
            ),
            yaxis=dict(
                range=[yaxis_min, yaxis_max],
                tickformat=".1f",
                dtick=2.5,
                showgrid=True,
                gridcolor="rgba(128,128,128, 0.2)",
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- 追加：直近の体重推移テーブル ---
        st.markdown("#### 📋 Recent Weight Logs")

        # 1. データ抽出（前回推奨したパターンBを採用）
        table_cols = ["ds", "y"]
        if "Calories" in df.columns:
            table_cols.append("Calories")

        log_df = df[table_cols].copy()

        # 2. 前日比の計算（昇順の状態で計算してから、表示用に降順へ）
        log_df["Diff"] = log_df["y"].diff().round(2)
        log_df = log_df.sort_values("ds", ascending=False).head(14)

        # 3. 条件付き書式（Coloring Logic）の定義
        def style_diff(val):
            if pd.isna(val) or val == 0:
                return ""
            # プラスなら赤、マイナスなら青（エンジニア好みの明瞭な色指定）
            color = "#FF4B4B" if val > 0 else "#1C83E1"
            return f"color: {color}; font-weight: bold;"

        # 4. Pandas Styler の適用
        # format() メソッドで "+0.50 kg" の形式を担保し、mapで色を塗る
        styled_df = log_df.style.map(style_diff, subset=["Diff"]).format(
            {
                "y": "{:.1f} kg",
                "Diff": "{:+.1f} kg",
                "Calories": "{:,.0f} kcal" if "Calories" in log_df.columns else "{}",
            }
        )

        # 5. Streamlitで表示
        # column_config でヘッダー名を整える（Stylerを使う場合はformat指定はStyler側が優先されます）
        st.dataframe(
            styled_df,
            use_container_width=True,
            column_config={
                "ds": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
                "y": "Weight",
                "Diff": "ΔWeight",
                "Calories": "Intake",
            },
            hide_index=True,
        )

    # --- Tab 2: History ---
    with tab2:
        if hist_df is not None:
            dr = st.slider("Display Range (Days)", 60, 300, 120, 10)
            fig2 = go.Figure()

            # 過去の大会データのスタイル設定
            STYLE_CONFIG = {
                "2021_TokyoNovice": dict(
                    color="rgba(150, 150, 150, 0.5)", dash="dot", width=2
                ),
                "2022_TokyoNovice": dict(
                    color="rgba(150, 150, 150, 0.5)", dash="dash", width=2
                ),
                "2023_TokyoNovice": dict(
                    color="rgba(200, 200, 200, 0.8)", dash="dashdot", width=2
                ),
                "2024_TokyoNovice": dict(
                    color="rgba(100, 100, 100, 0.5)", dash="longdash", width=2
                ),
                "2025_TokyoNovice": dict(
                    color="rgba(120, 120, 120, 0.5)", dash="solid", width=2
                ),
            }
            DEFAULT_STYLE = dict(color="rgba(100, 100, 100, 0.3)", dash="dot", width=1)

            # 過去データ描画
            for l in hist_df["Label"].unique():
                s = hist_df[
                    (hist_df["Label"] == l) & (hist_df["days_out"] > -dr)
                ].sort_values("Date")
                if not s.empty:
                    style = STYLE_CONFIG.get(l, DEFAULT_STYLE)
                    fig2.add_trace(
                        go.Scatter(
                            x=s["days_out"],
                            y=s["Weight"].rolling(7, 1).mean().round(1),
                            mode="lines",
                            name=l,
                            line=style,
                            hovertemplate="<b>%{fullData.name}</b><br>Days Out: %{x}<br>Weight: %{y:.1f}kg<extra></extra>",
                        )
                    )

            # 今回のデータ描画
            cur = df[df["days_out"] > -dr]
            fig2.add_trace(
                go.Scatter(
                    x=cur["days_out"],
                    y=cur["SMA_7"].round(1),
                    mode="lines",
                    name="Current",
                    line=dict(color="#FF0000", width=5, dash="solid"),
                    hovertemplate="<b>Current Season</b><br>Days Out: %{x}<br>Weight: %{y:.1f}kg<extra></extra>",
                )
            )

            fig2.update_layout(
                height=500,
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis_title="Days Out (0=Contest)",
                yaxis=dict(
                    title="Weight (kg)",
                    tickformat=".1f",
                    showgrid=True,
                    gridcolor="rgba(128,128,128,0.1)",
                ),
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.1)"),
                legend=dict(
                    orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1
                ),
                hoverlabel=dict(
                    bgcolor="#262730", font_color="white", bordercolor="#444444"
                ),
            )
            st.plotly_chart(fig2, use_container_width=True)

            # ========================================================
            # 【NEW】 📅 YoY Comparison Table (YYYY-MM-DD & Descending)
            # ========================================================
            st.markdown("### 📅 Recent 14 Days Comparison (Actual vs Past)")

            # 1. データ整理（日付順）
            df_sorted = df.sort_values("ds")

            if not df_sorted.empty:
                target_date_obj = cfg_goal_date
                current_date_val = df_sorted["ds"].iloc[-1].date()

                # 2. 表示したい日付リスト（今日 〜 13日前）
                date_objects = [current_date_val - timedelta(days=i) for i in range(14)]

                # 3. ベースのデータフレーム作成
                comp_df = pd.DataFrame({"DateObj": date_objects})

                # 【修正1】フォーマットを YYYY-MM-DD に変更
                comp_df["2026 Date"] = comp_df["DateObj"].apply(
                    lambda d: d.strftime("%Y-%m-%d")
                )

                comp_df["Days Remaining"] = comp_df["DateObj"].apply(
                    lambda d: (target_date_obj - d).days
                )

                # ----------------------------------------------------
                # A. 今年の実績 (2026 Actual) を結合
                # ----------------------------------------------------
                df_sorted["date_obj"] = df_sorted["ds"].dt.date

                comp_df = comp_df.merge(
                    df_sorted[["date_obj", "y"]].rename(
                        columns={"y": "2026 Actual", "date_obj": "DateObj"}
                    ),
                    on="DateObj",
                    how="left",
                )

                # ----------------------------------------------------
                # B. 過去の実績 (Past Years) を結合
                # ----------------------------------------------------
                past_labels = []

                if hist_df is not None and not hist_df.empty:
                    # 日付型変換とフォーマット
                    hist_df["Date"] = pd.to_datetime(hist_df["Date"])
                    # 【修正1】フォーマットを YYYY-MM-DD に変更
                    hist_df["date_str"] = hist_df["Date"].dt.strftime("%Y-%m-%d")

                    hist_df["join_key"] = hist_df["days_out"].astype(int)

                    # 符号判定
                    sample_val = (
                        hist_df["days_out"].dropna().iloc[0]
                        if not hist_df["days_out"].dropna().empty
                        else 0
                    )
                    is_negative_hist = sample_val < 0

                    if is_negative_hist:
                        comp_df["join_key_hist"] = -1 * comp_df["Days Remaining"]
                    else:
                        comp_df["join_key_hist"] = comp_df["Days Remaining"]

                    # Pivot
                    pivot_weight = hist_df.pivot_table(
                        index="join_key",
                        columns="Label",
                        values="Weight",
                        aggfunc="mean",
                    )
                    pivot_date = hist_df.pivot_table(
                        index="join_key",
                        columns="Label",
                        values="date_str",
                        aggfunc="first",
                    )

                    past_labels = list(pivot_weight.columns)
                    # 【修正2】新しい年が左に来るように降順ソート (2025 -> 2024 -> ...)
                    past_labels.sort(reverse=True)

                    # 結合
                    comp_df = comp_df.merge(
                        pivot_weight,
                        left_on="join_key_hist",
                        right_index=True,
                        how="left",
                    )
                    comp_df = comp_df.merge(
                        pivot_date.add_suffix("_Date"),
                        left_on="join_key_hist",
                        right_index=True,
                        how="left",
                    )

                # ----------------------------------------------------
                # C. 差分計算 & 表示設定
                # ----------------------------------------------------
                def format_diff_row(row, label_name):
                    past_val = row[label_name]
                    current_val = row["2026 Actual"]

                    if pd.isna(past_val):
                        weight_str = "-"
                    elif pd.isna(current_val):
                        weight_str = f"{past_val:.1f}"
                    else:
                        diff = current_val - past_val
                        weight_str = f"{past_val:.1f} ({diff:+.1f})"
                    return weight_str

                display_cols = ["Days Remaining", "2026 Date", "2026 Actual"]

                # 【修正3】日付が見切れないように width="medium" に変更
                col_config = {
                    "Days Remaining": st.column_config.NumberColumn(
                        "Days Out", format="%d", width="small"
                    ),
                    "2026 Date": st.column_config.TextColumn("Date", width="medium"),
                    "2026 Actual": st.column_config.NumberColumn(
                        "🔥 Actual", format="%.1f kg", width="small"
                    ),
                }

                # 降順ソートされた過去ラベル順にカラムを追加
                for label in past_labels:
                    date_col = f"{label}_Date"
                    weight_col = label
                    disp_weight_col = f"{label} Weight"

                    if date_col in comp_df.columns:
                        comp_df[date_col] = comp_df[date_col].fillna("-")

                    if weight_col in comp_df.columns:
                        comp_df[disp_weight_col] = comp_df.apply(
                            lambda r: format_diff_row(r, weight_col), axis=1
                        )

                    display_cols.append(date_col)
                    display_cols.append(disp_weight_col)

                    year_prefix = label.split("_")[0] if "_" in label else label

                    col_config[date_col] = st.column_config.TextColumn(
                        f"{year_prefix} Date",
                        width="medium",  # mediumへ拡大
                    )
                    col_config[disp_weight_col] = st.column_config.TextColumn(
                        f"{year_prefix} Weight", width="medium"
                    )

                # ----------------------------------------------------
                # D. テーブル表示
                # ----------------------------------------------------
                final_df = comp_df[display_cols]

                st.dataframe(
                    final_df,
                    use_container_width=True,
                    column_config=col_config,
                    hide_index=True,
                )
            else:
                st.warning("Daily logs are empty.")
        else:
            st.info("No history.csv found.")

    # --- Tab 3: Comp History ---
    with tab3:
        if hist_df is not None:
            st.markdown("### 🏆 Competition History")

            # データ結合
            curr_formatted = df[["ds", "y"]].rename(
                columns={"ds": "Date", "y": "Weight"}
            )
            curr_formatted["Label"] = "Current Season"
            full_history = pd.concat(
                [hist_df[["Date", "Weight", "Label"]], curr_formatted],
                ignore_index=True,
            )
            full_history = full_history.sort_values("Date")

            # 1. Timeline Chart
            st.subheader("📅 Career Timeline")
            fig_all = go.Figure()
            colors = ["#3B82F6", "#10B981", "#EF4444", "#8B5CF6", "#06B6D4", "#EC4899"]
            unique_labels = full_history["Label"].unique()

            for i, label in enumerate(unique_labels):
                d = full_history[full_history["Label"] == label]
                if "Current" in label:
                    col, wid, op = "#F59E0B", 4, 1.0
                else:
                    col, wid, op = colors[i % len(colors)], 2, 0.8

                fig_all.add_trace(
                    go.Scatter(
                        x=d["Date"],
                        y=d["Weight"],
                        mode="lines",
                        name=label,
                        line=dict(color=col, width=wid),
                        opacity=op,
                        hovertemplate="<b>%{data.name}</b><br>Date: %{x|%Y/%m}<br>Weight: %{y:.1f}kg<extra></extra>",
                    )
                )

            fig_all.update_layout(
                height=400,
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                xaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.1)"),
                yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.1)"),
                legend=dict(orientation="h", y=1.1),
                hoverlabel=dict(
                    bgcolor="#262730", font_color="white", bordercolor="#444444"
                ),
            )
            st.plotly_chart(fig_all, use_container_width=True)
            st.divider()

            # 2. Season Low Bar Chart
            st.subheader("📉 Season Low (Best Condition)")
            season_stats = full_history.groupby("Label")["Weight"].min().reset_index()
            season_stats.columns = ["Season", "MinWeight"]

            # 年の抽出ロジック
            def extract_year(label):
                if "Current" in label:
                    return 9999
                import re

                match = re.search(r"20\d{2}", str(label))
                return int(match.group()) if match else 0

            season_stats["Year"] = season_stats["Season"].apply(extract_year)
            season_stats = season_stats.sort_values("Year")
            season_stats["Prev"] = season_stats["MinWeight"].shift(1)
            season_stats["Delta"] = season_stats["MinWeight"] - season_stats["Prev"]

            y_min = season_stats["MinWeight"].min() - 3
            y_max = season_stats["MinWeight"].max() + 2

            fig_bar = go.Figure()
            fig_bar.add_trace(
                go.Bar(
                    x=season_stats["Season"],
                    y=season_stats["MinWeight"],
                    text=season_stats.apply(
                        lambda x: f"{x['MinWeight']:.1f}kg"
                        + (f" ({x['Delta']:+.1f})" if pd.notna(x["Delta"]) else ""),
                        axis=1,
                    ),
                    textposition="auto",
                    marker_color="#3B82F6",  # 青で統一
                    hovertemplate="<b>%{x}</b><br>Min: %{y:.1f}kg<extra></extra>",
                )
            )

            fig_bar.update_layout(
                height=350,
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                yaxis=dict(
                    range=[y_min, y_max],
                    title="Min Weight (kg)",
                    gridcolor="rgba(128,128,128,0.1)",
                ),
                xaxis=dict(title="Season"),
                showlegend=False,
                hoverlabel=dict(
                    bgcolor="#262730", font_color="white", bordercolor="#444444"
                ),
            )
            st.plotly_chart(fig_bar, use_container_width=True)
        else:
            st.info("No history.csv found.")

    # --- Tab 4: Stats ---
    with tab4:
        st.markdown("### 📊 Advanced Analytics")
        # 週次集計 (Weekly Aggregation)
        w_df = df.set_index("ds").resample("W").mean(numeric_only=True).reset_index()

        if len(w_df) >= 2:
            this_week = w_df.iloc[-1]
            last_week = w_df.iloc[-2]

            # Metric A: Weekly RoL (減少率)
            weight_diff = this_week["y"] - last_week["y"]
            rol_pct = (weight_diff / last_week["y"]) * 100

            if -1.5 <= rol_pct <= -0.5:
                rol_color, rol_msg = "normal", "Ideal Pace 🎯"
            elif rol_pct < -1.5:
                rol_color, rol_msg = "inverse", "Too Fast! ⚠️"
            else:
                rol_color, rol_msg = "off", "Slow / Bulk 🐢"

            # Metric B: Protein Ratio
            p_val_avg = this_week.get("Protein", 0)
            cal_val_avg = this_week.get("Calories", 1)
            if cal_val_avg == 0:
                cal_val_avg = 1  # ゼロ除算防止
            p_ratio = (p_val_avg * 4 / cal_val_avg) * 100

            k1, k2, k3 = st.columns(3)
            k1.metric(
                "Weekly Weight Change",
                f"{weight_diff:.2f} kg",
                f"{rol_pct:.2f} %",
                delta_color=rol_color,
            )
            k1.caption(f"Status: {rol_msg}")

            k2.metric(
                "Avg Intake (Week)",
                f"{cal_val_avg:.0f} kcal",
                f"{(cal_val_avg - last_week.get('Calories', 0)):.0f} kcal",
                delta_color="inverse",
            )
            k3.metric("Protein Ratio", f"{p_ratio:.1f} %", "Target: >30%")

        st.markdown("---")

        # Macro Composition Chart
        if "Protein" in df.columns:
            st.subheader("🥩 Macro Composition")
            df["P_cal"] = df["Protein"] * 4
            df["F_cal"] = df["Fat"] * 9
            df["C_cal"] = df["Carbs"] * 4
            df["Total_cal_calc"] = df["P_cal"] + df["F_cal"] + df["C_cal"]
            df["Total_cal_calc"] = df["Total_cal_calc"].replace(0, 1)

            df["P%"] = (df["P_cal"] / df["Total_cal_calc"]) * 100
            df["F%"] = (df["F_cal"] / df["Total_cal_calc"]) * 100
            df["C%"] = (df["C_cal"] / df["Total_cal_calc"]) * 100

            recent = df.tail(60)
            fig_macro = go.Figure()
            fig_macro.add_trace(
                go.Scatter(
                    x=recent["ds"],
                    y=recent["P%"],
                    mode="lines",
                    name="Protein",
                    stackgroup="one",
                    line=dict(width=0),
                    fillcolor="rgba(59, 130, 246, 0.7)",
                    hovertemplate="Date: %{x|%Y-%m-%d}<br>Protein: %{y:.0f}%<extra></extra>",
                )
            )
            fig_macro.add_trace(
                go.Scatter(
                    x=recent["ds"],
                    y=recent["F%"],
                    mode="lines",
                    name="Fat",
                    stackgroup="one",
                    line=dict(width=0),
                    fillcolor="rgba(234, 179, 8, 0.7)",
                    hovertemplate="Date: %{x|%Y-%m-%d}<br>Fat: %{y:.0f}%<extra></extra>",
                )
            )
            fig_macro.add_trace(
                go.Scatter(
                    x=recent["ds"],
                    y=recent["C%"],
                    mode="lines",
                    name="Carbs",
                    stackgroup="one",
                    line=dict(width=0),
                    fillcolor="rgba(16, 185, 129, 0.7)",
                    hovertemplate="Date: %{x|%Y-%m-%d}<br>Carbs: %{y:.0f}%<extra></extra>",
                )
            )

            fig_macro.update_layout(
                height=350,
                template="plotly_dark",
                margin=dict(l=0, r=0, t=30, b=0),
                yaxis=dict(range=[0, 100]),
            )
            st.plotly_chart(fig_macro, use_container_width=True)
        else:
            st.info("No Macro data available yet.")

        # ========================================================
        # 【NEW】 🥦 Daily Nutrition Breakdown (Compact & Updated)
        # ========================================================
        st.subheader("🥦 Daily Nutrition Breakdown")

        # 1. 各栄養素の上限値設定 (Goal Setting: Updated)
        # ----------------------------------------------------
        # Target: 2500 kcal
        # Balance: P(200g) : F(60g) : C(295g)
        # ※ 脂質を10g減らし(90kcal)、炭水化物を約22g追加(88kcal)
        # ----------------------------------------------------
        LIMIT_CAL = 2500
        LIMIT_P = 200
        LIMIT_F = 50  # 70g -> 60g に減量
        LIMIT_C = 320  # 270g -> 295g に増量 (約 +25g)

        # 2. カラム探索とデータ抽出
        target_cols = ["ds", "Calories"]
        p_key = next((k for k in ["P", "Protein", "p"] if k in df.columns), None)
        f_key = next((k for k in ["F", "Fat", "f"] if k in df.columns), None)
        c_key = next((k for k in ["C", "Carbs", "c"] if k in df.columns), None)

        if p_key and f_key and c_key:
            target_cols.extend([p_key, f_key, c_key])
            nutri_df = (
                df[target_cols].copy().sort_values("ds", ascending=False).head(14)
            )
            nutri_df = nutri_df.fillna(0)

            # 3. 表示用データの整形（g と % の結合ロジック）
            cal_safe = nutri_df["Calories"].replace(0, 1)

            def format_pfc(row, key, cal_factor):
                g_val = row[key]
                pct = (
                    (g_val * cal_factor / row["Calories"] * 100)
                    if row["Calories"] > 0
                    else 0
                )
                # Python f-string で "100.0g (50%)" の形式を作成
                return f"{g_val:.1f}g ({pct:.0f}%)"

            # 新しい表示用カラムを作成 (Apply関数で全行処理)
            nutri_df["P_disp"] = nutri_df.apply(
                lambda x: format_pfc(x, p_key, 4), axis=1
            )
            nutri_df["F_disp"] = nutri_df.apply(
                lambda x: format_pfc(x, f_key, 9), axis=1
            )
            nutri_df["C_disp"] = nutri_df.apply(
                lambda x: format_pfc(x, c_key, 4), axis=1
            )

            # 4. 表示用データフレームの構築
            # 元の数値データ(g)はバー表示用に残しつつ、テキスト表示用には結合した文字列を使う
            display_df = nutri_df[
                [
                    "ds",
                    "Calories",
                    p_key,
                    "P_disp",  # 数値(バー用) と 文字列(テキスト用)
                    f_key,
                    "F_disp",
                    c_key,
                    "C_disp",
                ]
            ]

            # 5. テーブル描画
            st.dataframe(
                display_df,
                use_container_width=True,
                column_config={
                    "ds": st.column_config.DateColumn(
                        "Date", format="YYYY-MM-DD", width="small"
                    ),
                    # --- Calories ---
                    "Calories": st.column_config.ProgressColumn(
                        f"Energy (Max: {LIMIT_CAL})",
                        format="%d",  # カロリーはそのまま数値表示でOK
                        min_value=0,
                        max_value=LIMIT_CAL,
                        width="medium",
                    ),
                    # --- Protein ---
                    # 【修正】format=" " (半角スペース) を指定して、バーの横の数値を消す
                    p_key: st.column_config.ProgressColumn(
                        f"Protein (Max: {LIMIT_P})",
                        format=" ",
                        max_value=LIMIT_P,
                        width="small",
                    ),
                    # 【修正】ヘッダーを空白文字 "" にして、左のバーと一体化しているように見せる
                    "P_disp": st.column_config.TextColumn("", width="small"),
                    # --- Fat ---
                    f_key: st.column_config.ProgressColumn(
                        f"Fat (Max: {LIMIT_F})",
                        format=" ",
                        max_value=LIMIT_F,
                        width="small",
                    ),
                    "F_disp": st.column_config.TextColumn("", width="small"),
                    # --- Carbs ---
                    c_key: st.column_config.ProgressColumn(
                        f"Carbs (Max: {LIMIT_C})",
                        format=" ",
                        max_value=LIMIT_C,
                        width="small",
                    ),
                    "C_disp": st.column_config.TextColumn("", width="small"),
                },
                hide_index=True,
            )
        else:
            st.info("PFC data columns not found.")

    # --- Tab 5: Metabolism ---
    with tab5:
        if "real_tdee_smooth" in df.columns:
            st.metric(
                "🔥 Real TDEE",
                f"{df['real_tdee_smooth'].iloc[-1]:.0f} kcal",
                f"Intake: {df['c_ma'].iloc[-1]:.0f}",
            )
            fig4 = go.Figure()
            fig4.add_trace(
                go.Scatter(
                    x=df["ds"],
                    y=df["real_tdee_smooth"],
                    mode="lines",
                    name="TDEE",
                    line=dict(color="#F59E0B", width=3),
                    fill="tozeroy",
                    hovertemplate="Date: %{x|%Y-%m-%d}<br>TDEE: %{y:.0f} kcal<extra></extra>",
                )
            )
            fig4.add_trace(
                go.Scatter(
                    x=df["ds"],
                    y=df["c_ma"],
                    mode="lines",
                    name="Intake",
                    line=dict(color="#10B981", width=2, dash="dot"),
                    hovertemplate="Date: %{x|%Y-%m-%d}<br>Intake: %{y:.0f} kcal<extra></extra>",
                )
            )
            fig4.update_layout(
                height=450, template="plotly_dark", yaxis=dict(range=[1000, 4000])
            )
            st.plotly_chart(fig4, use_container_width=True)

            # ========================================================
            # 【NEW】 📋 TDEE vs Intake Table
            # ========================================================
            st.markdown("### 📋 Daily TDEE & Intake Log")

            # 1. データ抽出 (日付, 摂取カロリー, 推定TDEE, カロリー収支)
            # TDEEが計算されている行だけに絞り込み、新しい日付順にソート
            tdee_table_df = df[["ds", "Calories", "real_tdee_smooth"]].copy()
            tdee_table_df = tdee_table_df.dropna(
                subset=["real_tdee_smooth"]
            ).sort_values("ds", ascending=False)

            # 2. 差分(Balance)の計算: Intake - TDEE
            # プラスならオーバーカロリー、マイナスならアンダーカロリー
            tdee_table_df["balance"] = (
                tdee_table_df["Calories"] - tdee_table_df["real_tdee_smooth"]
            )

            # 3. テーブル表示
            st.dataframe(
                tdee_table_df,
                use_container_width=True,
                column_config={
                    "ds": st.column_config.DateColumn(
                        "Date", format="YYYY-MM-DD", width="small"
                    ),
                    "Calories": st.column_config.NumberColumn(
                        "Intake", format="%d kcal", width="small"
                    ),
                    "real_tdee_smooth": st.column_config.NumberColumn(
                        "Real TDEE",
                        format="%d kcal",
                        width="small",
                        help="体重変化から逆算された実質の消費カロリー",
                    ),
                    # 収支(Balance)をバーで可視化
                    # 赤(正): 食べ過ぎ / 青(負): 絞れている
                    "balance": st.column_config.ProgressColumn(
                        "Balance",
                        format="%+d kcal",  # +200, -300 のように符号を表示
                        min_value=-1000,
                        max_value=1000,
                        width="medium",
                        help="Intake - TDEE (マイナスが脂肪燃焼中)",
                    ),
                },
                hide_index=True,
            )

    # --- Tab 6: Database (Food & Menu) ---
    with tab6:
        st.markdown("### 🍱 Food & Menu Manager")
        col_single, col_set = st.columns(2)

        # --- A. 単体食材登録 (リアルタイム計算 & 手動補正) ---
        with col_single:
            with st.container(border=True):
                st.subheader("🍎 Add Single Item")
                st.caption("PFCを入力するとカロリーが自動計算されます")

                def calc_cal_from_pfc():
                    p = st.session_state.new_p
                    f = st.session_state.new_f
                    c = st.session_state.new_c
                    # 計算結果をsession_stateに入れる
                    st.session_state.new_cal = int((p * 4) + (f * 9) + (c * 4))

                name = st.text_input(
                    "Food Name", placeholder="e.g. 白米 100g", key="new_name"
                )
                c1, c2, c3 = st.columns(3)
                c1.number_input(
                    "P (g)",
                    0.0,
                    100.0,
                    0.0,
                    step=0.1,
                    format="%.1f",
                    key="new_p",
                    on_change=calc_cal_from_pfc,
                )
                c2.number_input(
                    "F (g)",
                    0.0,
                    100.0,
                    0.0,
                    step=0.1,
                    format="%.1f",
                    key="new_f",
                    on_change=calc_cal_from_pfc,
                )
                c3.number_input(
                    "C (g)",
                    0.0,
                    500.0,
                    0.0,
                    step=0.1,
                    format="%.1f",
                    key="new_c",
                    on_change=calc_cal_from_pfc,
                )

                st.markdown("---")
                # 手動で上書き可能なカロリー欄 (文科省データなどと合わせる用)
                st.number_input(
                    "Energy (kcal)",
                    0,
                    2000,
                    0,
                    step=1,
                    key="new_cal",
                    help="自動計算されますが、手入力で上書きも可能です",
                )

                if st.button("Add to DB", type="primary"):
                    if st.session_state.new_name:
                        notion_db.add_food_item(
                            FOOD_DATABASE_ID,
                            NOTION_TOKEN,
                            st.session_state.new_name,
                            st.session_state.new_p,
                            st.session_state.new_f,
                            st.session_state.new_c,
                            st.session_state.new_cal,
                        )
                        st.success(f"Added: {st.session_state.new_name}")
                    else:
                        st.error("Name is required")

        # --- B. セットメニュー編集 (Load / Edit / Save) ---
        with col_set:
            with st.container(border=True):
                st.subheader("🍽 Menu Editor")
                st.caption("既存セットをロードして編集、または新規作成")

                try:
                    current_foods = notion_db.fetch_food_list(
                        FOOD_DATABASE_ID, NOTION_TOKEN
                    )
                    food_names = list(current_foods.keys())
                    existing_menus = notion_db.fetch_menu_list(
                        MENU_DATABASE_ID, NOTION_TOKEN
                    )
                except:
                    food_names = []
                    existing_menus = {}
                    current_foods = {}

                # 1. Load Existing Set
                c_load_sel, c_load_btn = st.columns([3, 1])
                load_target = c_load_sel.selectbox(
                    "Load Existing Set",
                    ["(Select to Load)"] + sorted(list(existing_menus.keys())),
                )

                if "edit_set_name" not in st.session_state:
                    st.session_state.edit_set_name = ""

                if c_load_btn.button("📥 Load"):
                    if load_target != "(Select to Load)":
                        st.session_state.temp_set_items = existing_menus[load_target]
                        st.session_state.edit_set_name = load_target
                        st.success(f"Loaded: {load_target}")
                        st.rerun()

                st.divider()

                # 2. Edit Items
                if "temp_set_items" not in st.session_state:
                    st.session_state.temp_set_items = []

                # アイテム追加
                c_sel, c_amt, c_btn = st.columns([3, 2, 1])
                sel_food = c_sel.selectbox("Add Food", food_names, key="set_maker_food")
                sel_amt = c_amt.number_input("g", 0, 2000, 100, 10, key="set_maker_amt")

                if c_btn.button("Add"):
                    st.session_state.temp_set_items.append(
                        {"name": sel_food, "amount": sel_amt}
                    )
                    st.rerun()

                # リスト表示
                if st.session_state.temp_set_items:
                    st.markdown("---")
                    st.caption("🧾 Recipe Content:")
                    preview_cal = 0
                    for idx, item in enumerate(st.session_state.temp_set_items):
                        cols = st.columns([4, 1])
                        fname = item["name"]
                        famt = item["amount"]
                        if fname in current_foods:
                            base = current_foods[fname]
                            cal = int(base["cal"] * (famt / 100))
                            preview_cal += cal
                        else:
                            cal = 0
                        cols[0].text(f"・{fname} ({famt}g) : {cal}kcal")
                        if cols[1].button("🗑️", key=f"del_set_item_{idx}"):
                            st.session_state.temp_set_items.pop(idx)
                            st.rerun()
                    st.markdown(f"**Total: approx. {preview_cal} kcal**")

                    # 3. Save / Update
                    with st.form("save_set_recipe"):
                        set_name = st.text_input(
                            "Set Name", value=st.session_state.edit_set_name
                        )
                        if st.form_submit_button("💾 Save / Update"):
                            if set_name and st.session_state.temp_set_items:
                                notion_db.save_menu_item(
                                    MENU_DATABASE_ID,
                                    NOTION_TOKEN,
                                    set_name,
                                    st.session_state.temp_set_items,
                                )
                                st.success(f"Saved: {set_name}")
                                st.session_state.temp_set_items = []
                                st.session_state.edit_set_name = ""
                                st.rerun()
                            else:
                                st.error("Name and items required")

    # --- Tab 7: Settings (New!) ---
    with tab7:
        st.subheader("⚙️ System Settings")
        st.caption("目標やフェーズの設定変更はこちらで行います。")

        with st.container(border=True):
            # フォーム化して、ボタンを押した時だけDB更新する
            with st.form("settings_form"):
                col1, col2 = st.columns(2)

                # 初期値には 冒頭でロードした cfg_ 変数を使う
                new_goal_date = col1.date_input("Goal Date", value=cfg_goal_date)
                new_phase = col2.radio(
                    "Phase",
                    ["Cut", "Bulk"],
                    index=0 if cfg_is_cut else 1,
                    horizontal=True,
                )

                st.divider()

                c3, c4 = st.columns(2)
                new_goal_weight = c3.number_input(
                    "Goal Weight (kg)",
                    0.0,
                    100.0,
                    value=cfg_goal_weight,
                    step=0.1,
                    format="%.1f",
                )
                new_monthly_target = c4.number_input(
                    "Monthly Target (kg)",
                    0.0,
                    100.0,
                    value=cfg_monthly_target,
                    step=0.1,
                    format="%.1f",
                )

                submitted = st.form_submit_button("💾 Update Settings", type="primary")

                if submitted:
                    # Settings DB を更新
                    # キー名は notion_db.py 内の実装に合わせる (target_date, current_phase など)
                    notion_db.update_setting(
                        SETTINGS_DATABASE_ID,
                        NOTION_TOKEN,
                        "target_date",
                        str(new_goal_date),
                    )
                    notion_db.update_setting(
                        SETTINGS_DATABASE_ID, NOTION_TOKEN, "current_phase", new_phase
                    )
                    notion_db.update_setting(
                        SETTINGS_DATABASE_ID,
                        NOTION_TOKEN,
                        "target_weight",
                        new_goal_weight,
                    )
                    notion_db.update_setting(
                        SETTINGS_DATABASE_ID,
                        NOTION_TOKEN,
                        "monthly_target",
                        new_monthly_target,
                    )

                    st.success("Settings Updated! Reloading...")
                    st.rerun()  # リロードしてTab1などに反映させる

        st.info(
            "※ ここで設定した「Goal Date」や「Target」は、シミュレーター(Tab 1)の予測線に反映されます。"
        )


if __name__ == "__main__":
    main()
