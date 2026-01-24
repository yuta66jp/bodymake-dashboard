import numpy as np
import pandas as pd
import streamlit as st
from prophet import Prophet
from sklearn.linear_model import LinearRegression


# --- データ加工 (TDEE計算など) ---
def enrich_data(df, target_date_obj):
    if df.empty:
        return df

    # 日付(ds)が重複していたら、最後の1つだけを残して他を捨てる
    # notion_db側で作成日時順にソート済みなので、keep='last'で最新が残る
    df = df.drop_duplicates(subset=["ds"], keep="last")

    # 1. TDEE Reverse Engineering
    # 欠損日を埋めて計算精度を安定させる
    df_c = df.set_index("ds").asfreq("D").ffill().reset_index()

    # 7日間移動平均 (Weight & Calories) でノイズ（水分等）を除去 10日に変更
    df_c["w_ma"] = df_c["y"].rolling(window=10, min_periods=1).mean()

    if "Calories" in df_c.columns:
        df_c["c_ma"] = df_c["Calories"].rolling(window=10, min_periods=1).mean()
    else:
        df_c["c_ma"] = 0

    # 【重要】7日平均体重の「前日との差」をとる
    # これにより、単日の跳ね上がりを抑えた「真の体重推移」が得られる
    df_c["w_delta_smooth"] = df_c["w_ma"].diff()

    # TDEE = 摂取カロリー平均 - (平均体重の変化量 * 7200kcal) 6800kcalに修正
    df_c["real_tdee"] = df_c["c_ma"] - (df_c["w_delta_smooth"] * 6800)

    # グラフ表示用にさらに平滑化（トレンドを可視化）
    df_c["real_tdee_smooth"] = df_c["real_tdee"].rolling(window=7, min_periods=1).mean()

    # 計算結果を元のデータフレームにマージ
    df = pd.merge(df, df_c[["ds", "real_tdee_smooth", "c_ma"]], on="ds", how="left")

    # 2. Days Out (大会までの日数)
    target_dt = pd.to_datetime(target_date_obj)
    df["days_out"] = (df["ds"] - target_dt).dt.days

    # 3. Simple Moving Average (グラフ表示用)
    df["SMA_7"] = df["y"].rolling(7, 1).mean() if len(df) >= 7 else np.nan

    return df


# --- Prophet予測 (AIモデル) ---
@st.cache_resource
def run_prophet_model(df, target_date):
    # データが少なすぎる場合は予測できないのでガード
    if len(df) < 5:
        # ダミーのデータを返す
        future_dummy = pd.DataFrame(
            {"ds": [pd.to_datetime(target_date)], "yhat": [df["y"].iloc[-1]]}
        )
        return df["y"].iloc[-1], future_dummy

    # Prophetは 'ds' と 'y' カラムがあれば動作する
    m = Prophet(
        daily_seasonality=False, weekly_seasonality=True, changepoint_prior_scale=0.05
    )
    m.fit(df[["ds", "y"]])

    target_dt = pd.to_datetime(target_date)
    # 最終データ日から目標日までの日数を計算
    days = (target_dt - df["ds"].max()).days
    days = 1 if days < 1 else days

    future = m.make_future_dataframe(periods=days)
    forecast = m.predict(future)

    # 予測値の最終行を取得
    return forecast.iloc[-1]["yhat"], forecast


# --- 線形回帰トレンド (単純予測) ---
def run_linear_model(df, target_date):
    if len(df) < 2:
        return df["y"].iloc[-1] if not df.empty else 0

    start = df["ds"].min()
    # 日付を数値(経過日数)に変換
    df["d"] = (df["ds"] - start).dt.total_seconds() / 86400

    model = LinearRegression()
    # 欠損値(NaN)があるとエラーになるので除去してfit
    valid_df = df.dropna(subset=["y", "d"])
    model.fit(valid_df[["d"]], valid_df["y"])

    tgt_dt = pd.to_datetime(target_date)
    tgt_d = (tgt_dt - start).total_seconds() / 86400

    X_pred = pd.DataFrame({"d": [tgt_d]})
    pred = model.predict(X_pred)[0]
    return pred
