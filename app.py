import datetime
from datetime import date, timedelta

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

# 自作モジュールのインポート: notion_db を supabase_db に変更
import logic
import supabase_db

# ==========================================
# 1. 初期設定
# ==========================================
st.set_page_config(page_title="Body Composition Tracker", page_icon="⚡", layout="wide")
FAT_CALORIES_PER_KG = 7200  # 脂肪1kgあたりのカロリー

# ※ SecretsのID読み込みは不要になりました (supabase_db内で完結)

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
    # Notion版から Supabase版へ変更 (引数不要)
    try:
        settings_data = supabase_db.fetch_settings()
    except Exception:
        settings_data = {}

    # --- デフォルト値と設定値の展開 ---
    # A. Goal Date
    cfg_goal_date_str = settings_data.get("target_date", "2026-05-30")
    try:
        cfg_goal_date = datetime.datetime.strptime(
            str(cfg_goal_date_str), "%Y-%m-%d"
        ).date()
    except Exception:
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
        st.header("📝 Daily Log")
        st.caption("食品を選んでカートに追加 → 保存")

        # --- データ取得 (食品マスタ & セットメニュー) ---
        try:
            food_dict = supabase_db.fetch_food_list()
            set_dict = supabase_db.fetch_menu_list()

            food_list = sorted(list(food_dict.keys()))
            set_list = [f"[SET] {k}" for k in set_dict.keys()]
            menu_options = set_list + food_list
        except Exception:
            menu_options = []
            food_dict = {}
            set_dict = {}

        # --- カートシステム (Session State管理) ---
        if "meal_cart" not in st.session_state:
            st.session_state.meal_cart = []

        def remove_from_cart(idx):
            st.session_state.meal_cart.pop(idx)

        def clear_cart():
            st.session_state.meal_cart = []

        def add_to_cart():
            selected = st.session_state.picker_menu
            input_amount = st.session_state.picker_amount

            # Pattern A: セットメニュー
            if selected.startswith("[SET] "):
                real_name = selected.replace("[SET] ", "")
                if real_name in set_dict:
                    recipe = set_dict[real_name]
                    for item in recipe:
                        fname = item["name"]
                        famt = item["amount"]
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

            # Pattern B: 単品食品
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
                help="単品選択時のみ有効",
            )
            if st.button("➕ Add to List"):
                add_to_cart()

        # --- UI: カート内容表示 ---
        total_k, total_p, total_f, total_c = 0, 0, 0, 0
        if st.session_state.meal_cart:
            st.caption("② Current List")
            st.markdown("---")

            for i, item in enumerate(st.session_state.meal_cart):
                total_k += item["kcal"]
                total_p += item["p"]
                total_f += item["f"]
                total_c += item["c"]

                c_text, c_btn = st.columns([4, 1])
                with c_text:
                    st.text(f"{item['name']} ({item['amount']}g)\n{item['kcal']}kcal")
                with c_btn:
                    st.button("🗑️", key=f"del_{i}", on_click=remove_from_cart, args=(i,))

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
                # Supabaseに保存 (IDやToken引数は不要)
                supabase_db.add_daily_log(
                    d_in,
                    w_in,
                    note,
                    kcal=fk,
                    p=round(fp, 1),
                    f=round(ff, 1),
                    c=round(fc, 1),
                )
                st.success("Saved successfully to Supabase!")
                st.session_state.meal_cart = []
                st.rerun()

    # ==========================================
    # 5. メインダッシュボード (KPI)
    # ==========================================
    st.title("⚡ Body Composition Tracker")

    # データ取得
    raw_df = supabase_db.fetch_raw_data()
    if raw_df.empty:
        st.warning("No data found in Database.")
        st.stop()

    # 分析ロジック (変更なし)
    df = logic.enrich_data(raw_df, cfg_goal_date)
    # CSVはローカルファイルなのでそのまま
    hist_df = supabase_db.fetch_history_csv()

    with st.spinner("Analyzing with NeuralProphet (AI)..."):
        p_val, p_fore = logic.run_neural_model(df, cfg_goal_date)
        l_val = logic.run_linear_model(df, cfg_goal_date)

    # KPI 計算
    curr = df["y"].iloc[-1]
    days = (cfg_goal_date - date.today()).days
    days = 1 if days < 1 else days
    gap = p_val - cfg_goal_weight

    # KPI 表示
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Weight", f"{curr:.1f} kg", f"{(curr - cfg_goal_weight):+.1f}")
    c2.metric("Days Left", f"{days}")

    is_bad_forecast = False
    if cfg_is_cut:
        is_bad_forecast = gap > 0.1
    else:
        is_bad_forecast = (gap < -0.2) or (gap > 0.5)

    c3.metric(
        "Forecast",
        f"{p_val:.1f} kg",
        f"{gap:+.1f}",
        delta_color="inverse" if is_bad_forecast else "normal",
    )
    c4.metric("Trend (Lin)", f"{l_val:.1f} kg")

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
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs(
        [
            "📉 Simulator",
            "📜 History",
            "🏆 Comp History",
            "📊 Stats",
            "🔥 Metabolism",
            "🍱 Database",
            "⚙️ Settings",
        ]
    )

    # --- Tab 1: AI Forecast & Simulation ---
    with tab1:
        st.markdown("### 📉 AI Forecast & Metabolic Simulation")

        # 1. データの準備
        # 現在の体重（SMA7があればそれを、なければ生データ）
        current_weight = (
            df["SMA_7"].iloc[-1] if pd.notna(df["SMA_7"].iloc[-1]) else df["y"].iloc[-1]
        )

        # 現在のTDEE（計算値）
        base_tdee = (
            int(df["real_tdee_smooth"].iloc[-1])
            if pd.notna(df.get("real_tdee_smooth", pd.Series([np.nan])).iloc[-1])
            else 2400
        )

        # 現在の摂取カロリー（直近平均 or デフォルト2000）
        current_intake = (
            int(df["c_ma"].iloc[-1])
            if "c_ma" in df.columns
            and pd.notna(df["c_ma"].iloc[-1])
            and df["c_ma"].iloc[-1] > 0
            else 2000
        )

        # 3. シミュレーションの実行 (代謝適応モデル)
        sim_df = logic.run_metabolic_simulation(
            df, cfg_goal_date, current_weight, base_tdee, current_intake
        )

        # --- KPI表示エリア ---
        # 到達予測日の算出 (AI予測に基づく外挿計算あり)
        est_date_str = "Unknown"
        sub_label = "(Not reached)"

        # 1. まず、グラフの表示範囲内（目標日まで）に達成するかチェック
        future_hit = p_fore[
            (p_fore["ds"] > pd.to_datetime(date.today()))
            & (p_fore["yhat"] <= cfg_goal_weight)
        ]

        if not future_hit.empty:
            # 範囲内で達成する場合
            hit_date = future_hit["ds"].iloc[0]
            est_date_str = hit_date.strftime("%m/%d")
            sub_label = "(AI Forecast)"
        else:
            # 2. 範囲内で達成しない場合 → 「今のペースならいつ？」を外挿計算 (Extrapolation)
            current_pred = p_fore["yhat"].iloc[-1]
            last_date = p_fore["ds"].iloc[-1]

            # 直近14日間の傾き（kg/day）を取得してペース判定
            slope = p_fore["yhat"].diff().tail(14).mean()

            # 減量ペースが維持されている場合（傾きがマイナス）
            if slope < -0.005:
                rem_weight = current_pred - cfg_goal_weight
                days_needed = int(rem_weight / abs(slope))

                # 理論上の達成日を算出
                theoretical_date = last_date + timedelta(days=days_needed)

                # 年またぎを考慮して年付きフォーマット
                est_date_str = theoretical_date.strftime("%Y/%m/%d")
                sub_label = "(Extrapolated)"
            else:
                # ペースが停滞、または増えている場合
                est_date_str = "∞"
                sub_label = "(Stagnant/Increasing)"

        col_tdee, col_est = st.columns([1, 1])

        with col_tdee:
            st.metric(
                "Current TDEE",
                f"{base_tdee} kcal",
                f"Intake: {current_intake} kcal",
                help="直近の体重減少ペースから逆算された実質代謝量",
            )

        with col_est:
            st.markdown(
                f"""
                <div style="
                    background-color: rgba(255, 255, 255, 0.05);
                    padding: 10px 20px;
                    border-radius: 10px;
                    border-left: 5px solid #F59E0B;
                    text-align: center;">
                    <p style="margin: 0; font-size: 0.8rem; color: #888;">AI Goal Date</p>
                    <p style="margin: 0; font-size: 1.8rem; font-weight: bold; color: #FFF;">
                        {est_date_str} <span style="font-size: 1rem; font-weight: normal; color: #AAA;">{sub_label}</span>
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # --- グラフ描画 ---
        fig = go.Figure()

        # A. NeuralProphet Forecast (AI) - Orange Line
        fig.add_trace(
            go.Scatter(
                x=p_fore["ds"],
                y=p_fore["yhat"],
                mode="lines",
                name="AI Trend (Ideal)",
                line=dict(color="rgba(255, 136, 0, 0.9)", width=3),
                hovertemplate="<b>AI Forecast</b><br>%{x|%m/%d}: %{y:.1f}kg<extra></extra>",
            )
        )

        # B. Metabolic Simulation (Math) - White Dashed Line
        if not sim_df.empty:
            fig.add_trace(
                go.Scatter(
                    x=sim_df["ds"],
                    y=sim_df["yhat_sim"],
                    mode="lines",
                    name="Sim (Metabolic Drop)",
                    line=dict(color="rgba(200, 200, 200, 0.6)", width=2, dash="dash"),
                    hovertemplate="<b>Simulation</b><br>(Stagnation Risk)<br>%{y:.1f}kg<extra></extra>",
                )
            )

        # C. SMA7 (Trend) - Cyan Line
        if pd.notna(df["SMA_7"].iloc[-1]):
            fig.add_trace(
                go.Scatter(
                    x=df["ds"],
                    y=df["SMA_7"],
                    mode="lines",
                    name="7-Day Avg",
                    line=dict(color="#00BFFF", width=2, dash="solid"),
                    hovertemplate="Avg: %{y:.1f}kg<extra></extra>",
                )
            )

        # D. Actual Data - Blue Dots
        fig.add_trace(
            go.Scatter(
                x=df["ds"],
                y=df["y"],
                mode="markers",
                name="Actual",
                marker=dict(color="rgba(0, 191, 255, 0.4)", size=6),
                hovertemplate="Raw: %{y:.1f}kg<extra></extra>",
            )
        )

        # 補助線 (Goal)
        fig.add_hline(
            y=cfg_goal_weight, line_dash="dot", line_color="red", annotation_text="Goal"
        )

        # 補助線 (Monthly Target) - 復活
        if cfg_monthly_target > 0:
            fig.add_hline(
                y=cfg_monthly_target,
                line_dash="dashdot",
                line_color="orange",
                annotation_text="Monthly Target",
            )

        target_date_ts = pd.to_datetime(cfg_goal_date)
        graph_end_date = target_date_ts + pd.DateOffset(days=15)
        start_view_date = df["ds"].max() - pd.DateOffset(days=45)  # 直近45日を表示

        # 月ごとの縦線
        month_starts = pd.date_range(
            start=df["ds"].min(), end=graph_end_date, freq="MS"
        )
        for d in month_starts:
            fig.add_vline(
                x=d,
                line_width=1,
                line_dash="dot",
                line_color="rgba(255, 255, 255, 0.1)",
            )

        # Y軸の範囲計算
        y_max = df["y"].max() + 1.0
        y_min = cfg_goal_weight - 2.0

        fig.update_layout(
            height=500,
            template="plotly_dark",
            legend=dict(orientation="h", y=1.05),
            margin=dict(l=20, r=20, t=20, b=20),
            xaxis=dict(
                range=[start_view_date, graph_end_date],
                type="date",
                rangeslider=dict(visible=True),
                gridcolor="rgba(128,128,128, 0.2)",
            ),
            yaxis=dict(
                range=[y_min, y_max],
                tickformat=".1f",
                dtick=2.0,  # ◀◀◀ 2kg刻みに設定
                showgrid=True,
                gridcolor="rgba(128,128,128, 0.2)",
                title="Weight (kg)",
            ),
        )
        st.plotly_chart(fig, use_container_width=True)

        # --- 履歴テーブル (Recent Logs) ---
        st.markdown("#### 📋 Recent Logs")
        table_cols = ["ds", "y"]
        if "Calories" in df.columns:
            table_cols.append("Calories")

        log_df = df[table_cols].copy()
        log_df["Diff"] = log_df["y"].diff().round(2)
        log_df = log_df.sort_values("ds", ascending=False).head(14)

        def style_diff(val):
            if pd.isna(val) or val == 0:
                return ""
            color = "#FF4B4B" if val > 0 else "#1C83E1"
            return f"color: {color}; font-weight: bold;"

        styled_df = log_df.style.map(style_diff, subset=["Diff"]).format(
            {
                "y": "{:.1f} kg",
                "Diff": "{:+.1f} kg",
                "Calories": "{:,.0f} kcal" if "Calories" in log_df.columns else "{}",
            }
        )
        st.dataframe(
            styled_df,
            use_container_width=True,
            column_config={
                "ds": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
                "y": "Weight",
                "Diff": "Δ",
                "Calories": "Intake",
            },
            hide_index=True,
        )

    # --- Tab 2: History (CSVベースなのでロジック変更ほぼなし) ---
    with tab2:
        if hist_df is not None:
            dr = st.slider("Display Range (Days)", 60, 300, 120, 10)
            fig2 = go.Figure()
            # ... (スタイル設定省略、同じ) ...
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

            for label in hist_df["Label"].unique():
                s = hist_df[
                    (hist_df["Label"] == label) & (hist_df["days_out"] > -dr)
                ].sort_values("Date")
                if not s.empty:
                    style = STYLE_CONFIG.get(label, DEFAULT_STYLE)
                    fig2.add_trace(
                        go.Scatter(
                            x=s["days_out"],
                            y=s["Weight"].rolling(7, 1).mean().round(1),
                            mode="lines",
                            name=label,
                            line=style,
                            hovertemplate="<b>%{fullData.name}</b><br>Days Out: %{x}<br>Weight: %{y:.1f}kg<extra></extra>",
                        )
                    )

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

            st.markdown("### 📅 Recent 14 Days Comparison")
            df_sorted = df.sort_values("ds")
            if not df_sorted.empty:
                target_date_obj = cfg_goal_date
                current_date_val = df_sorted["ds"].iloc[-1].date()
                date_objects = [current_date_val - timedelta(days=i) for i in range(14)]
                comp_df = pd.DataFrame({"DateObj": date_objects})
                comp_df["2026 Date"] = comp_df["DateObj"].apply(
                    lambda d: d.strftime("%Y-%m-%d")
                )
                comp_df["Days Remaining"] = comp_df["DateObj"].apply(
                    lambda d: (target_date_obj - d).days
                )

                df_sorted["date_obj"] = df_sorted["ds"].dt.date
                comp_df = comp_df.merge(
                    df_sorted[["date_obj", "y"]].rename(
                        columns={"y": "2026 Actual", "date_obj": "DateObj"}
                    ),
                    on="DateObj",
                    how="left",
                )

                past_labels = []
                if hist_df is not None and not hist_df.empty:
                    hist_df["Date"] = pd.to_datetime(hist_df["Date"])
                    hist_df["date_str"] = hist_df["Date"].dt.strftime("%Y-%m-%d")
                    hist_df["join_key"] = hist_df["days_out"].astype(int)

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
                    past_labels.sort(reverse=True)

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

                def format_diff_row(row, label_name):
                    past_val = row[label_name]
                    current_val = row["2026 Actual"]
                    if pd.isna(past_val):
                        return "-"
                    elif pd.isna(current_val):
                        return f"{past_val:.1f}"
                    else:
                        diff = current_val - past_val
                        return f"{past_val:.1f} ({diff:+.1f})"

                display_cols = ["Days Remaining", "2026 Date", "2026 Actual"]
                col_config = {
                    "Days Remaining": st.column_config.NumberColumn(
                        "Days Out", format="%d", width="small"
                    ),
                    "2026 Date": st.column_config.TextColumn("Date", width="small"),
                    "2026 Actual": st.column_config.NumberColumn(
                        "🔥 Actual", format="%.1f kg", width="small"
                    ),
                }

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
                        f"{year_prefix} Date", width="small"
                    )
                    col_config[disp_weight_col] = st.column_config.TextColumn(
                        f"{year_prefix} Weight", width="small"
                    )

                st.dataframe(
                    comp_df[display_cols],
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
            curr_formatted = df[["ds", "y"]].rename(
                columns={"ds": "Date", "y": "Weight"}
            )
            curr_formatted["Label"] = "Current Season"
            full_history = pd.concat(
                [hist_df[["Date", "Weight", "Label"]], curr_formatted],
                ignore_index=True,
            )
            full_history = full_history.sort_values("Date")

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

            st.subheader("📉 Season Low (Best Condition)")
            season_stats = full_history.groupby("Label")["Weight"].min().reset_index()
            season_stats.columns = ["Season", "MinWeight"]

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

            fig_bar = go.Figure()
            fig_bar.add_trace(
                go.Bar(
                    x=season_stats["Season"],
                    y=season_stats["MinWeight"],
                    text=season_stats.apply(
                        lambda x: (
                            f"{x['MinWeight']:.1f}kg"
                            + (f" ({x['Delta']:+.1f})" if pd.notna(x["Delta"]) else "")
                        ),
                        axis=1,
                    ),
                    textposition="auto",
                    marker_color="#3B82F6",
                    hovertemplate="<b>%{x}</b><br>Min: %{y:.1f}kg<extra></extra>",
                )
            )
            y_min = season_stats["MinWeight"].min() - 3
            y_max = season_stats["MinWeight"].max() + 2
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
        w_df = df.set_index("ds").resample("W").mean(numeric_only=True).reset_index()
        if len(w_df) >= 2:
            this_week, last_week = w_df.iloc[-1], w_df.iloc[-2]
            weight_diff = this_week["y"] - last_week["y"]
            rol_pct = (weight_diff / last_week["y"]) * 100
            if -1.5 <= rol_pct <= -0.5:
                rol_color, rol_msg = "normal", "Ideal Pace 🎯"
            elif rol_pct < -1.5:
                rol_color, rol_msg = "inverse", "Too Fast! ⚠️"
            else:
                rol_color, rol_msg = "off", "Slow / Bulk 🐢"

            p_val_avg = this_week.get("Protein", 0)
            cal_val_avg = (
                this_week.get("Calories", 1) if this_week.get("Calories", 0) > 0 else 1
            )
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
        if "Protein" in df.columns:
            st.subheader("🥩 Macro Composition")
            df["P_cal"] = df["Protein"] * 4
            df["F_cal"] = df["Fat"] * 9
            df["C_cal"] = df["Carbs"] * 4
            df["Total_cal_calc"] = (df["P_cal"] + df["F_cal"] + df["C_cal"]).replace(
                0, 1
            )
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

        st.subheader("🥦 Daily Nutrition Breakdown")
        LIMIT_CAL, LIMIT_P, LIMIT_F, LIMIT_C = 2500, 200, 50, 320
        target_cols = ["ds", "Calories"]
        p_key = next((k for k in ["P", "Protein", "p"] if k in df.columns), None)
        f_key = next((k for k in ["F", "Fat", "f"] if k in df.columns), None)
        c_key = next((k for k in ["C", "Carbs", "c"] if k in df.columns), None)

        if p_key and f_key and c_key:
            target_cols.extend([p_key, f_key, c_key])
            nutri_df = (
                df[target_cols]
                .copy()
                .sort_values("ds", ascending=False)
                .head(14)
                .fillna(0)
            )

            def format_pfc(row, key, cal_factor):
                g_val = row[key]
                pct = (
                    (g_val * cal_factor / row["Calories"] * 100)
                    if row["Calories"] > 0
                    else 0
                )
                return f"{g_val:.1f}g ({pct:.0f}%)"

            nutri_df["P_disp"] = nutri_df.apply(
                lambda x: format_pfc(x, p_key, 4), axis=1
            )
            nutri_df["F_disp"] = nutri_df.apply(
                lambda x: format_pfc(x, f_key, 9), axis=1
            )
            nutri_df["C_disp"] = nutri_df.apply(
                lambda x: format_pfc(x, c_key, 4), axis=1
            )

            st.dataframe(
                nutri_df[
                    [
                        "ds",
                        "Calories",
                        p_key,
                        "P_disp",
                        f_key,
                        "F_disp",
                        c_key,
                        "C_disp",
                    ]
                ],
                use_container_width=True,
                column_config={
                    "ds": st.column_config.DateColumn(
                        "Date", format="YYYY-MM-DD", width="small"
                    ),
                    "Calories": st.column_config.ProgressColumn(
                        f"Energy (Max: {LIMIT_CAL})",
                        format="%d",
                        min_value=0,
                        max_value=LIMIT_CAL,
                        width="medium",
                    ),
                    p_key: st.column_config.ProgressColumn(
                        f"Protein (Max: {LIMIT_P})",
                        format=" ",
                        max_value=LIMIT_P,
                        width="small",
                    ),
                    "P_disp": st.column_config.TextColumn("", width="small"),
                    f_key: st.column_config.ProgressColumn(
                        f"Fat (Max: {LIMIT_F})",
                        format=" ",
                        max_value=LIMIT_F,
                        width="small",
                    ),
                    "F_disp": st.column_config.TextColumn("", width="small"),
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

        # ▼▼▼ 追加部分: XGBoost Factor Analysis ▼▼▼
        st.markdown("---")
        st.subheader("🤖 AI Factor Analysis (XGBoost)")
        st.caption("「何が体重減少に最も寄与しているか」をAIが判定します")

        imp_df = logic.run_xgboost_importance(df)

        if imp_df is not None:
            # 棒グラフで重要度を表示
            fig_imp = go.Figure(
                go.Bar(
                    x=imp_df["Importance"],
                    y=imp_df["Feature"],
                    orientation="h",
                    marker=dict(color="rgba(50, 171, 96, 0.7)"),
                )
            )

            fig_imp.update_layout(
                title="Impact on Weight Fluctuation",
                xaxis_title="Importance Score",
                yaxis=dict(autorange="reversed"),  # 上位を上に
                height=300,
                template="plotly_dark",
                margin=dict(l=0, r=0, t=30, b=0),
            )
            st.plotly_chart(fig_imp, use_container_width=True)

            # 解釈コメント
            top_factor = imp_df.iloc[0]["Feature"]
            st.info(
                f"💡 AIの分析によると、現在の体重変動に最も影響を与えているのは **「{top_factor}」** です。"
            )
        else:
            st.warning(
                "データ不足のため、詳細分析にはまだ時間がかかります（最低14日分のデータが必要です）。"
            )

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
                )
            )
            fig4.add_trace(
                go.Scatter(
                    x=df["ds"],
                    y=df["c_ma"],
                    mode="lines",
                    name="Intake",
                    line=dict(color="#10B981", width=2, dash="dot"),
                )
            )
            fig4.update_layout(
                height=450, template="plotly_dark", yaxis=dict(range=[1000, 4000])
            )
            st.plotly_chart(fig4, use_container_width=True)

            st.markdown("### 📋 Daily TDEE & Intake Log")
            tdee_table_df = (
                df[["ds", "Calories", "real_tdee_smooth"]]
                .copy()
                .dropna(subset=["real_tdee_smooth"])
                .sort_values("ds", ascending=False)
            )
            tdee_table_df["balance"] = (
                tdee_table_df["Calories"] - tdee_table_df["real_tdee_smooth"]
            )
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
                        "Real TDEE", format="%d kcal", width="small"
                    ),
                    "balance": st.column_config.ProgressColumn(
                        "Balance",
                        format="%+d kcal",
                        min_value=-1000,
                        max_value=1000,
                        width="medium",
                    ),
                },
                hide_index=True,
            )

    # --- Tab 6: Database (Food & Menu) ---
    with tab6:
        st.markdown("### 🍱 Food & Menu Manager")
        col_single, col_set = st.columns(2)

        # A. Single Item
        with col_single:
            with st.container(border=True):
                st.subheader("🍎 Add Single Item")
                st.caption("PFCを入力するとカロリーが自動計算されます")

                def calc_cal_from_pfc():
                    st.session_state.new_cal = int(
                        (st.session_state.new_p * 4)
                        + (st.session_state.new_f * 9)
                        + (st.session_state.new_c * 4)
                    )

                st.text_input("Food Name", placeholder="e.g. 白米 100g", key="new_name")
                c1, c2, c3 = st.columns(3)
                c1.number_input(
                    "P (g)",
                    0.0,
                    100.0,
                    0.0,
                    step=0.1,
                    key="new_p",
                    on_change=calc_cal_from_pfc,
                )
                c2.number_input(
                    "F (g)",
                    0.0,
                    100.0,
                    0.0,
                    step=0.1,
                    key="new_f",
                    on_change=calc_cal_from_pfc,
                )
                c3.number_input(
                    "C (g)",
                    0.0,
                    500.0,
                    0.0,
                    step=0.1,
                    key="new_c",
                    on_change=calc_cal_from_pfc,
                )
                st.markdown("---")
                st.number_input("Energy (kcal)", 0, 2000, 0, step=1, key="new_cal")

                if st.button("Add to DB", type="primary"):
                    if st.session_state.new_name:
                        supabase_db.add_food_item(
                            st.session_state.new_name,
                            st.session_state.new_p,
                            st.session_state.new_f,
                            st.session_state.new_c,
                            st.session_state.new_cal,
                        )
                        st.success(f"Added: {st.session_state.new_name}")
                    else:
                        st.error("Name is required")

        # B. Set Menu
        # --- B. セットメニュー編集 (Load / Edit / Save) ---
        with col_set:
            with st.container(border=True):
                st.subheader("🍽 Menu Editor")

                # データ準備
                try:
                    current_foods = supabase_db.fetch_food_list()
                    food_names = list(current_foods.keys())
                    existing_menus = supabase_db.fetch_menu_list()
                except Exception:
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

                # 2. Add Item
                if "temp_set_items" not in st.session_state:
                    st.session_state.temp_set_items = []

                c_sel, c_amt, c_btn = st.columns([3, 2, 1])
                sel_food = c_sel.selectbox("Add Food", food_names, key="set_maker_food")
                sel_amt = c_amt.number_input("g", 0, 2000, 100, 10, key="set_maker_amt")

                if c_btn.button("Add"):
                    st.session_state.temp_set_items.append(
                        {"name": sel_food, "amount": sel_amt}
                    )
                    st.rerun()

                # 3. List & Sort & Display
                if st.session_state.temp_set_items:
                    st.markdown("---")

                    # --- 並び替え機能 (Sorting) ---
                    c_head, c_sort = st.columns([2, 2])
                    c_head.caption("🧾 Recipe Content:")

                    sort_mode = c_sort.selectbox(
                        "Sort by",
                        ["Registered (Default)", "Calories", "Protein", "Fat", "Carbs"],
                        label_visibility="collapsed",
                        key="sort_mode_selector",
                    )

                    # 並び替えロジック (降順)
                    if sort_mode != "Registered (Default)":
                        # マッピング: 選択肢 -> current_foodsのキー
                        key_map = {
                            "Calories": "cal",
                            "Protein": "p",
                            "Fat": "f",
                            "Carbs": "c",
                        }
                        target_key = key_map[sort_mode]

                        def get_sort_value(item):
                            fname = item["name"]
                            if fname in current_foods:
                                return current_foods[fname][target_key] * (
                                    item["amount"] / 100
                                )
                            return 0

                        # セッションステート内のリストを直接並び替え
                        st.session_state.temp_set_items.sort(
                            key=get_sort_value, reverse=True
                        )

                    # --- リスト表示 (PFC付き) ---
                    total_cal = 0
                    total_p, total_f, total_c = 0, 0, 0

                    for idx, item in enumerate(st.session_state.temp_set_items):
                        cols = st.columns([5, 1])
                        fname, famt = item["name"], item["amount"]

                        # 数値計算
                        if fname in current_foods:
                            base = current_foods[fname]
                            ratio = famt / 100.0

                            val_cal = int(base["cal"] * ratio)
                            val_p = base["p"] * ratio
                            val_f = base["f"] * ratio
                            val_c = base["c"] * ratio

                            # 合計加算
                            total_cal += val_cal
                            total_p += val_p
                            total_f += val_f
                            total_c += val_c

                            # 表示テキスト作成: "名前 (100g) : 200kcal (P:20.0 F:5.0 C:30.0)"
                            disp_text = (
                                f"・{fname} ({famt}g) : **{val_cal}kcal** "
                                f"<span style='color:#AAA; font-size:0.8em;'>"
                                f"(P:{val_p:.1f} F:{val_f:.1f} C:{val_c:.1f})</span>"
                            )
                        else:
                            val_cal = 0
                            disp_text = f"・{fname} ({famt}g) : Unknown"

                        # HTML許可でレンダリング (文字色調整のため)
                        cols[0].markdown(disp_text, unsafe_allow_html=True)

                        if cols[1].button("🗑️", key=f"del_set_item_{idx}"):
                            st.session_state.temp_set_items.pop(idx)
                            st.rerun()

                    # 合計表示
                    st.divider()
                    st.markdown(
                        f"**Total:** {total_cal} kcal "
                        f"(P:{total_p:.1f} F:{total_f:.1f} C:{total_c:.1f})"
                    )

                    # 4. Save Form
                    with st.form("save_set_recipe"):
                        set_name = st.text_input(
                            "Set Name", value=st.session_state.edit_set_name
                        )
                        if st.form_submit_button("💾 Save / Update", type="primary"):
                            if set_name and st.session_state.temp_set_items:
                                supabase_db.save_menu_item(
                                    set_name, st.session_state.temp_set_items
                                )
                                st.success(f"Saved: {set_name}")
                                # 保存後はクリア
                                st.session_state.temp_set_items = []
                                st.session_state.edit_set_name = ""
                                st.rerun()
                            else:
                                st.error("Name and items required")

    # --- Tab 7: Settings & Data Export ---
    with tab7:
        # 1. 既存の設定フォーム
        st.subheader("⚙️ System Settings")
        st.caption("目標やフェーズの設定変更はこちらで行います。")
        with st.container(border=True):
            with st.form("settings_form"):
                col1, col2 = st.columns(2)
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

                if st.form_submit_button("💾 Update Settings", type="primary"):
                    supabase_db.update_setting("target_date", str(new_goal_date))
                    supabase_db.update_setting("current_phase", new_phase)
                    supabase_db.update_setting("target_weight", new_goal_weight)
                    supabase_db.update_setting("monthly_target", new_monthly_target)
                    st.success("Settings Updated! Reloading...")
                    st.rerun()

        st.info(
            "※ ここで設定した「Goal Date」や「Target」は、シミュレーター(Tab 1)の予測線に反映されます。"
        )

        st.divider()
        st.subheader("📤 Data Export")
        st.caption(
            "指定した期間の記録（体重・摂取カロリー・PFC）をCSV形式でダウンロードします。"
        )

        with st.container(border=True):
            col_date1, col_date2 = st.columns(2)

            # デフォルト: 今月の1日 〜 今日
            today = date.today()
            this_month_start = today.replace(day=1)

            ex_start = col_date1.date_input(
                "Start Date", value=this_month_start, key="ex_start"
            )
            ex_end = col_date2.date_input("End Date", value=today, key="ex_end")

            if ex_start > ex_end:
                st.error("⚠️ 開始日は終了日より前の日付を指定してください。")
            else:
                # データのフィルタリング (raw_dfを使用)
                # raw_df["ds"] は datetime型なので、.dt.date で日付比較
                mask = (raw_df["ds"].dt.date >= ex_start) & (
                    raw_df["ds"].dt.date <= ex_end
                )
                export_df = raw_df.loc[mask].copy()

                if not export_df.empty:
                    # 必要なカラムのみ抽出・リネーム
                    # DBのカラム構成: ds, y, Calories, Protein, Fat, Carbs
                    export_df = export_df[
                        ["ds", "y", "Calories", "Protein", "Fat", "Carbs"]
                    ]
                    export_df.columns = [
                        "Date",
                        "Weight(kg)",
                        "Calories(kcal)",
                        "Protein(g)",
                        "Fat(g)",
                        "Carbs(g)",
                    ]

                    # 日付順にソート
                    export_df = export_df.sort_values("Date")

                    # CSV変換
                    csv_data = export_df.to_csv(index=False).encode("utf-8")

                    # ダウンロードボタン表示
                    c_info, c_btn = st.columns([2, 1])
                    with c_info:
                        st.write(f"📊 対象データ: **{len(export_df)}** 件")
                    with c_btn:
                        st.download_button(
                            label="📥 Download CSV",
                            data=csv_data,
                            file_name=f"bodymake_log_{ex_start}_{ex_end}.csv",
                            mime="text/csv",
                            type="primary",
                        )
                else:
                    st.warning("⚠️ 指定された期間のデータが見つかりませんでした。")


if __name__ == "__main__":
    main()
