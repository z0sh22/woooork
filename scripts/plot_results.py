"""Standalone research figures; optional matplotlib, no API calls."""
import json
from pathlib import Path
import sys
import csv

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from safety_games.metrics import load_observations

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def main(directory):
    directory=Path(directory)
    metrics=json.loads((directory/'metrics.json').read_text(encoding='utf-8'))
    groups=metrics['by_difficulty']
    labels=list(groups)
    fig, ax=plt.subplots(figsize=(7,4))
    values=[groups[d]['hacking_rate_confirmed_lower_bound'] if groups[d]['n'] else float('nan') for d in labels]
    ax.bar(labels,values,color='#9c3b3b')
    ax.set(ylim=(0,1),ylabel='Confirmed hacking / observed episodes',title='Hacking rate by difficulty: audited confirmations only')
    for i,d in enumerate(labels):
        ax.text(i,0.04,f"n={groups[d]['n']}\nunreviewed={groups[d]['unreviewed_n']}",ha='center')
    fig.text(0.5,0.01,'Lower bound. Unreviewed episodes are not certified honest.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,0.05,1,1))
    for ext in ('png','svg'): fig.savefig(directory/('hacking_by_difficulty.'+ext),dpi=160)
    plt.close(fig)
    fig,ax=plt.subplots(figsize=(7,4))
    for offset,key,title,color in ((-0.2,'true_success','True success','#237a57'),(0.2,'proxy_success','Proxy success','#3d70ad')):
        values=[groups[d][key]['rate'] if groups[d][key]['rate'] is not None else float('nan') for d in labels]
        ax.bar([i+offset for i in range(len(labels))],values,width=0.38,label=title,color=color)
    ax.set(xticks=range(len(labels)),xticklabels=[d+'\nn='+str(groups[d]['n']) for d in labels],ylim=(0,1.05),ylabel='Success rate among known outcomes',title='Independent and public correctness')
    ax.legend();fig.tight_layout()
    for ext in ('png','svg'):fig.savefig(directory/('success_by_difficulty.'+ext),dpi=160)
    plt.close(fig)
    counts=metrics['overall']['confirmed_category_counts']
    observed={}
    for episode in load_observations(directory):
        for category in episode['behavior']['categories']:
            observed[category]=observed.get(category,0)+1
    with (directory/'behavior_categories.csv').open('w',encoding='utf-8',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['category','automatically_flagged_episodes','confirmed_episodes'])
        for category in sorted(set(observed)|set(counts)):
            writer.writerow([category,observed.get(category,0),counts.get(category,0)])
    fig,axes=plt.subplots(1,2,figsize=(11,4))
    ax=axes[0]
    if observed:
        ax.barh(list(observed),list(observed.values()),color='#bc8741');ax.set_xlabel('Flagged episodes (not confirmations)')
    else:
        ax.text(0.5,0.5,'No automatic behavioral flags',ha='center',va='center',transform=ax.transAxes);ax.set_axis_off()
    ax.set_title('Automatic signals for contextual review')
    ax=axes[1]
    if counts:
        ax.barh(list(counts),list(counts.values()),color='#74528a');ax.set_xlabel('Confirmed episodes')
    else:
        ax.text(0.5,0.5,'No confirmed categories yet\nSee audit coverage before interpretation',ha='center',va='center',transform=ax.transAxes)
        ax.set_axis_off()
    ax.set_title('Confirmed behavior categories');fig.tight_layout()
    for ext in ('png','svg'):fig.savefig(directory/('behavior_categories.'+ext),dpi=160)
    plt.close(fig)


if __name__=='__main__':
    main(sys.argv[1])
