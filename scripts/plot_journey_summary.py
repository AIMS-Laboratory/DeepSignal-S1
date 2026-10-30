"""Plot all eight published journey reductions, without selecting only a maximum."""

import argparse
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from plot_homepage_results import load_rows, ROOT


def plot(language):
    zh = language == 'zh'
    if zh:
        for candidate in ('/System/Library/Fonts/STHeiti Medium.ttc',):
            if Path(candidate).exists():
                font_manager.fontManager.addfont(candidate)
                plt.rcParams['font.family'] = font_manager.FontProperties(fname=candidate).get_name()
                break
        else:
            plt.rcParams['font.family'] = ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'DejaVu Sans']
    else:
        plt.rcParams['font.family'] = 'DejaVu Sans'
    rows = load_rows(ROOT / 'results/fusion-2026-10-30-traffic.csv')
    fig, ax = plt.subplots(figsize=(10, 5.4), dpi=160)
    fig.subplots_adjust(left=.27, right=.96, top=.76, bottom=.16)
    fig.patch.set_facecolor('#FFFFFF')
    fig.text(.035,.95,'画面受干扰时，行程缩短多少？' if zh else 'Shorter journeys under visual disruption',
             fontsize=19,weight='bold',color='#142C37')
    fig.text(.035,.885,'相对 YOLO+MP 的平均行程降幅 · 越高越好' if zh else
             'Mean journey reduction vs YOLO+MP · Higher is better',fontsize=12,color='#53656F')
    conditions=('df9','mb31','angle15','shake5')
    labels=(['失焦 σ=9','运动模糊 31像素','固定偏角\n偏航±15° / 俯仰±8°','动态抖动 峰值5°'] if zh else
            ['Defocus σ=9','Motion blur 31 px','Fixed camera shift\nyaw ±15° / pitch ±8°','Dynamic shake peak 5°'])
    for scene,offset,color,label in [('nansha',.18,'#147D78','多路口场景 · 9案例/条件' if zh else 'Multi-intersection · 9 cases/condition'),
                                     ('town',-.18,'#6486A9','标准仿真场景 · 5案例/条件' if zh else 'Standard simulation · 5 cases/condition')]:
        vals=[100*(1-rows[(scene,c,'s1')]['mean_journey_s_per_vehicle']/rows[(scene,c,'mp')]['mean_journey_s_per_vehicle']) for c in conditions]
        ys=[3-i+offset for i in range(4)]
        ax.barh(ys,vals,height=.29,color=color,label=label)
        for y,v in zip(ys,vals):
            ax.text(v+1.5,y,f'{v:.2f}%',va='center',fontsize=12,weight='bold',color='#253C48')
    ax.set_yticks([3,2,1,0],labels,fontsize=12)
    ax.set_xlim(0,100)
    ax.set_xticks([0,25,50,75,100],['0%','25%','50%','75%','100%'],fontsize=11,color='#53656F')
    ax.xaxis.grid(True,color='#E5ECEF')
    ax.set_axisbelow(True)
    for spine in ax.spines.values(): spine.set_visible(False)
    ax.tick_params(length=0,pad=8)
    fig.legend(loc='upper left',bbox_to_anchor=(.025,.855),ncol=2,frameon=False,fontsize=10)
    fig.text(.035,.045,'受控仿真；每场景每条件一个种子；YOLO车道区域冻结，不随偏角重新标定。' if zh else
             'Controlled simulation; one seed per scene/condition; frozen YOLO lane regions, no recalibration.',fontsize=10,color='#53656F')
    return fig


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--language',choices=['en','zh'],required=True)
    language=parser.parse_args().language
    fig=plot(language)
    for extension in ('png','svg'):
        output = ROOT/f'assets/results-fusion/journey-summary-{language}.{extension}'
        fig.savefig(output, facecolor='white')
        if extension == 'svg':
            output.write_text('\n'.join(line.rstrip() for line in output.read_text().splitlines()) + '\n')
    plt.close(fig)
