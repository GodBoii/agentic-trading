"""Exact-clock private volume preparation then four-date frozen account replay."""

from dataclasses import asdict,replace
from hashlib import sha256
import json
from pathlib import Path

from research.common.data import DATES,DEVELOPMENT,VALIDATION,AUDIT,load_ticks
from research.common.runner import Variant,run_track
from research.intraday_lab.domain import PolicyConfig
from .data import load_volume
from .strategy import completed_bars,fit_baseline,RelativeVolumePolicy


def main() -> None:
    root=Path(__file__).parent
    prep=root/'preparation/initial-v1'
    if prep.exists():
        raise ValueError('choose a new version; do not overwrite preparation')
    prep.mkdir(parents=True)
    frozen={'training_dates':DEVELOPMENT,'evaluation_dates':VALIDATION+AUDIT,
            'continuation_rvol':2,'continuation_move_bps':5,'climax_rvol':3,
            'climax_move_bps':10,'reversal_move_bps':3,'minimum_baseline_days':3,
            'minimum_minute_observations':40,'maximum_start_boundary_age_seconds':2,
            'minimum_end_second':58,'maximum_next_quote_second':62,
            'role':'incremental completed-minute relative volume; not cumulative RDV replication'}
    (prep/'frozen-hypotheses.json').write_text(json.dumps(frozen,indent=2),encoding='utf-8')
    sessions={mode:{} for mode in ('recent_trade','receipt_proxy')}
    reports=[]
    for day in DATES:
        ticks=load_ticks(day)
        volumes,report=load_volume(day,ticks)
        report['bar_admission']={}
        for mode in sessions:
            bars,counts=completed_bars(ticks,volumes,replace(PolicyConfig(),freshness_mode=mode))
            sessions[mode][day]=bars
            report['bar_admission'][mode]=counts
        reports.append(report)
        print(json.dumps({'event':'volume_prepared','date':day,'admission':report['bar_admission']}),flush=True)
    baselines={mode:fit_baseline({day:days[day] for day in DEVELOPMENT}) for mode,days in sessions.items()}
    baseline_payload={mode:[{'security_id':key[0],'minute_of_day':key[1],'mean_volume':value}
                              for key,value in sorted(b.items())]for mode,b in baselines.items()}
    serialized=json.dumps(baseline_payload,sort_keys=True)
    parameters={**frozen,'baseline_sha256':sha256(serialized.encode()).hexdigest(),
                'baseline_cells':{mode:len(b)for mode,b in baselines.items()},
                'private_volume_inputs':reports}
    allbars={mode:[bar for day in VALIDATION+AUDIT for bar in days[day]]for mode,days in sessions.items()}
    variants=[Variant(method,lambda cfg,method=method: RelativeVolumePolicy(
        cfg,allbars[cfg.freshness_mode],baselines[cfg.freshness_mode],method),parameters)
        for method in ('continuation','climax_reversal')]
    output=run_track(root,variants,dates=VALIDATION+AUDIT)
    (output/'frozen-baselines.json').write_text(serialized,encoding='utf-8')
    (output/'volume-normalization.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
