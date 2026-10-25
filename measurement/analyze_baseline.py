"""Summarize a completed paired capture without changing its raw evidence."""
import argparse
from collections import Counter
import csv
import json
import math
from pathlib import Path
import statistics


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def interval_summary(ticks, frequency):
    gaps = [(b-a)*1000/frequency for a,b in zip(ticks,ticks[1:])]
    return {'median_ms':statistics.median(gaps) if gaps else None,
            'p95_ms':sorted(gaps)[int((len(gaps)-1)*.95)] if gaps else None}


def summarize(points, request):
    start, frequency = request['start_qpc'], request['qpc_frequency']
    axes = {}
    for key in ('lx','ly','rx','ry','lt','rt'):
        values = sorted({r[key] for r in points})
        steps = [b-a for a,b in zip(values,values[1:])]
        axes[key] = {'unique':len(values),'min':min(values) if values else None,
                     'max':max(values) if values else None,
                     'observed_step_gcd':math.gcd(*steps),
                     'common_adjacent_steps':Counter(steps).most_common(5)}
    changes = []
    previous = None
    for row in points:
        current = tuple(row[key] for key in ('lx','ly','rx','ry'))
        if previous is not None and current != previous:
            changes.append(row['qpc_ticks'])
        previous = current
    phases = {}
    for name,lo,hi in [('left_sweeps',10,30),('right_sweeps',30,50),('circles',50,70)]:
        ticks = [t for t in changes if lo <= (t-start)/frequency < hi]
        phases[name] = {'fresh_stick_changes':len(ticks),
                        'changes_per_second':len(ticks)/(hi-lo),
                        **interval_summary(ticks,frequency)}
    return {'rows':len(points),'axes':axes,'moving_phases':phases}


def xinput_points(path, slot):
    with path.open(newline='') as stream:
        return [{k:int(v) for k,v in row.items() if k != 'event'}
                for row in csv.DictReader(stream)
                if row['connected'] == '1' and int(row['slot']) == slot]


def hid_points(folder, context):
    matches = [d for d in context['devices'] if d.get('caps',{}).get('UsagePage') == 1
               and d['caps']['Usage'] in (4,5)]
    if len(matches) != 1 or matches[0]['vid'] != '2dc8' or matches[0]['pid'] != '6012':
        raise ValueError('Native HID decoder requires the measured 2DC8:6012 profile')
    device = matches[0]
    if device['caps']['InputReportByteLength'] != 34:
        raise ValueError('Unexpected native HID report size')
    axis_caps = [v for v in device['value_caps'] if v['usage_page'] == 1
                 and v['usage_min'] in (48,49,50,53)]
    if len(axis_caps) != 4 or any(v['bit_size'] != 8 or v['logical_min'] != 0
                                or v['logical_max'] != 255 for v in axis_caps):
        raise ValueError('Native HID axis declaration differs from the measured byte profile')
    points = []
    with (folder/'windows-hid.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            raw = bytes.fromhex(row['report_hex'])
            if len(raw) != 34 or raw[0] != 1:
                raise ValueError('Unexpected native HID report; do not assume its axis layout')
            points.append(dict(qpc_ticks=int(row['qpc_ticks']),lx=raw[2],ly=raw[3],
                               rx=raw[4],ry=raw[5],rt=raw[6],lt=raw[7]))
    return points


def analyze(folder):
    request = read_json(folder/'request.json')
    steam = read_json(folder/'steam-summary.json')
    windows = read_json(folder/'windows-summary.json')
    context = read_json(folder/'windows-context.json')
    if steam['outcome'] != 'complete' or windows['outcome'] != 'finished':
        raise ValueError('Both sides must have completed before baseline analysis')
    operator = read_json(folder/'operator-note.json') if (folder/'operator-note.json').exists() else {}
    focus = steam['foreground_matches']/steam['foreground_checks'] if steam['foreground_checks'] else 0
    steam_slots = [s['slot'] for s in steam['slots'] if s['initially_connected']]
    if len(steam_slots) != 1:
        raise ValueError('Expected exactly one Steam-facing slot')
    result = {'condition':operator.get('corrected_condition',request['condition']),
              'repetition':operator.get('corrected_repetition',request['repetition']),
              'recorded_condition_label':request['condition'],
              'recorded_repetition_label':request['repetition'],
              'duration_seconds':steam['seconds'],'foreground_fraction':focus,
              'steam_sampler_hz':steam['sampler_iterations']/steam['seconds'],
              'windows_attach_delay_ms':(windows['capture_start_qpc']-request['start_qpc'])*1000/request['qpc_frequency'],
              'disconnects':sum(s['disconnects'] for s in steam['slots']),
              'operator_excluded':operator.get('include_in_baseline') is False,
              'steam_slot':steam_slots[0],
              'steam':summarize(xinput_points(folder/'steam-output.csv',steam_slots[0]),request),
              'limitations':'Distinct output codes do not establish ADC bit depth or sensor accuracy. Changed-state rates depend on movement, host sampling and scheduling; they are not physical latency or unconditional polling-rate measurements.'}
    if windows['source'] == 'xinput':
        result['windows_slot'] = windows['slot']
        result['windows'] = summarize(xinput_points(folder/'windows-xinput.csv',windows['slot']),request)
        result['windows_api_sampler_hz'] = windows['sampler_calls']/windows['capture_elapsed_seconds']
    else:
        points = hid_points(folder,context)
        result['windows'] = summarize(points,request)
        ticks = [p['qpc_ticks'] for p in points]
        result['hid_report_arrivals'] = {'reports':len(ticks),
            'observed_hz':(len(ticks)-1)*request['qpc_frequency']/(ticks[-1]-ticks[0]) if len(ticks)>1 else None,
            **interval_summary(ticks,request['qpc_frequency'])}
    if (folder/'windows-aux-summary.json').exists():
        aux = read_json(folder/'windows-aux-summary.json')
        result['passive_vendor_interface'] = {'outcome':aux['outcome'],'reports':aux['reports'],
            'limitation':'No activation command was sent; silence cannot rule out an enableable stream.'}
    result['basic_quality_pass'] = (focus >= .98 and not result['disconnects']
                                    and not result['operator_excluded'] and result['windows']['rows']>0)
    result['focus_validation'] = read_json(folder/'focus-validation.json') if (folder/'focus-validation.json').exists() else None
    result['moving_phase_comparison_eligible'] = (not result['disconnects'] and not result['operator_excluded']
        and result['windows']['rows']>0 and (focus >= .98 or bool(result['focus_validation']
            and result['focus_validation'].get('moving_phases_foreground_verified'))))
    (folder/'baseline-analysis.json').write_text(json.dumps(result,indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('session',type=Path)
    args = parser.parse_args()
    print(json.dumps(analyze(args.session.resolve()),indent=2))
