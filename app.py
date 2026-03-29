import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

st.set_page_config(layout="wide", page_title="QQQ 專業撈底系統")
st.title("📊 QQQ 專業量化分析：X年一遇撈底系統")

@st.cache_data(ttl=86400)
def load_data():
    # 刪除咗手動面具，由得 yfinance 自己用最新防 block 技術
    qqq = yf.Ticker("QQQ").history(start="1999-01-01")
    
    if qqq.index.tz is not None:
        qqq.index = qqq.index.tz_convert(None)
    
    weekly = qqq.resample('W-FRI').agg({
        'Open': 'first', 'High': 'max', 'Low': 'min', 'Close': 'last', 'Volume': 'sum'
    })
    
    delta = weekly['Close'].diff()
    gain = (delta.where(delta > 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss
    weekly['14_Week_RSI'] = 100 - (100 / (1 + rs))
    
    weekly = weekly.dropna().round(2)
    return weekly

full_data = load_data()

def find_events(df, threshold, gap_weeks=26): 
    dips = df[df['14_Week_RSI'] <= threshold]
    if dips.empty: return []
    
    events = []
    current_event = [dips.index[0]]
    
    for date in dips.index[1:]:
        if (date - current_event[-1]).days <= gap_weeks * 7:
            current_event.append(date)
        else:
            events.append(current_event)
            current_event = [date]
    events.append(current_event)
    
    event_dates = []
    for ev in events:
        first_trigger_date = ev[0] 
        event_dates.append(first_trigger_date)
        
    return event_dates

# --- 網頁控制面板 ---
st.markdown("### 🎯 設定分析參數")
col_sel1, col_sel2, col_stat = st.columns([1, 1, 2])

with col_sel1:
    target_years = st.selectbox("你想搵幾多年一遇嘅低位？", [1, 2, 3, 4, 5, 10], index=2) 

with col_sel2:
    lookback_choice = st.selectbox("使用幾多年嘅歷史數據？", [10, 15, 20, 25, "全部 (1999年起)"], index=2)

latest_date = full_data.index.max()
latest_price = full_data['Close'].iloc[-1] 

if lookback_choice != "全部 (1999年起)":
    start_date = latest_date - pd.DateOffset(years=lookback_choice)
    analysis_data = full_data[full_data.index >= start_date].copy()
    actual_total_years = lookback_choice
else:
    analysis_data = full_data.copy()
    actual_total_years = (latest_date - full_data.index.min()).days / 365.25

target_events_count = actual_total_years / target_years
best_threshold = 50
best_events = []

for thresh in range(50, 10, -1):
    events = find_events(analysis_data, thresh)
    if len(events) <= target_events_count:
        best_threshold = thresh
        best_events = events
        break

with col_stat:
    st.info(f"💡 基於過去 **{actual_total_years} 年** 數據，對應平均 {target_years} 年一遇嘅 RSI 觸發點係 **{best_threshold}**。\n\n"
            f"共觸發 **{len(best_events)} 次** (以每浪首次跌穿為準)。")

fig = make_subplots(rows=2, cols=1, shared_xaxes=True, 
                    vertical_spacing=0.05, row_heights=[0.6, 0.4],
                    subplot_titles=(f"QQQ 週線陰陽燭", "14週 RSI"))

fig.add_trace(go.Candlestick(
    x=analysis_data.index,
    open=analysis_data['Open'], high=analysis_data['High'],
    low=analysis_data['Low'], close=analysis_data['Close'],
    name='QQQ 陰陽燭',
    increasing_line_color='green', decreasing_line_color='red' 
), row=1, col=1)

fig.add_trace(go.Scatter(
    x=analysis_data.index, y=analysis_data['14_Week_RSI'], 
    name='RSI', line=dict(color='purple')
), row=2, col=1)

fig.add_hrect(
    y0=30, y1=70, fillcolor="lightblue", opacity=0.2, 
    line_width=0, layer="below", row=2, col=1
)

fig.add_hline(y=best_threshold, line_width=2, line_color="orange", row=2, col=1, annotation_text=f"動態觸發點 ({best_threshold})")

if best_events:
    event_data = analysis_data.loc[best_events]
    fig.add_trace(go.Scatter(
        x=event_data.index, y=event_data['Close'], 
        mode='markers+text', 
        marker=dict(color='blue', size=12, symbol='triangle-up'),
        text=event_data['Close'].apply(lambda x: f"${x:.2f}"), 
        textposition="bottom center", 
        textfont=dict(color='blue', size=13, family="Arial Black"),
        name='觸發點收市價'
    ), row=1, col=1)
    
    fig.add_trace(go.Scatter(
        x=event_data.index, y=event_data['14_Week_RSI'], 
        mode='markers', marker=dict(color='blue', size=10, symbol='circle'),
        name='首穿 RSI 點'
    ), row=2, col=1)

fig.update_yaxes(side="right")

fig.update_layout(
    height=750, 
    hovermode="x unified", 
    showlegend=False,
    xaxis_rangeslider_visible=False,
    dragmode="pan",
    updatemenus=[dict(
        type="buttons",
        direction="right",
        x=1.0, y=1.05,
        xanchor='right', yanchor='bottom',
        buttons=list([
            dict(
                args=[{"xaxis.autorange": True, "yaxis.autorange": True, "yaxis2.autorange": True}],
                label="🔄 重置圖表比例 (Reset)",
                method="relayout"
            )
        ]),
        font=dict(size=14, color="white"),
        bgcolor="royalblue",
        borderwidth=2,
        bordercolor="darkblue"
    )]
)

st.plotly_chart(fig, use_container_width=True, config={'scrollZoom': True})

# --- 🎯 回測報告區塊 ---
st.divider()
st.header("💰 回測報告：撈底後持倉至今真實績效")
st.write(f"假設你喺每一個藍色觸發點買入，並一直持倉到今日（最新價格: **${latest_price:.2f}**）：")

if best_events:
    results = []
    
    for ev_date in best_events:
        buy_price = full_data.loc[ev_date, 'Close']
        
        one_year_later = ev_date + pd.DateOffset(years=1)
        if one_year_later <= latest_date:
            closest_1y_idx = full_data.index.get_indexer([one_year_later], method='nearest')[0]
            p_1y = full_data['Close'].iloc[closest_1y_idx]
            ret_1y = (p_1y - buy_price) / buy_price
            ret_1y_str = f"{ret_1y*100:.1f}%"
        else:
            ret_1y_str = "未滿一年"
            
        three_years_later = ev_date + pd.DateOffset(years=3)
        if three_years_later <= latest_date:
            closest_3y_idx = full_data.index.get_indexer([three_years_later], method='nearest')[0]
            p_3y = full_data['Close'].iloc[closest_3y_idx]
            ret_3y = (p_3y - buy_price) / buy_price
            ret_3y_str = f"{ret_3y*100:.1f}%"
        else:
            ret_3y_str = "未滿三年"

        hold_years = (latest_date - ev_date).days / 365.25
        tot_ret = (latest_price - buy_price) / buy_price
        
        if hold_years > 0:
            avg_annual_ret = tot_ret / hold_years
            cagr = ((latest_price / buy_price) ** (1 / hold_years)) - 1
        else:
            avg_annual_ret = 0
            cagr = 0
            
        results.append({
            "買入日期": ev_date.strftime('%Y-%m-%d'),
            "買入價": f"${buy_price:.2f}",
            "1年後回報": ret_1y_str,
            "3年後回報": ret_3y_str,
            "持倉時間": f"{hold_years:.1f} 年",
            "至今總回報": f"{tot_ret*100:.1f}%",
            "平均年回報": f"{avg_annual_ret*100:.1f}%",
            "複式回報 (CAGR)": f"{cagr*100:.1f}%"
        })

    res_df = pd.DataFrame(results)
    
    def highlight_positive(val):
        if isinstance(val, str) and '%' in val:
            num = float(val.replace('%', ''))
            color = 'green' if num > 0 else 'red'
            return f'color: {color}; font-weight: bold'
        return ''
        
    st.dataframe(res_df.style.map(highlight_positive), use_container_width=True, hide_index=True)
