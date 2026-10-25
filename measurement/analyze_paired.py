"""Compare native receiver packets with Steam output, with no bridge involved."""
import argparse
import bisect
import csv
import json
from pathlib import Path
import struct

ROOT=Path(__file__).resolve().parent
from analysis_common import load,distribution,cadence


def analyze(folder):
    request=load(folder/'request.json');steam=load(folder/'steam-summary.json');windows=load(folder/'windows-summary.json');context=load(folder/'windows-context.json')
    if request['condition']!='hid-steam-patch' or steam['outcome']!='complete' or windows['outcome']!='finished':raise ValueError('A completed direct-reader paired test is required')
    slots=[s['slot'] for s in steam['slots'] if s['initially_connected']]
    if len(slots)!=1 or context['outside_steam_xinput_slots']:raise ValueError('Expected only one Steam-emulated XInput slot')
    with (folder/'steam-output.csv').open(newline='') as stream:
        output=[{k:int(v) for k,v in r.items()} for r in csv.DictReader(stream) if r['connected']=='1' and int(r['slot'])==slots[0]]
    source=[];bad=0
    with (folder/'windows-hid.csv').open(newline='') as stream:
        for row in csv.DictReader(stream):
            raw=bytes.fromhex(row['report_hex'])
            if len(raw)!=34 or raw[0]!=1:raise ValueError('Unexpected native report')
            words=[struct.unpack_from('<H',raw,off)[0] for off in (11,27,29,31)]
            fine=tuple(32767-v if i%2==0 else v-32768 for i,v in enumerate(words))
            for i,value in enumerate(words):
                high=value>>8;expected=(127 if high==127 else 255-high) if i%2==0 else high
                bad+=raw[i+2]!=expected
            source.append(dict(time=int(row['qpc_ticks']),raw=raw,axes=fine))
    start=request['start_qpc'];frequency=request['qpc_frequency']
    result=dict(condition=request['condition'],seconds=steam['seconds'],foreground_fraction=steam['foreground_matches']/steam['foreground_checks'],
                physical_reports=len(source),physical_arrivals=cadence([s['time'] for s in source],frequency),legacy_extension_mismatches=bad,
                steam_slot=slots[0],disconnects=sum(s['disconnects'] for s in steam['slots']),outside_steam_xinput_slots=context['outside_steam_xinput_slots'],axes={},triggers={})
    for i,key in enumerate(('lx','ly','rx','ry')):
        result['axes'][key]=dict(legacy=distribution(s['raw'][i+2] for s in source),physical_fine=distribution(s['axes'][i] for s in source),steam_output=distribution(o[key] for o in output))
    for key,offset in [('lt',7),('rt',6)]:result['triggers'][key]=dict(physical=distribution(s['raw'][offset] for s in source),steam_output=distribution(o[key] for o in output))
    result['extra_buttons']={}
    for name,offset,bit,mask in [('PL',8,5,0x40),('PR',8,2,0x80),('L4',10,0,0x20),('R4',10,1,0x10)]:
        previous=bool(source[0]['raw'][offset]&(1<<bit));presses=[]
        for s in source[1:]:
            down=bool(s['raw'][offset]&(1<<bit))
            if down and not previous:
                matches=[o for o in output if s['time']<=o['qpc_ticks']<=s['time']+frequency//4 and o['buttons']&mask]
                presses.append(dict(seconds=(s['time']-start)/frequency,matched=bool(matches),output_mask=hex(matches[0]['buttons']) if matches else None))
            previous=down
        result['extra_buttons'][name]=dict(expected_mask=hex(mask),presses=presses)
    result['face_button_checks']={}
    for name,bit,mask in [('A',0,0x1000),('B',1,0x2000)]:
        previous=bool(source[0]['raw'][8]&(1<<bit));presses=[]
        for s in source[1:]:
            down=bool(s['raw'][8]&(1<<bit))
            if down and not previous:
                matches=[o for o in output if s['time']<=o['qpc_ticks']<=s['time']+frequency//4 and o['buttons']&mask]
                presses.append(dict(seconds=(s['time']-start)/frequency,matched=bool(matches)))
            previous=down
        result['face_button_checks'][name]=presses
    ticks=[s['time'] for s in source];result['axis_sign_check']={}
    for i,key in enumerate(('lx','ly','rx','ry')):
        pairs=[]
        for o in output:
            physical=source[max(0,bisect.bisect_right(ticks,o['qpc_ticks']-int(.002*frequency))-1)]['axes'][i]
            if abs(physical)>12000 and abs(o[key])>12000:pairs.append((physical,o[key]))
        result['axis_sign_check'][key]=dict(pairs=len(pairs),same_sign_fraction=sum((x>0)==(y>0) for x,y in pairs)/len(pairs) if pairs else None,note='Approximate 2 ms alignment; orientation check, not a latency measurement.')
    result['moving_phases']={}
    for name,lo,hi in [('sweeps',5,20),('circles',20,35)]:
        st=[];ot=[];previous=None
        for s in source:
            if lo<=(s['time']-start)/frequency<hi and s['axes']!=previous:st.append(s['time'])
            previous=s['axes']
        previous=None
        for o in output:
            axes=tuple(o[k] for k in ('lx','ly','rx','ry'))
            if lo<=(o['qpc_ticks']-start)/frequency<hi and axes!=previous:ot.append(o['qpc_ticks'])
            previous=axes
        result['moving_phases'][name]=dict(physical_changed_states=cadence(st,frequency),steam_changed_states=cadence(ot,frequency))
    result['fine_output_confirmed']=all(a['steam_output']['unique']>256 for a in result['axes'].values())
    result['all_extra_buttons_confirmed']=all(b['presses'] and all(p['matched'] for p in b['presses']) for b in result['extra_buttons'].values())
    result['limits']='Distinct codes are observed transport/output values, not sensor accuracy. Arrival/changed-state rates are not physical latency. Game-facing data is from Steam-launched diagnostic process, not a measurement of Witcher frame input.'
    (folder/'direct-reader-analysis.json').write_text(json.dumps(result,indent=2));return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('session',type=Path)
    print(json.dumps(analyze(parser.parse_args().session.resolve()),indent=2))
