"""Render a lightweight bilingual SVG feature panel from published latency data."""

from html import escape
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def render(data, chinese):
    latency = data['latency']['all_calls']
    mean = f"{latency['mean_ms']:.0f}"
    pct = f"{100 * latency['under_1s_fraction']:.2f}%"
    if chinese:
        title = '视觉直达决策 · 抗干扰 · 快速响应'
        subtitle = 'DeepSignal S1 / 核心创新与特色'
        cards = [
            ('01  模型设计', '画面 → 动作', '同一模型理解画面并选择动作', '连续三帧 + 路口与信号状态', '直接输出合法动作及候选概率'),
            ('02  控制特色', '4 类视觉干扰', '失焦 · 模糊 · 偏移 · 抖动', '两组仿真场景的已测条件下', '等待、排队、行程均优于 YOLO+MP'),
            ('03  响应速度', mean + ' ms', '未量化模型的平均请求耗时', f"{latency['count']:,} 次 RTX 5090 请求", pct + ' 的请求低于 1 秒'),
        ]
        scope = '受控仿真结果；延迟仅指模型请求。BF16 / RTX 5090；完整比较与测试条件见下文。'
    else:
        title = 'Direct decisions. Robust control. Fast response.'
        subtitle = 'DeepSignal S1 / Design and strengths'
        cards = [
            ('01  MODEL DESIGN', 'Vision → action', 'One model interprets and decides', 'Three frames + intersection/signal state', 'Legal actions and candidate probabilities'),
            ('02  CONTROL', '4 perturbations', 'Defocus · blur · shift · shake', 'Lower wait, queues and journey time', 'vs YOLO+MP in both tested scenes'),
            ('03  RESPONSE', mean + ' ms', 'Mean unquantized model-request time', f"{latency['count']:,} RTX 5090 requests", pct + ' of requests under 1 second'),
        ]
        scope = 'Controlled simulation; model-request latency only. BF16 / RTX 5090. Full comparisons and conditions below.'
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 415" role="img" aria-labelledby="title desc">',
             f'<title id="title">{escape(title)}</title><desc id="desc">{escape(scope)}</desc>',
             '<rect width="1200" height="415" rx="18" fill="#F5F8FB"/>',
             '<g font-family="Arial, PingFang SC, Microsoft YaHei, sans-serif">',
             f'<text x="30" y="39" font-size="17" fill="#526577">{escape(subtitle)}</text>',
             f'<text x="30" y="85" font-size="34" font-weight="700" fill="#132E41">{escape(title)}</text>']
    for i, (label, key, desc, line1, line2) in enumerate(cards):
        x = 30 + i * 390
        color = ('#087F8C', '#315CA8', '#6E4AA2')[i]
        fill = ('#E9F6F4', '#EDF2FC', '#F3EDF9')[i]
        parts += [f'<rect x="{x}" y="112" width="360" height="239" rx="12" fill="{fill}"/>',
                  f'<rect x="{x}" y="134" width="4" height="26" rx="2" fill="{color}"/>']
        for y, text, size, weight, ink in [(153,label,17,'700',color), (212,key,42 if i == 2 else 29,'700','#132E41'),
                                         (252,desc,19,'400','#243F50'), (296,line1,17,'400','#526577'), (325,line2,17,'400','#526577')]:
            parts.append(f'<text x="{x+20}" y="{y}" font-size="{size}" font-weight="{weight}" fill="{ink}">{escape(text)}</text>')
    parts += [f'<text x="30" y="387" font-size="17" fill="#526577">{escape(scope)}</text>', '</g></svg>']
    return '\n'.join(parts) + '\n'


def main():
    data = json.loads((ROOT / 'results/fusion-2026-10-30.json').read_text())
    output = ROOT / 'assets/highlights'
    output.mkdir(exist_ok=True)
    for language in ('en', 'zh'):
        (output / f's1-features-{language}.svg').write_text(render(data, language == 'zh'))


if __name__ == '__main__':
    main()
