import numpy as np
import pandas as pd
import streamlit as st
import xgboost as xgb
from neuralprophet import NeuralProphet
from sklearn.linear_model import LinearRegression


# --- データ加工 (TDEE計算など) ---
def enrich_data(df, target_date_obj):
    if df.empty:
        return df

    # 日付重複排除
    df = df.drop_duplicates(subset=["ds"], keep="last")

    # 日付ソートを保証
    df = df.sort_values("ds")

    # 1. TDEE Reverse Engineering
    df_c = df.set_index("ds").asfreq("D").ffill().reset_index()

    # 移動平均 (Weight & Calories)
    df_c["w_ma"] = df_c["y"].rolling(window=10, min_periods=1).mean()
    if "Calories" in df_c.columns:
        df_c["c_ma"] = df_c["Calories"].rolling(window=10, min_periods=1).mean()
    else:
        df_c["c_ma"] = 0

    # 体重変化量とTDEE計算 (係数6800を採用)
    df_c["w_delta_smooth"] = df_c["w_ma"].diff()
    df_c["real_tdee"] = df_c["c_ma"] - (df_c["w_delta_smooth"] * 6800)
    df_c["real_tdee_smooth"] = df_c["real_tdee"].rolling(window=7, min_periods=1).mean()

    # マージ
    df = pd.merge(df, df_c[["ds", "real_tdee_smooth", "c_ma"]], on="ds", how="left")

    # 2. Days Out
    target_dt = pd.to_datetime(target_date_obj)
    df["days_out"] = (df["ds"] - target_dt).dt.days

    # 3. SMA (Simple Moving Average)
    df["SMA_7"] = df["y"].rolling(7, 1).mean() if len(df) >= 7 else np.nan

    return df


# logic.py


# --- NeuralProphet予測 (New Main Model) ---
@st.cache_resource
def run_neural_model(df, target_date):
    """
    NeuralProphetを使用し、長期的なトレンド予測を行う
    """
    # データ数が極端に少ない場合のガード
    if len(df) < 5:
        return df["y"].iloc[-1], pd.DataFrame(
            {"ds": [pd.to_datetime(target_date)], "yhat": [df["y"].iloc[-1]]}
        )

    # NeuralProphet用データ準備
    data = df[["ds", "y"]].copy()

    # モデル構築
    # n_lags=0 に変更: 長期予測（5月まで）を行うため、直近依存(AR)をオフにする
    # これにより、過去のデータがない未来の日付でもトレンド予測が可能になる
    m = NeuralProphet(
        n_lags=0,  # ← 【重要】長期予測のために0にする
        n_forecasts=1,
        changepoints_range=0.90,
        daily_seasonality=False,
        weekly_seasonality=True,
        yearly_seasonality=False,
        batch_size=32,
        epochs=500,  # じっくり学習
        learning_rate=0.005,  # 慎重に学習
    )

    # ログ出力を抑制
    import logging

    logging.getLogger("NP").setLevel(logging.ERROR)

    # 学習
    m.fit(data, freq="D", progress="bar")

    # --- 予測データの作成（過去 + 未来）---

    # 1. 未来の期間を計算
    target_dt = pd.to_datetime(target_date)
    last_date = data["ds"].max()
    future_days = (target_dt - last_date).days
    if future_days < 1:
        future_days = 1

    # 2. 未来用の空箱を作成
    future_df = m.make_future_dataframe(data, periods=future_days)

    # 3. 予測実行
    # 過去データ(data)に対する適合値
    forecast_train = m.predict(data)
    # 未来データ(future_df)に対する予測値
    forecast_future = m.predict(future_df)

    # 4. 結合して一本のデータにする
    forecast = pd.concat([forecast_train, forecast_future], ignore_index=True)

    # カラム名統一 ('yhat1' -> 'yhat')
    if "yhat1" in forecast.columns:
        forecast = forecast.rename(columns={"yhat1": "yhat"})

    # 最終的な予測値（目標日の値）と、全期間の予測データを返す
    return forecast["yhat"].iloc[-1], forecast


# --- XGBoost 重要度分析 (For Analytics Tab) ---
@st.cache_data
def run_xgboost_importance(df):
    """
    体重減少に影響を与えている因子を特定する
    """
    if len(df) < 14 or "Calories" not in df.columns:
        return None

    # 特徴量エンジニアリング
    d = df.copy().sort_values("ds")

    # 目的変数: 翌日の体重変動 (diff) を予測させることで「何が減量に効くか」を見る
    # y_target = (翌日の体重 - 今日の体重)
    d["target_diff"] = d["y"].shift(-1) - d["y"]

    # 説明変数 (Features)
    # 1. 食事 (昨日の摂取量が今日の変動に効くと仮定)
    d["cal_lag1"] = d["Calories"]
    if "Protein" in d.columns:
        d["p_lag1"] = d["Protein"]
    if "Fat" in d.columns:
        d["f_lag1"] = d["Fat"]
    if "Carbs" in d.columns:
        d["c_lag1"] = d["Carbs"]

    # 2. 状態
    d["current_weight"] = d["y"]
    d["rolling_cal_7"] = d["Calories"].rolling(7).mean()  # 1週間の平均摂取

    # NaN除去
    d = d.dropna()

    if d.empty:
        return None

    # 学習用データセット
    features = ["cal_lag1", "rolling_cal_7", "current_weight"]
    if "p_lag1" in d.columns:
        features.extend(["p_lag1", "f_lag1", "c_lag1"])

    X = d[features]
    y = d["target_diff"]

    # モデル学習
    model = xgb.XGBRegressor(n_estimators=100, max_depth=3, learning_rate=0.1)
    model.fit(X, y)

    # 重要度抽出
    importance_df = pd.DataFrame(
        {"Feature": features, "Importance": model.feature_importances_}
    ).sort_values("Importance", ascending=False)

    # 表示用の名前変換
    name_map = {
        "cal_lag1": "Calories (Daily)",
        "rolling_cal_7": "Calories (Weekly Avg)",
        "current_weight": "Current Bodyweight",
        "p_lag1": "Protein",
        "f_lag1": "Fat",
        "c_lag1": "Carbs",
    }
    importance_df["Feature"] = (
        importance_df["Feature"].map(name_map).fillna(importance_df["Feature"])
    )

    return importance_df


# --- 線形回帰 (トレンド補助) ---
def run_linear_model(df, target_date):
    if len(df) < 2:
        return df["y"].iloc[-1] if not df.empty else 0

    start = df["ds"].min()
    df["d"] = (df["ds"] - start).dt.total_seconds() / 86400

    model = LinearRegression()
    valid_df = df.dropna(subset=["y", "d"])
    if valid_df.empty:
        return 0

    model.fit(valid_df[["d"]], valid_df["y"])

    tgt_dt = pd.to_datetime(target_date)
    tgt_d = (tgt_dt - start).total_seconds() / 86400

    pred = model.predict(pd.DataFrame({"d": [tgt_d]}))[0]
    return pred


# --- 代謝適応シミュレーション ---
def run_metabolic_simulation(
    df, target_date, current_weight, current_tdee, plan_intake
):
    """
    【代謝適応シミュレーター】
    体重減少に伴うTDEEの低下（停滞）を数理モデルで計算する

    Parameters:
    - current_weight: 直近の体重 (kg)
    - current_tdee: 直近の計算上のTDEE (kcal)
    - plan_intake: 予定摂取カロリー (kcal) ※デフォルトは直近平均など
    """

    # 設定値: 代謝適応係数 (Adaptive Thermogenesis)
    # 体重が1kg減ると、基礎代謝 + 活動代謝が約 30kcal 落ちると仮定
    # (一般的には 15-30kcal/kg と言われるが、減量末期は高めに見積もるのが安全)
    ADAPTATION_FACTOR = 30.0

    future_dates = []
    sim_weights = []

    # 初期値設定
    sim_w = current_weight
    sim_tdee = current_tdee

    # 日付計算
    start_date = df["ds"].max()
    target_dt = pd.to_datetime(target_date)
    days_to_predict = (target_dt - start_date).days

    if days_to_predict < 1:
        return pd.DataFrame()

    # 日次ループ計算
    for i in range(1, days_to_predict + 1):
        # 1. カロリー収支 = 摂取 - 消費
        balance = plan_intake - sim_tdee

        # 2. 体重変動 (7200kcal = 1kg脂肪)
        # ※ バッファとして水分変動などは無視し、純粋なエネルギー保存則で計算
        weight_diff = balance / 7200.0

        # 3. 次の日の体重更新
        sim_w += weight_diff

        # 4. 【重要】TDEEの減衰 (Metabolic Adaptation)
        # 体重が減った分だけ、翌日の消費カロリーを減らす
        # (sim_w - current_weight) はマイナス値なので、TDEEは減少する
        weight_loss_amount = current_weight - sim_w
        sim_tdee = current_tdee - (weight_loss_amount * ADAPTATION_FACTOR)

        # 記録
        next_date = start_date + pd.Timedelta(days=i)
        future_dates.append(next_date)
        sim_weights.append(sim_w)

    # DataFrame化
    return pd.DataFrame({"ds": future_dates, "yhat_sim": sim_weights})
