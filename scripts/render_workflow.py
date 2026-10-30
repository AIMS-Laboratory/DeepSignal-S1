"""Render the small workflow as ordinary images, without GitHub Mermaid loading."""
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
from plot_homepage_results import ROOT, style


def render(language):
    style(language)
    zh = language == 'zh'
    labels = ([('输入', '连续三帧画面', '路口信息 + 当前信号状态'),
               ('DeepSignal S1', '选择合法控制动作', '返回动作及候选概率'),
               ('信号执行器', '执行信号转换', '绿灯尾段 → 黄灯 → 全红')]
              if zh else
              [('Input', 'Three temporal frames', 'Intersection info + signal state'),
               ('DeepSignal S1', 'Select a legal control action', 'Return action + probabilities'),
               ('Signal executor', 'Execute signal transitions', 'Green tail → yellow → all-red')])
    fig, ax = plt.subplots(figsize=(12, 2.15), dpi=140)
    fig.subplots_adjust(left=0, right=1, bottom=0, top=1)
    fig.patch.set_facecolor('white')
    ax.set(xlim=(0, 1200), ylim=(0, 215))
    ax.axis('off')
    for i, (title, line1, line2) in enumerate(labels):
        x = 14 + i * 402
        ax.add_patch(FancyBboxPatch((x, 28), 368, 160, boxstyle='round,pad=0,rounding_size=12',
                                   linewidth=0, facecolor=('#E9F6F4', '#EDF2FC', '#F3EDF9')[i]))
        for y, text, size, color in [(150, title, 17, '#132E41'), (108, line1, 14, '#243F50'),
                                     (72, line2, 12, '#526577')]:
            ax.text(x + 184, y, text, ha='center', va='center', fontsize=size, color=color)
        if i < 2:
            ax.add_patch(FancyArrowPatch((x + 373, 108), (x + 397, 108),
                                        arrowstyle='-|>', mutation_scale=15, color='#526577', linewidth=1.5))
    fig.savefig(ROOT / 'assets/highlights' / f's1-workflow-{language}.png', facecolor='white')
    plt.close(fig)


if __name__ == '__main__':
    for language in ('en', 'zh'):
        render(language)
