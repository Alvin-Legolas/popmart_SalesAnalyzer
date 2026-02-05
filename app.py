# ==============================
# 1> 设置 matplotlib 后端
# ==============================
import os
import re
from datetime import datetime, timedelta
from collections import defaultdict

os.environ["MPLBACKEND"] = "Agg"

# ==============================
# 2> 导入库
# ==============================
import pandas as pd
import numpy as np
import gradio as gr
import matplotlib

matplotlib.use("Agg", force=True)
import matplotlib.pyplot as plt
import io
import base64

# 设置中文字体（避免中文显示为方框或报 glyph 警告）
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False  # 正常显示负号

# ==============================
# 3>加载 Excel 数据
# ==============================
# desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
# file_path = os.path.join(desktop, "popmart_sales.xlsx")

# try:
#     df = pd.read_excel(file_path)
#     df['date'] = pd.to_datetime(df['date'])
#     print(f"✅ 数据加载成功，共 {len(df)} 条记录")
# except Exception as e:
#     print(f"❌ 数据加载失败: {e}")
#     # 创建模拟数据供演示
#     ... # 删除所有模拟数据代码

# ==============================
# 4> 初始化全局变量和配置
# ==============================
df = None  # 数据将在这里存储
IPS = ['Molly', 'Dimoo', 'Skullpanda', 'Crybaby', 'Pucky', 'The Monsters']
REGIONS = ['华东', '华北', '华南', '华中', '西南', '西北']

# 用户对话历史（简单内存存储）
conversation_history = defaultdict(list)

# 异常检测缓存
last_anomaly_check = None
anomaly_cache = []


# ==============================
# 5> 辅助函数
# ==============================

def load_data(file):
    """加载用户上传的文件"""
    global df, IPS, REGIONS

    try:
        # 读取上传的文件
        if isinstance(file, str):
            file_path = file
        else:
            file_path = file.name

        # 加载数据
        df = pd.read_excel(file_path)
        df['date'] = pd.to_datetime(df['date'])

        # 动态提取IP和区域列表
        if 'ip' in df.columns:
            IPS = sorted(df['ip'].dropna().unique().tolist())
        if 'region' in df.columns:
            REGIONS = sorted(df['region'].dropna().unique().tolist())

        return f"✅ 数据加载成功！共 {len(df)} 条记录，{len(IPS)} 个IP，{len(REGIONS)} 个区域"

    except Exception as e:
        return f"❌ 数据加载失败: {str(e)}"

def get_time_filter(query):
    """从查询中提取时间范围"""
    today = pd.Timestamp.now().date()

    if "今天" in query:
        start_date = today
        end_date = today
        label = "今天"
    elif "昨天" in query:
        start_date = today - timedelta(days=1)
        end_date = start_date
        label = "昨天"
    elif "最近7天" in query or "近7天" in query:
        start_date = today - timedelta(days=7)
        end_date = today
        label = "最近7天"
    elif "最近30天" in query or "近30天" in query:
        start_date = today - timedelta(days=30)
        end_date = today
        label = "最近30天"
    elif "本周" in query:
        start_date = today - timedelta(days=today.weekday())
        end_date = today
        label = "本周"
    elif "上周" in query:
        start_date = today - timedelta(days=today.weekday() + 7)
        end_date = start_date + timedelta(days=6)
        label = "上周"
    elif "本月" in query:
        start_date = today.replace(day=1)
        end_date = today
        label = "本月"
    else:
        # 默认使用全部数据
        start_date = df['date'].min().date()
        end_date = df['date'].max().date()
        label = "全部"

    return start_date, end_date, label

def extract_compare_items(query):
    """从查询中提取对比项"""
    items = []

    # 检查IP对比
    for ip in IPS:
        if ip in query:
            items.append(('ip', ip))

    # 检查区域对比
    for region in REGIONS:
        if region in query:
            items.append(('region', region))

    return items


def detect_anomalies():
    """自动检测异常情况"""
    global last_anomaly_check, anomaly_cache

    # 每小时检查一次
    current_time = datetime.now()
    if last_anomaly_check and (current_time - last_anomaly_check).seconds < 3600:
        return anomaly_cache

    anomalies = []

    # 获取最近7天的数据
    today = pd.Timestamp.now().date()
    week_ago = today - timedelta(days=7)
    recent_df = df[df['date'].dt.date >= week_ago]

    if recent_df.empty:
        last_anomaly_check = current_time
        anomaly_cache = anomalies
        return anomalies

    # 1. 检查整体销量异常
    daily_sales = recent_df.groupby(recent_df['date'].dt.date)['sales'].sum()
    if len(daily_sales) >= 3:
        avg_sales = daily_sales.mean()
        std_sales = daily_sales.std()

        for date, sales in daily_sales.items():
            if std_sales > 0 and abs(sales - avg_sales) > 2 * std_sales:
                diff_pct = ((sales - avg_sales) / avg_sales) * 100
                anomalies.append(f"📊 {date} 整体销量{'异常高' if diff_pct > 0 else '异常低'} ({diff_pct:+.1f}%)")
                break

    # 2. 检查各IP的异常波动
    for ip in IPS:
        ip_data = df[df['ip'] == ip]
        if len(ip_data) < 7:
            continue

        # 计算最近3天 vs 前4天的对比
        recent_3d = ip_data.tail(3)['sales'].mean()
        prev_4d = ip_data.tail(7).head(4)['sales'].mean()

        if prev_4d > 0:
            change = ((recent_3d - prev_4d) / prev_4d) * 100
            if abs(change) > 30:  # 波动超过30%
                anomalies.append(f"🎭 {ip} 销量{'' if change > 0 else '大幅'}波动 ({change:+.1f}%)")

    # 3. 检查区域异常
    for region in REGIONS:
        region_data = df[df['region'] == region]
        if len(region_data) < 7:
            continue

        recent_avg = region_data.tail(3)['sales'].mean()
        prev_avg = region_data.tail(7).head(4)['sales'].mean()

        if prev_avg > 0:
            change = ((recent_avg - prev_avg) / prev_avg) * 100
            if change < -20:  # 下降超过20%
                anomalies.append(f"📍 {region} 区域销量明显下降 ({change:+.1f}%)")

    last_anomaly_check = current_time
    anomaly_cache = anomalies[:5]  # 只保留前5个异常
    return anomaly_cache


def get_smart_suggestions(user_id="default"):
    """生成智能问题建议"""
    suggestions = []

    # 1. 基于热门数据
    hot_ip = df.groupby('ip')['sales'].sum().idxmax()
    hot_region = df.groupby('region')['sales'].sum().idxmax()
    suggestions.append(f"{hot_ip}在{hot_region}最近表现怎样？")

    # 2. 基于增长趋势
    growth_data = []
    for ip in IPS:
        ip_data = df[df['ip'] == ip]
        if len(ip_data) >= 14:
            week2 = ip_data.tail(7)['sales'].sum()
            week1 = ip_data.tail(14).head(7)['sales'].sum()
            if week1 > 0:
                growth = ((week2 - week1) / week1) * 100
                growth_data.append((ip, growth))

    if growth_data:
        fastest_ip = max(growth_data, key=lambda x: x[1])
        suggestions.append(f"{fastest_ip[0]}为什么增长这么快？(+{fastest_ip[1]:.1f}%)")

    # 3. 基于用户历史
    if user_id in conversation_history and conversation_history[user_id]:
        last_query = conversation_history[user_id][-1]
        # 从上次查询中提取关键词
        for ip in IPS:
            if ip in last_query:
                for region in REGIONS:
                    if region not in last_query:
                        suggestions.append(f"{ip}在{region}的销量怎么样？")
                break

    # 4. 通用建议
    suggestions.append("<span style='color: black;'>今天销量最好的IP是哪个？</span>")
    suggestions.append("<span style='color: black;'>对比一下Molly和Dimoo的销量</span>")
    suggestions.append("<span style='color: black;'>最近7天各区域销量排名</span>")
    suggestions.append("<span style='color: black;'>哪个IP增长最快？</span>")
    suggestions.append("<span style='color: black;'>Dimoo在华南最近表现怎样？</span>")
    suggestions.append("<span style='color: black;'>Dimoo为什么增长这么快？(+17.5%)</span>")
    suggestions.append("<span style='color: black;'>Dimoo在华南最近表现怎样？</span>")

    return list(set(suggestions))[:6]  # 去重并限制数量


def create_comparison_chart(items, time_label):
    """创建对比图表"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # 提取时间范围
    start_date, end_date, _ = get_time_filter(time_label)
    time_filtered_df = df[
        (df['date'].dt.date >= start_date) &
        (df['date'].dt.date <= end_date)
        ]

    # 准备对比数据
    comparison_data = []
    labels = []

    for item_type, item_name in items:
        if item_type == 'ip':
            item_sales = time_filtered_df[time_filtered_df['ip'] == item_name]['sales'].sum()
            labels.append(f"{item_name}(IP)")
        else:  # region
            item_sales = time_filtered_df[time_filtered_df['region'] == item_name]['sales'].sum()
            labels.append(f"{item_name}(区域)")
        comparison_data.append(item_sales)

    # 柱状图
    bars = ax1.bar(range(len(comparison_data)), comparison_data, color=['#FF6B6B', '#4ECDC4', '#45B7D1'])
    ax1.set_title(f'{time_label}对比', fontsize=14)
    ax1.set_xticks(range(len(comparison_data)))
    ax1.set_xticklabels(labels, rotation=45, ha='right')
    ax1.set_ylabel('销量（件）')

    # 添加数据标签
    for bar in bars:
        height = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width() / 2., height + max(comparison_data) * 0.01,
                 f'{int(height)}', ha='center', va='bottom', fontsize=10)

    # 饼图（如果有2-3个对比项）
    if 2 <= len(comparison_data) <= 3:
        ax2.pie(comparison_data, labels=labels, autopct='%1.1f%%',
                colors=['#FF6B6B', '#4ECDC4', '#45B7D1'])
        ax2.set_title('占比分布', fontsize=14)
    else:
        ax2.text(0.5, 0.5, '对比项过多，\n建议对比2-3个项目',
                 ha='center', va='center', fontsize=12, transform=ax2.transAxes)
        ax2.set_title('提示', fontsize=14)

    plt.tight_layout()

    # 转换为Base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')

    return img_b64


def simple_forecast(ip, region=None, days=7):
    """简单预测未来销量"""
    sub_df = df[df['ip'] == ip]
    if region:
        sub_df = sub_df[sub_df['region'] == region]

    if len(sub_df) < 7:
        return None, "数据不足，无法预测"

    # 使用最近14天数据
    recent = sub_df.tail(14)['sales'].values

    # 方法1：移动平均
    ma_window = 7
    if len(recent) >= ma_window:
        ma_value = recent[-ma_window:].mean()
    else:
        ma_value = recent.mean()

    # 方法2：加权平均（最近的值权重更高）
    weights = np.arange(1, len(recent) + 1)
    weighted_avg = np.average(recent, weights=weights)

    # 方法3：简单趋势
    if len(recent) >= 7:
        recent_trend = recent[-7:].mean() - recent[-14:-7].mean()
        trend_value = recent[-1] + recent_trend
    else:
        trend_value = recent[-1]

    # 综合预测（取三种方法的平均值）
    forecast_avg = np.mean([ma_value, weighted_avg, trend_value])

    # 生成预测值（加入小幅波动）
    forecast_values = [max(10, forecast_avg * (1 + np.random.uniform(-0.1, 0.1))) for _ in range(days)]

    # 趋势判断
    if len(recent) >= 7:
        week2 = recent[-7:].mean()
        week1 = recent[-14:-7].mean() if len(recent) >= 14 else recent[-7:].mean()
        trend_pct = ((week2 - week1) / week1 * 100) if week1 > 0 else 0
    else:
        trend_pct = 0

    trend_text = "上升" if trend_pct > 5 else ("下降" if trend_pct < -5 else "平稳")

    forecast_info = {
        'values': forecast_values,
        'avg': np.mean(forecast_values),
        'trend': trend_text,
        'trend_pct': trend_pct,
        'confidence': min(85, max(50, 100 - abs(trend_pct) / 2))  # 置信度估算
    }

    return forecast_info, None


def generate_forecast_chart(ip, region, forecast_info):
    """生成预测图表"""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # 历史数据（最近14天）
    sub_df = df[df['ip'] == ip]
    if region:
        sub_df = sub_df[sub_df['region'] == region]

    history_dates = sub_df.tail(14)['date'].tolist()
    history_sales = sub_df.tail(14)['sales'].tolist()

    # 预测日期（未来7天）
    if history_dates:
        last_date = history_dates[-1]
        forecast_dates = [last_date + timedelta(days=i + 1) for i in range(7)]
    else:
        forecast_dates = [datetime.now() + timedelta(days=i + 1) for i in range(7)]

    # 历史趋势图
    ax1.plot(history_dates, history_sales, 'b-o', linewidth=2, markersize=4, label='历史销量')
    ax1.set_title(f'{ip}在{region if region else "全国"}的历史销量', fontsize=12)
    ax1.set_xlabel('日期')
    ax1.set_ylabel('销量（件）')
    ax1.grid(True, linestyle='--', alpha=0.5)
    ax1.legend()
    ax1.tick_params(axis='x', rotation=45)

    # 预测图
    ax2.bar(range(7), forecast_info['values'], color='orange', alpha=0.7, label='预测销量')
    ax2.axhline(y=forecast_info['avg'], color='red', linestyle='--', label=f'预测均值: {forecast_info["avg"]:.1f}')
    ax2.set_title('未来7天销量预测', fontsize=12)
    ax2.set_xlabel('未来天数')
    ax2.set_ylabel('预测销量（件）')
    ax2.set_xticks(range(7))
    ax2.set_xticklabels([f'第{i + 1}天' for i in range(7)])
    ax2.grid(True, linestyle='--', alpha=0.5)
    ax2.legend()

    plt.tight_layout()

    # 转换为Base64
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150)
    plt.close()
    buf.seek(0)
    img_b64 = base64.b64encode(buf.read()).decode('utf-8')

    return img_b64


# ==============================
# 6> 主分析函数（增强版）
# ==============================

def analyze(query: str, user_id: str = "default"):
    """增强版分析函数"""
    global df, IPS, REGIONS

    # 检查数据是否已加载
    if df is None:
        return """
        <div style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h3>📁 请先上传数据文件</h3>
            <p>请点击左侧的"上传文件"按钮，上传您的销售数据Excel文件</p>
            <p style="color: #666; margin-top: 20px;">💡 支持 .xlsx 和 .xls 格式</p>
            <p style="color: #666;">📊 文件应包含：date, ip, region, sales 等列</p>
        </div>
        """

    # 原有的对话历史记录代码继续...
    if user_id:
        conversation_history[user_id].append({
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'query': query,
            'response': '待生成'
        })
        # 只保留最近10条历史
        conversation_history[user_id] = conversation_history[user_id][-10:]

    query = query.strip()

    # 空查询：显示智能建议
    if not query:
        anomalies = detect_anomalies()
        suggestions = get_smart_suggestions(user_id)

        html = """
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h3>🤖 泡泡玛特销售分析助手</h3>
            <p>基于实时销售数据，为您提供深度分析和智能建议</p>
        """

        # 显示异常预警（如果有）
        if anomalies:
            html += """
            <div style="background: #fff3cd; padding: 15px; border-radius: 8px; margin: 15px 0; border-left: 4px solid #ffc107;">
                <h4 style="margin-top: 0; color: #FF6347 !important; background: transparent !important;">🔔 系统预警</h4>
                <ul style="margin-bottom: 0;">
            """
            for anomaly in anomalies[:3]:  # 只显示前3个异常
                html += f"<li>{anomaly}</li>"
            html += """
                </ul>
            </div>
            """

        # 显示智能建议
        html += """
            <div style="margin: 20px 0;">
                <h4 style="color: white;">💡 智能推荐问题：</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 12px; margin-top: 15px;">
        """

        for i, suggestion in enumerate(suggestions):
            color = ['#e3f2fd', '#f3e5f5', '#e8f5e8', '#fff3e0', '#fce4ec', '#f3e5f5'][i % 6]
            html += f"""
                <div style="background: {color}; padding: 12px; border-radius: 8px; border: 1px solid #ddd;">
                    <div style="font-weight: bold; margin-bottom: 5px; color: #000000 !important;">📌 {suggestion}</div>
                </div>
            """

        html += """
                </div>
            </div>

            <div style="margin-top: 25px; padding-top: 15px; border-top: 1px solid #eee;">
                <h4>🎯 支持的分析类型：</h4>
                <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px;">
    <span style="background: #e8f5e8; padding: 5px 10px; border-radius: 15px; color: #000000;">IP排名分析</span>
    <span style="background: #e3f2fd; padding: 5px 10px; border-radius: 15px; color: #000000;">区域表现</span>
    <span style="background: #f3e5f5; padding: 5px 10px; border-radius: 15px; color: #000000;">趋势对比</span>
    <span style="background: #fff3e0; padding: 5px 10px; border-radius: 15px; color: #000000;">销量预测</span>
    <span style="background: #fce4ec; padding: 5px 10px; border-radius: 15px; color: #000000;">异常检测</span>
    <span style="background: #e0f2f1; padding: 5px 10px; border-radius: 15px; color: #000000;">时间分析</span>
</div>

                <div style="margin-top: 20px;">
                    <h5>📝 示例问题：</h5>
                    <ul>
                        <li><b>时间分析：</b>"昨天销量如何？"、"最近7天趋势"</li>
                        <li><b>对比分析：</b>"Molly和Dimoo哪个卖得好？"、"华东 vs 华南"</li>
                        <li><b>预测分析：</b>"预测Molly下周销量"</li>
                        <li><b>排名分析：</b>"销量前3名"、"增长最快的IP"</li>
                    </ul>
                </div>
            </div>
        </div>
        """

        return html

    # ==================== 1. 时间范围查询 ====================
    time_keywords = ["今天", "昨天", "最近7天", "近7天", "最近30天", "近30天", "本周", "上周", "本月"]
    if any(keyword in query for keyword in time_keywords):
        start_date, end_date, time_label = get_time_filter(query)
        time_df = df[(df['date'].dt.date >= start_date) & (df['date'].dt.date <= end_date)]
        if time_df.empty:
            return f"<div style='color: #e74c3c;'>❌ 未找到{time_label}的销售数据</div>"
        # 总体统计
        total_sales = time_df['sales'].sum()
        avg_daily = time_df['sales'].mean()
        # 按IP排名
        ip_ranking = time_df.groupby('ip')['sales'].sum().sort_values(ascending=False).head(5)
        top_ip = ip_ranking.index[0] if not ip_ranking.empty else "无"
        # 按区域排名
        region_ranking = time_df.groupby('region')['sales'].sum().sort_values(ascending=False).head(3)
        # 生成图表
        plt.figure(figsize=(10, 8))

        # 1. 日销量趋势
        plt.subplot(2, 2, 1)
        # 生成最近7天完整日期
        today = pd.Timestamp.now().date()
        dates = [today - pd.Timedelta(days=6 - i) for i in range(7)]
        # 获取销量（无数据为0）
        sales_by_date = time_df.groupby(time_df['date'].dt.date)['sales'].sum()
        sales = [sales_by_date.get(d, 0) for d in dates]
        # 创建标签：今天/昨天/月-日
        labels = []
        for d in dates:
            if d == today:
                labels.append("今天")
            elif d == today - pd.Timedelta(days=1):
                labels.append("昨天")
            else:
                labels.append(d.strftime('%m-%d'))

        # 画图
        x = range(7)
        plt.plot(x, sales, 'b-o', linewidth=2, markersize=4)
        plt.title('最近7天日销量趋势')
        plt.xlabel('日期')
        plt.ylabel('销量（件）')
        plt.xticks(x, labels, rotation=0, ha='center')
        plt.grid(True, alpha=0.3)

        # 2. IP销量分布（前5名）
        plt.subplot(2, 2, 2)
        plt.bar(range(len(ip_ranking)), ip_ranking.values, color='skyblue')
        plt.title(f'{time_label}IP销量Top 5')
        plt.xlabel('IP')
        plt.ylabel('销量（件）')
        plt.xticks(range(len(ip_ranking)), ip_ranking.index, rotation=45)
        for i, v in enumerate(ip_ranking.values):
            plt.text(i, v + max(ip_ranking.values) * 0.01, str(v), ha='center', va='bottom')

        # 3. 区域分布（饼图）
        plt.subplot(2, 2, 3)
        plt.pie(region_ranking.values, labels=region_ranking.index, autopct='%1.1f%%')
        plt.title(f'{time_label}区域销量Top 3')

        # 4. 热力图（IP × 日期）
        plt.subplot(2, 2, 4)
        try:
            pivot_data = time_df.pivot_table(index='ip', columns=time_df['date'].dt.date, values='sales', aggfunc='sum')
            im = plt.imshow(pivot_data.fillna(0).values, aspect='auto', cmap='YlOrRd')
            plt.colorbar(im, label='销量')
            plt.title('IP-日期热力图')
            plt.xlabel('日期')
            plt.ylabel('IP')
            plt.yticks(range(len(pivot_data.index)), pivot_data.index)
            plt.xticks(range(len(pivot_data.columns)), [str(d)[5:] for d in pivot_data.columns], rotation=45)
        except:
            plt.text(0.5, 0.5, '数据过多\n无法显示热力图', ha='center', va='center', transform=plt.gca().transAxes)
            plt.title('IP-日期热力图')

        plt.tight_layout()

        # 转换为Base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        plt.close()
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')

        # 生成报告
        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h3>📅 {time_label}销售分析报告</h3>

            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h4 style="margin-top: 0;">📊 核心指标</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div style="background: white; padding: 15px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="font-size: 12px; color: #666;">总销量</div>
                        <div style="font-size: 24px; font-weight: bold; color: #2c3e50;">{total_sales:,} 件</div>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="font-size: 12px; color: #666;">日均销量</div>
                        <div style="font-size: 24px; font-weight: bold; color: #2c3e50;">{avg_daily:.1f} 件</div>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="font-size: 12px; color: #666;">最受欢迎IP</div>
                        <div style="font-size: 24px; font-weight: bold; color: #2c3e50;">{top_ip}</div>
                    </div>
                </div>
            </div>

            <div style="margin: 20px 0;">
                <h4>📈 可视化分析</h4>
                <img src="data:image/png;base64,{img_b64}" style="max-width:100%; border: 1px solid #ddd; border-radius: 8px;">
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0;">
                <div style="background: #e8f5e8; padding: 15px; border-radius: 8px;">
                    <h5 style="margin-top: 0;">🏆 IP销量排名（Top 5）</h5>
                    <ol>
        """

        for i, (ip, sales) in enumerate(ip_ranking.items(), 1):
            html += f"<li><b>{ip}</b>: {sales:,} 件</li>"

        html += """
                    </ol>
                </div>
                <div style="background: #e3f2fd; padding: 15px; border-radius:8px;">
                    <h5 style="margin-top: 0;">🌍 区域表现（Top 3）</h5>
                    <ol>
        """
        for i, (region, sales) in enumerate(region_ranking.items(), 1):
            html += f"<li><b>{region}</b>: {sales:,} 件</li>"
        html += f"""
                    </ol>
                </div>
            </div>
            <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <h5 style="margin-top: 0;">💡 运营建议</h5>
                <p>根据{time_label}数据分析：</p>
                <ul>
        """
        if avg_daily > time_df['sales'].quantile(0.75):
            html += "<li>销售表现良好，建议保持当前策略</li>"
        else:
            html += "<li>销售有提升空间，建议分析具体原因并制定提升策略</li>"
        if ip_ranking.iloc[0] > ip_ranking.iloc[1] * 1.5:
            html += f"<li>{top_ip}表现突出，可考虑加大相关产品推广力度</li>"
        html += """
                    <li>关注热销区域的成功经验，复制到其他区域</li>
                    <li>定期监控销售趋势，及时调整库存和营销策略</li>
                </ul>
            </div>
        </div>
        """
        return html

    # ==================== 2. 对比分析查询 ====================
    compare_keywords = ["对比", "比较", "vs", "VS", "和", "哪个"]
    if any(keyword in query for keyword in compare_keywords):
        compare_items = extract_compare_items(query)

        if len(compare_items) < 2:
            return """
            <div style="color: #e74c3c;">
                ❌ 对比分析需要至少两个对比项（IP或区域）
                <br>例如："Molly和Dimoo哪个卖得好？" 或 "华东 vs 华南"
            </div>
            """

        # 确定时间范围
        time_start, time_end, time_label = get_time_filter(query)

        # 生成对比图表
        img_b64 = create_comparison_chart(compare_items[:3], time_label)  # 最多对比3项

        # 获取详细数据
        start_date, end_date, _ = get_time_filter(time_label)
        time_filtered_df = df[
            (df['date'].dt.date >= start_date) &
            (df['date'].dt.date <= end_date)
            ]

        comparison_data = []
        for item_type, item_name in compare_items[:3]:
            if item_type == 'ip':
                sales = time_filtered_df[time_filtered_df['ip'] == item_name]['sales'].sum()
            else:
                sales = time_filtered_df[time_filtered_df['region'] == item_name]['sales'].sum()
            comparison_data.append((item_name, sales, item_type))

        # 排序并找出最佳
        comparison_data.sort(key=lambda x: x[1], reverse=True)
        best_item = comparison_data[0]

        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h3>🔄 {time_label}对比分析</h3>
            <p>对比项：{', '.join([f'{name}({typ})' for name, _, typ in comparison_data])}</p>

            <div style="margin: 20px 0;">
                <img src="data:image/png;base64,{img_b64}" style="max-width:100%; border: 1px solid #ddd; border-radius: 8px;">
            </div>

            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin: 15px 0;">
                <h4 style="margin-top: 0;">📊 对比结果</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #e9ecef;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">项目</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">类型</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">{time_label}销量</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">排名</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for i, (name, sales, typ) in enumerate(comparison_data, 1):
            html += f"""
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;"><b>{name}</b></td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">{typ}</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">{sales:,} 件</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">第{i}名</td>
                        </tr>
            """

        html += f"""
                    </tbody>
                </table>
            </div>

            <div style="background: #d4edda; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <h5 style="margin-top: 0; color: #155724;">🎯 核心结论</h5>
                <p>在{time_label}期间，表现最佳的是 <b>{best_item[0]}</b>（{best_item[2]}），
                销量达 <b>{best_item[1]:,} 件</b>。</p>

                <p><b>优势分析：</b></p>
                <ul>
        """

        # 计算优势百分比
        if len(comparison_data) >= 2:
            advantage = ((best_item[1] - comparison_data[1][1]) / comparison_data[1][1]) * 100
            html += f"<li>领先第二名 {advantage:.1f}%</li>"

        if best_item[2] == 'ip':
            # 如果是IP，分析其最佳区域
            ip_data = time_filtered_df[time_filtered_df['ip'] == best_item[0]]
            if not ip_data.empty:
                best_region = ip_data.groupby('region')['sales'].sum().idxmax()
                region_sales = ip_data.groupby('region')['sales'].sum().max()
                html += f"<li>在 <b>{best_region}</b> 区域表现最佳（{region_sales:,}件）</li>"

        html += """
                </ul>

                <p><b>行动建议：</b></p>
                <ul>
        """

        if best_item[2] == 'ip':
            html += f"""
                    <li>加大 <b>{best_item[0]}</b> 的推广力度，巩固市场优势</li>
                    <li>分析 {best_item[0]} 的成功因素，复制到其他IP</li>
                    <li>考虑推出 {best_item[0]} 的限量版或联名款</li>
            """
        else:
            html += f"""
                    <li>总结 <b>{best_item[0]}</b> 区域的销售经验</li>
                    <li>将成功经验推广到其他区域</li>
                    <li>考虑在 {best_item[0]} 增加门店或营销资源</li>
            """

        html += """
                </ul>
            </div>
        </div>
        """

        return html

    # ==================== 3. 排名查询 ====================
    rank_keywords = ["排名", "前", "名", "top", "Top", "排行榜"]
    if any(keyword in query for keyword in rank_keywords):
        # 提取排名数量
        n = 3  # 默认显示前3名
        match = re.search(r'前(\d+)名', query)
        if match:
            n = int(match.group(1))
        elif "top" in query.lower():
            match = re.search(r'top\s*(\d+)', query.lower())
            if match:
                n = int(match.group(1))

        # 限制范围
        n = min(n, 10)

        # 确定排名维度
        if "区域" in query or "地区" in query:
            # 区域排名
            ranking = df.groupby('region')['sales'].sum().sort_values(ascending=False).head(n)
            rank_type = "区域"
            rank_items = [f"{region}" for region in ranking.index]
        elif "增长" in query or "上升" in query:
            # 增长排名
            growth_data = []
            for ip in IPS:
                ip_data = df[df['ip'] == ip]
                if len(ip_data) >= 14:
                    week2 = ip_data.tail(7)['sales'].sum()
                    week1 = ip_data.tail(14).head(7)['sales'].sum()
                    if week1 > 0:
                        growth = ((week2 - week1) / week1) * 100
                        growth_data.append((ip, growth))

            growth_data.sort(key=lambda x: x[1], reverse=True)
            ranking = pd.Series({ip: growth for ip, growth in growth_data[:n]})
            rank_type = "增长"
            rank_items = [f"{ip}" for ip in ranking.index]
        else:
            # IP排名（默认）
            ranking = df.groupby('ip')['sales'].sum().sort_values(ascending=False).head(n)
            rank_type = "IP"
            rank_items = [f"{ip}" for ip in ranking.index]

        # 生成图表
        plt.figure(figsize=(10, 6))

        if rank_type == "增长":
            colors = ['#2ecc71' if val > 0 else '#e74c3c' for val in ranking.values]
            bars = plt.bar(range(len(ranking)), ranking.values, color=colors)
            plt.title(f'{rank_type}速度Top {n}', fontsize=14)
            plt.ylabel('增长率 (%)')
        else:
            bars = plt.bar(range(len(ranking)), ranking.values, color='#3498db')
            plt.title(f'{rank_type}销量Top {n}', fontsize=14)
            plt.ylabel('销量（件）')

        plt.xlabel(rank_type)
        plt.xticks(range(len(ranking)), rank_items, rotation=45, ha='right')

        # 添加数值标签
        for bar in bars:
            height = bar.get_height()
            if rank_type == "增长":
                plt.text(bar.get_x() + bar.get_width() / 2., height + max(ranking.values) * 0.01,
                         f'{height:+.1f}%', ha='center', va='bottom', fontsize=10)
            else:
                plt.text(bar.get_x() + bar.get_width() / 2., height + max(ranking.values) * 0.01,
                         f'{int(height):,}', ha='center', va='bottom', fontsize=10)

        plt.grid(True, alpha=0.3, axis='y')
        plt.tight_layout()

        # 转换为Base64
        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        plt.close()
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')

        # 生成报告
        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h3>🏆 {rank_type}销量排行榜（Top {n}）</h3>

            <div style="margin: 20px 0;">
                <img src="data:image/png;base64,{img_b64}" style="max-width:100%; border: 1px solid #ddd; border-radius: 8px;">
            </div>

            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
                <h4 style="margin-top: 0;">📋 详细排名</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #e9ecef;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">排名</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">{rank_type}</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">{'增长率' if rank_type == '增长' else '总销量'}</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">市场表现</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for i, (item, value) in enumerate(ranking.items(), 1):
            if rank_type == "增长":
                value_str = f"{value:+.1f}%"
                if value > 10:
                    performance = "🚀 高速增长"
                    color = "#27ae60"
                elif value > 0:
                    performance = "📈 稳定增长"
                    color = "#2ecc71"
                else:
                    performance = "⚠️ 需要关注"
                    color = "#e74c3c"
            else:
                value_str = f"{int(value):,} 件"
                if i == 1:
                    performance = "🥇 市场领先"
                    color = "#f39c12"
                elif i <= 3:
                    performance = "🥈 表现优秀"
                    color = "#3498db"
                else:
                    performance = "📊 良好"
                    color = "#95a5a6"

            html += f"""
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">
                                <div style="display: inline-block; width: 24px; height: 24px; background: #e74c3c; color: white; text-align: center; line-height: 24px; border-radius: 50%;">{i}</div>
                            </td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold;">{item}</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold;">{value_str}</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; color: {color};">{performance}</td>
                        </tr>
            """

        html += """
                    </tbody>
                </table>
            </div>

            <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin-top: 20px;">
                <h5 style="margin-top: 0;">💡 运营洞察</h5>
        """

        if rank_type == "IP":
            if n >= 2:
                first = ranking.iloc[0]
                second = ranking.iloc[1]
                advantage = ((first - second) / second) * 100
                html += f"""
                <ul>
                    <li><b>市场集中度：</b>Top {n} IP占总销量的 {(ranking.sum() / df['sales'].sum() * 100):.1f}%</li>
                    <li><b>领先优势：</b>第一名领先第二名 {advantage:.1f}%</li>
                    <li><b>机会点：</b>关注排名靠后的IP，分析提升空间</li>
                </ul>
                """
        elif rank_type == "区域":
            html += f"""
                <ul>
                    <li><b>区域分布：</b>Top {n} 区域销量占比 {(ranking.sum() / df['sales'].sum() * 100):.1f}%</li>
                    <li><b>市场机会：</b>分析低排名区域的提升策略</li>
                    <li><b>资源调配：</b>根据区域表现优化库存和营销资源分配</li>
                </ul>
            """
        elif rank_type == "增长":
            fastest = ranking.index[0]
            fastest_growth = ranking.iloc[0]
            html += f"""
                <ul>
                    <li><b>增长明星：</b>{fastest} 增长最快 ({fastest_growth:+.1f}%)</li>
                    <li><b>增长动力：</b>分析高增长IP的成功因素</li>
                    <li><b>风险预警：</b>关注负增长IP，及时制定应对策略</li>
                </ul>
            """

        html += """
            </div>
        </div>
        """

        return html

    # ==================== 4. 预测查询 ====================
    predict_keywords = ["预测", "未来", "下周", "下个月", "预计", "趋势"]
    if any(keyword in query for keyword in predict_keywords):
        # 提取IP和区域
        found_ip = next((ip for ip in IPS if ip in query), None)
        found_region = next((region for region in REGIONS if region in query), None)

        if not found_ip:
            # 如果没有指定IP，使用最受欢迎的IP
            found_ip = df.groupby('ip')['sales'].sum().idxmax()

        # 执行预测
        forecast_info, error = simple_forecast(found_ip, found_region)

        if error:
            return f"""
            <div style="color: #e74c3c;">
                ❌ {error}
                <br>请尝试其他分析功能。
            </div>
            """

        # 生成预测图表
        img_b64 = generate_forecast_chart(found_ip, found_region, forecast_info)

        # 生成报告
        region_text = f"在{found_region}" if found_region else "在全国"

        html = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h3>🔮 {found_ip}{region_text}销量预测</h3>

            <div style="background: #f0f8ff; padding: 15px; border-radius: 8px; margin: 15px 0;">
            <h4 style="margin-top: 0; color: #000000 !important;">📊 预测概览</h4>
                <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px;">
                    <div style="background: white; padding: 15px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="font-size: 12px; color: #666;">预测日均销量</div>
                        <div style="font-size: 24px; font-weight: bold; color: #2c3e50;">{forecast_info['avg']:.1f} 件</div>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="font-size: 12px; color: #666;">未来趋势</div>
                        <div style="font-size: 24px; font-weight: bold; color: {'#27ae60' if forecast_info['trend'] == '上升' else ('#e74c3c' if forecast_info['trend'] == '下降' else '#f39c12')};">{forecast_info['trend']}</div>
                    </div>
                    <div style="background: white; padding: 15px; border-radius: 6px; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                        <div style="font-size: 12px; color: #666;">预测置信度</div>
                        <div style="font-size: 24px; font-weight: bold; color: #2c3e50;">{forecast_info['confidence']:.0f}%</div>
                    </div>
                </div>
            </div>

            <div style="margin: 20px 0;">
                <img src="data:image/png;base64,{img_b64}" style="max-width:100%; border: 1px solid #ddd; border-radius: 8px;">
            </div>

            <div style="background: #f8f9fa; padding: 15px; border-radius: 8px;">
                <h4 style="margin-top: 0;">📈 未来7天详细预测</h4>
                <table style="width: 100%; border-collapse: collapse;">
                    <thead>
                        <tr style="background: #e9ecef;">
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">预测日期</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">预计销量</th>
                            <th style="padding: 10px; text-align: left; border-bottom: 2px solid #dee2e6;">波动范围</th>
                        </tr>
                    </thead>
                    <tbody>
        """

        for i, value in enumerate(forecast_info['values'], 1):
            lower = value * 0.9
            upper = value * 1.1

            html += f"""
                        <tr>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6;">第{i}天</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; font-weight: bold;">{value:.1f} 件</td>
                            <td style="padding: 10px; border-bottom: 1px solid #dee2e6; color: #666;">{lower:.1f} ~ {upper:.1f} 件</td>
                        </tr>
            """

        html += f"""
                    </tbody>
                </table>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin: 20px 0;">
                <div style="background: #e8f5e8; padding: 15px; border-radius: 8px;">
                    <h5 style="margin-top: 0;">📝 预测说明</h5>
                    <ul>
                        <li>基于历史销量数据的趋势分析</li>
                        <li>使用移动平均、加权平均和趋势外推综合预测</li>
                        <li>预测置信度：{forecast_info['confidence']:.0f}%</li>
                        <li>实际销量可能受促销、天气等因素影响</li>
                    </ul>
                </div>

                <div style="background: #e3f2fd; padding: 15px; border-radius: 8px;">
                    <h5 style="margin-top: 0;">🎯 行动建议</h5>
                    <ul>
        """

        if forecast_info['trend'] == "上升":
            html += f"""
                        <li>📈 {found_ip}处于上升趋势，建议加大备货</li>
                        <li>🎯 抓住增长机会，加强相关营销活动</li>
                        <li>📊 密切监控实际销量，及时调整策略</li>
            """
        elif forecast_info['trend'] == "下降":
            html += f"""
                        <li>⚠️ {found_ip}呈下降趋势，建议分析原因</li>
                        <li>🔍 检查库存、竞品和用户反馈</li>
                        <li>🔄 考虑调整定价或推出促销活动</li>
            """
        else:
            html += f"""
                        <li>📊 {found_ip}趋势平稳，建议维持现状</li>
                        <li>💡 可尝试营销创新或捆绑销售</li>
                        <li>🎁 考虑会员专享活动提升销量</li>
            """

        html += """
                    </ul>
                </div>
            </div>

            <div style="background: #fff3e0; padding: 15px; border-radius: 8px; margin-top: 20px; font-size: 14px; color: #666;">
                <p>💡 <b>温馨提示：</b>销量预测基于历史数据统计模型，实际结果可能受多种因素影响。建议结合市场动态和业务经验综合判断。</p>
            </div>
        </div>
        """

        return html

    # ==================== 5. IP+区域查询（原始功能） ====================
    found_ip = next((ip for ip in IPS if ip in query), None)
    found_region = next((region for region in REGIONS if region in query), None)

    if found_ip and found_region:
        sub_df = df[(df['ip'] == found_ip) & (df['region'] == found_region)]
        if sub_df.empty:
            return f"""
            <div style="font-family: Arial, sans-serif; color: #e74c3c;">
                ❌ 未找到 <b>{found_ip}</b> 在 <b>{found_region}</b> 的销售记录。
                <br>请确认 IP 名称或区域名称是否正确。
            </div>
            """

        total_sales = sub_df['sales'].sum()
        avg_daily = sub_df['sales'].mean()
        last_7_days = sub_df.tail(7)['sales'].tolist()
        week1 = sub_df.tail(14).head(7)['sales'].sum()
        week2 = sub_df.tail(7)['sales'].sum()
        weekly_change = ((week2 - week1) / week1 * 100) if week1 > 0 else 0

        # 趋势判断
        if weekly_change > 5:
            trend = "📈 上升"
            trend_color = "#27ae60"
        elif weekly_change < -5:
            trend = "📉 下降"
            trend_color = "#e74c3c"
        else:
            trend = "➡️ 稳定"
            trend_color = "#f39c12"

        # 生成趋势图
        plt.figure(figsize=(7, 3.5))
        plt.plot(sub_df['date'].tail(14), sub_df['sales'].tail(14), marker='o', linewidth=2, markersize=4)
        plt.title(f"{found_ip} 在 {found_region} 近14天销量趋势", fontsize=12)
        plt.xlabel("日期", fontsize=9)
        plt.ylabel("销量（件）", fontsize=9)
        plt.xticks(rotation=45, fontsize=8)
        plt.yticks(fontsize=8)
        plt.grid(True, linestyle='--', alpha=0.5)
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png', dpi=150)
        plt.close()
        buf.seek(0)
        img_b64 = base64.b64encode(buf.read()).decode('utf-8')
        img_html = f'<img src="data:image/png;base64,{img_b64}" style="max-width:100%; border: 1px solid #eee; border-radius: 6px;">'

        # 检查是否有相关异常
        related_anomalies = []
        all_anomalies = detect_anomalies()
        for anomaly in all_anomalies:
            if found_ip in anomaly or found_region in anomaly:
                related_anomalies.append(anomaly)

        analysis = f"""
        <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
            <h3>📊 {found_ip} 在 {found_region} 销售深度分析</h3>
        """

        if related_anomalies:
            analysis += f"""
            <div style="background: #fff3cd; padding: 10px; border-radius: 5px; margin: 10px 0; border-left: 4px solid #ffc107;">
                <strong>⚠️ 相关异常预警：</strong>
                <ul style="margin-bottom: 0;">
                    {''.join(f'<li>{anomaly}</li>' for anomaly in related_anomalies)}
                </ul>
            </div>
            """

        analysis += f"""
            <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin: 20px 0;">
                <div style="background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <div style="font-size: 14px; color: #666; margin-bottom: 5px;">总销量</div>
                    <div style="font-size: 28px; font-weight: bold; color: #2c3e50;">{total_sales:,} 件</div>
                </div>
                <div style="background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <div style="font-size: 14px; color: #666; margin-bottom: 5px;">日均销量</div>
                    <div style="font-size: 28px; font-weight: bold; color: #2c3e50;">{avg_daily:.1f} 件</div>
                </div>
                <div style="background: white; padding: 15px; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <div style="font-size: 14px; color: #666; margin-bottom: 5px;">周环比变化</div>
                    <div style="font-size: 28px; font-weight: bold; color: {trend_color};">{weekly_change:+.1f}%</div>
                    <div style="font-size: 12px; color: #666;">{trend}</div>
                </div>
            </div>

            <p><b>最近7天销量：</b>{last_7_days}</p>

            <h4>📈 近14天销量趋势图</h4>
            {img_html}

            <div style="margin-top: 25px; padding-top: 20px; border-top: 1px solid #eee;">
                <h4>💡 分析解读与建议</h4>

                <p><b>趋势解读：</b>
                {'近期销量呈明显上升趋势，用户对该IP的接受度正在提高。' if weekly_change > 5 else
        '销量出现下滑，可能受到竞品、库存或用户偏好变化的影响。' if weekly_change < -5 else
        '销量保持平稳，市场表现稳定，用户基础牢固。'}
                </p>

                <p><b>运营建议：</b></p>
                <ul>
                    {'<li>加大备货量，满足增长需求</li>' if weekly_change > 5 else ''}
                    {'<li>推出促销活动，刺激销量回升</li>' if weekly_change < -5 else ''}
                    {'<li>尝试推出新款式或联名款，测试市场反应</li>' if -5 <= weekly_change <= 5 else ''}
                    <li>关注用户反馈，了解产品满意度</li>
                    <li>分析竞品动态，保持市场竞争力</li>
                    <li>优化店内陈列，提升产品可见度</li>
                </ul>

                <div style="background: #f8f9fa; padding: 15px; border-radius: 8px; margin-top: 15px;">
                    <p><b>📊 数据质量：</b>基于{len(sub_df)}条销售记录分析，数据覆盖{sub_df['date'].min().strftime('%Y-%m-%d')}至{sub_df['date'].max().strftime('%Y-%m-%d')}。</p>
                </div>
            </div>
        </div>
        """
        return analysis

    # ==================== 6. 默认回答（更友好的提示） ====================
    suggestions = get_smart_suggestions(user_id)

    # 构建suggestions的HTML部分
    suggestions_html = ""
    for suggestion in suggestions:
        suggestions_html += f"""
                <div style="background: white; padding: 8px 12px; border-radius: 6px; border: 1px solid #bbdefb;">
                    {suggestion}
                </div>
        """

    # 一次性返回完整的HTML
    return f"""
    <div style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
        <h3>🤔 我理解了您的查询，但需要更明确的信息</h3>
        <p>您的问题：<b>"{query}"</b></p>

        <div style="background: #f8f9fa; padding: 20px; border-radius: 8px; margin: 20px 0;">
            <h4 style="margin-top: 0;">💡 我能为您分析什么？</h4>
            <p>请尝试以下任一方式提问：</p>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-top: 15px;">
                <div>
                    <h5>📅 时间分析</h5>
                    <ul style="margin-top: 10px;">
                        <li>"昨天销量如何？"</li>
                        <li>"最近7天趋势"</li>
                        <li>"本月销售报告"</li>
                    </ul>
                </div>

                <div>
                    <h5>🔄 对比分析</h5>
                    <ul style="margin-top: 10px;">
                        <li>"Molly和Dimoo哪个卖得好？"</li>
                        <li>"华东 vs 华南"</li>
                        <li>"对比一下热门IP"</li>
                    </ul>
                </div>

                <div>
                    <h5>🏆 排名分析</h5>
                    <ul style="margin-top: 10px;">
                        <li>"销量前3名"</li>
                        <li>"增长最快的IP"</li>
                        <li>"区域排名"</li>
                    </ul>
                </div>

                <div>
                    <h5>🔮 预测分析</h5>
                    <ul style="margin-top: 10px;">
                        <li>"预测Molly下周销量"</li>
                        <li>"Dimoo未来趋势"</li>
                        <li>"销售预测"</li>
                    </ul>
                </div>
            </div>
        </div>

        <div style="background: #e3f2fd; padding: 15px; border-radius: 8px;">
            <h5 style="margin-top: 0;">🎯 智能推荐问题（基于数据热点）</h5>
            <div style="display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px;">
                {suggestions_html}
            </div>
        </div>

        <div style="margin-top: 25px; padding-top: 15px; border-top: 1px solid #eee; font-size: 14px; color: #000000;">
            <p>💡 <b>使用技巧：</b></p>
            <ul>
                <li>包含具体的IP名称（如Molly、Dimoo）</li>
                <li>指定区域（如华东、华南）</li>
                <li>明确时间范围（如昨天、最近7天）</li>
                <li>使用对比词汇（如vs、对比、哪个更好）</li>
            </ul>
        </div>
    </div>
    """


# ==============================
# 7> 创建 Gradio 界面
# ==============================

# 创建一个新的函数来处理文件和查询
def analyze_with_file(file, query):
    global df, IPS, REGIONS

    # 如果有文件上传，加载数据
    if file is not None:
        try:
            # 读取Excel文件
            df = pd.read_excel(file)
            df['date'] = pd.to_datetime(df['date'])

            # 从数据中提取IP和区域列表
            if 'ip' in df.columns:
                IPS = sorted(df['ip'].dropna().unique().tolist())
            if 'region' in df.columns:
                REGIONS = sorted(df['region'].dropna().unique().tolist())

            print(f"✅ 数据加载成功，共 {len(df)} 条记录")
        except Exception as e:
            return f"""
            <div style="font-family: Arial, sans-serif; padding: 20px; background: #fee; border-radius: 8px; border-left: 4px solid #e74c3c;">
                <h3 style="color: #e74c3c; margin-top: 0;">❌ 数据加载失败</h3>
                <p><b>错误原因：</b> {str(e)}</p>
                <p><b>请检查：</b></p>
                <ul>
                    <li>文件是否为 .xlsx 或 .xls 格式</li>
                    <li>文件是否包含 date, ip, region, sales 列</li>
                    <li>日期列是否为标准格式（如2024-01-01）</li>
                    <li>文件是否被其他程序占用</li>
                </ul>
                <p style="color: #666; font-size: 14px; margin-top: 15px;">
                    💡 提示：请确保Excel文件格式符合要求，再重新上传
                </p>
            </div>
            """

    # 检查数据是否已加载
    if df is None:
        return """
        <div style="font-family: Arial, sans-serif; text-align: center; padding: 50px;">
            <h3>📁 请先上传数据文件</h3>
            <p>请上传泡泡玛特销售数据的Excel文件</p>
            <p style="color: #666; margin-top: 20px;">💡 支持 .xlsx 和 .xls 格式</p>
        </div>
        """

    # 调用原来的analyze函数
    return analyze(query, "default")


# 保持原有界面完全不变，只增加一个文件上传输入
demo = gr.Interface(
    fn=analyze_with_file,
    inputs=[
        gr.File(
            label="📁 上传数据文件",
            file_types=[".xlsx", ".xls"],
            type="filepath",
             height = 120,
        ),
        gr.Textbox(
            label="💬 请输入您的销售分析问题",
            placeholder="例如：昨天销量如何？对比Molly和Dimoo？预测下周销量？",
            lines=3
        )
    ],
    outputs=gr.HTML(label="📊 AI 深度分析报告"),
    title="🤖 泡泡玛特销售分析助手",
    description="""
    <div style="text-align: center; color: black; font-size: 14px; margin-top: 8px;">
    ✨ 支持时间分析、对比分析、排名查询、销量预测、异常检测
    </div>
    """,
    examples=[
        [None, "昨天销量如何？"],
        [None, "Molly和Dimoo哪个卖得好？"],
        [None, "预测Molly下周销量"],
        [None, "销量前3名"],
        [None, "最近7天销售趋势"],
        [None, "华东 vs 华南对比分析"]
    ]
)

# ==============================
# 8> 启动服务
# ==============================
if __name__ == "__main__":
    import subprocess
    import time
    import webbrowser
    import socket
    from contextlib import closing

    def check_port(port):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            try:
                sock.bind(('0.0.0.0', port))
                return True
            except:
                return False
    port = 7860
    while not check_port(port):
        port += 1
        if port > 7960:  # 设置一个上限，避免无限循环
            print("端口范围7860-7960都被占用，请关闭其他程序")
            exit(1)

    url = f"http://localhost:{port}"  # 改成localhost，更友好

    print("=" * 60)
    print("🤖 泡泡玛特销售分析助手")
    print("=" * 60)
    print(f"🌐 服务地址：{url}")
    print("=" * 60)
    print("📁 使用说明：")
    print("1. 上传Excel销售数据文件")
    print("2. 输入分析问题")
    print("3. 查看分析报告")
    print("=" * 60)

    def open_edge():
        time.sleep(2)
        edge_path = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

        if os.path.exists(edge_path):
            try:
                subprocess.Popen([edge_path, url])
                print("✅ 已自动用 Microsoft Edge 打开")
            except Exception as e:
                print(f"⚠️ 自动打开 Edge 失败: {e}")
                webbrowser.open(url)
        else:
            print("❌ Edge 浏览器未找到，请手动打开:", url)

    import threading
    browser_thread = threading.Thread(target=open_edge, daemon=True)
    browser_thread.start()

    demo.launch(
        server_name="0.0.0.0",
        server_port=port,
        inbrowser=False,
        share=False,
        show_error=True,
        css="""
        /*1. 修改主界面背景色 */
         /* 修改主界面背景色 */
        .gradio-container {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        padding: 20px !important;
        min-height: 100vh !important;
        }

/* 2. 主容器调整为浅灰色，增加层次感 */
.gradio-container > div {
    background-color: #f8f9fa !important; /* 非常浅的灰 */
    border-radius: 12px !important;
    box-shadow: 0 5px 20px rgba(0, 0, 0, 0.05) !important; /* 更柔和的阴影 */
}

/* 3. 输出框样式优化 */
.gradio-container .html-container .prose {
    background-color: #5972aa !important;  /* 改为蓝色背景 */
    border: 1px solid #e2e8f0 !important;   /* 柔和的边框 */
    border-radius: 8px !important;
    padding: 24px !important;
    color: #2d3748 !important;  /* 改为深蓝灰色文字 */
    line-height: 1.6 !important;  /* 增加行高，提高可读性 */
    box-shadow: 0 2px 12px rgba(0, 0, 0, 0.04) !important;  /* 轻微阴影 */
}

/* 覆盖内联样式 */
.gradio-container .html-container .prose > div[style*="font-family"] {
    color: #ffffff !important;  /* 强制覆盖内联颜色 */
    font-family: Arial, sans-serif !important;
    line-height: 1.6 !important;
}

/* 输出框标题样式 */
.gradio-container .html-container .prose h3 {
    color: #ffffff !important;  /* 输出框标题颜色 */
    border-bottom: 2px solid #e2e8f0 !important;
    padding-bottom: 8px !important;
    margin-top: 0px !important;
}

/* 新增：错误提示的h3标题特殊处理，保持红色 */
.gradio-container .html-container .prose div[style*="background: #fee"] h3,
.gradio-container .html-container .prose div[style*="border-left: 4px solid #e74c3c"] h3 {
    color: #e74c3c !important;
    border-bottom: none !important;  /* 去掉下划线 */
    padding-bottom: 0 !important;    /* 去掉内边距 */
}
.gradio-container .html-container .prose h4,
.gradio-container .html-container .prose h5 {
    color: #212529 !important;
}
/* 但为智能推荐标题添加例外 */
.gradio-container .html-container .prose h4:first-child {
    color: white !important;  /* 让第一个h4显示为白色 */
}

/* 输出框标题横线下方文字 */
.gradio-container .html-container .prose p {
    color: #000000 !important;
    margin: 12px 0 !important;
}

/* 表格样式 */
.gradio-container .html-container .prose table {
    border: 1px solid #e2e8f0 !important;
    border-radius: 6px !important;
    overflow: hidden !important;
    margin: 16px 0 !important;
}

.gradio-container .html-container .prose th {
    background-color: #edf2f7 !important;
    color: #2d3748 !important;
    font-weight: 600 !important;
    padding: 12px 16px !important;
}

.gradio-container .html-container .prose td {
    background-color: white !important;
    color: #4b5563 !important;  /* 表格内容用中灰色 */
    padding: 10px 16px !important;
    border-top: 1px solid #e2e8f0 !important;
}

/* 核心结论框样式（背景区域） */
.gradio-container .html-container .prose div[style*="background: #d4edda"] {
    background-color: #ffffff !important;  /* 保持白色背景 */
    color: #c29d59 !important;  /* 金色文字 */
    padding: 15px !important;
    border-radius: 8px !important;
    margin-top: 20px !important;
}
/*核心结论标题字体红色*/
.gradio-container .html-container .prose div[style*="background: #d4edda"] h5 {
    color: #d62828 !important;
}

/*核心结论字体颜色*/
.gradio-container .html-container .prose div[style*="background: #d4edda"] p,
.gradio-container .html-container .prose div[style*="background: #d4edda"] li {
    color: #000000 !important;
}

/* 分析结果框样式（浅灰色背景区域） */
.gradio-container .html-container .prose div[style*="background: #f8f9fa"] {
    background-color: #f8f9fa !important;  /* 保持浅灰色背景 */
    color: #212529 !important;  /* 深灰色文字 */
    padding: 15px !important;
    border-radius: 8px !important;
    margin: 15px 0 !important;
}

.gradio-container .html-container .prose div[style*="background: #f8f9fa"] h4 {
    color: #212529 !important;
}

/* 列表样式 */
.gradio-container .html-container .prose ul,
.gradio-container .html-container .prose ol {
    color: #2d3748 !important;
    margin: 8px 0 !important;
}

.gradio-container .html-container .prose li {
    margin: 6px 0 !important;
    color: #000000 !important;
}

/* 粗体文字颜色 */
.gradio-container .html-container .prose b,
.gradio-container .html-container .prose strong {
    color: #c29d59 !important;
}

/* 4. 标题改为黑色*/
.gradio-container h1 {
    color: #000000 !important;
    font-weight: 700 !important;
}

/* 5. 按钮样式为黑白基础色，用紫色渐变同色系作为交互色 */
button.gallery-item {
    background-color: #ffffff !important; /* 白底 */
    color: #000000 !important; /* 黑字 */
    border: 1px solid #dee2e6 !important; /* 浅灰边框 */
    border-radius: 6px !important; /* 圆角调小 */
    padding: 6px 12px !important; /* 内边距调小 */
    margin: 4px !important;
    font-size: 13px !important; /* 字体 */
    cursor: pointer !important;
    transition: all 0.3s ease !important;
    min-height: unset !important;
    height: auto !important;
}

button.gallery-item:hover {
    background-color: #764ba2 !important; /* 悬停时变为与背景渐变一致的紫色 */
    color: #ffffff !important; /* 白色字 */
    border-color: #764ba2 !important;
    transform: translateY(-2px) !important; 
    box-shadow: 0 4px 12px rgba(118, 75, 162, 0.3) !important;
}

/* 6. 各级标题和表格文字使用黑色系，确保可读性 */
.gradio-container .output-html h3,
.gradio-container .output-html h4,
.gradio-container .output-html h5 {
    color: #000000 !important; /* 黑色 */
}

.gradio-container .output-html table td {
    color: #003049 !important;
}

/* 精准定位到 Examples 的标签，将文字设为黑色 */
.gradio-container .label {
    color: #000000 !important;
}

/* 温馨提示文字颜色修改 */
 #html-0xmi0svi3 > div > div:nth-child(6) > p,
 .gradio-container .html-container .prose div[style*="background: #fff3cd"] p {
     color: #000000 !important;
 }
        """

    )


