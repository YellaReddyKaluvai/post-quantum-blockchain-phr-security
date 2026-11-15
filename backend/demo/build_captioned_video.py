#!/usr/bin/env python3
"""Render a captioned MP4 from authorized screen captures and measured results.
Requires Pillow and ffmpeg (or imageio-ffmpeg). Does not automate a browser.
"""
import argparse
import bisect
import json
from pathlib import Path
import shutil
import subprocess
from PIL import Image, ImageDraw, ImageFont


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--manifest',type=Path,required=True)
    p.add_argument('--results',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--font',type=Path,required=True)
    a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=True)
    scenes=json.loads(a.manifest.read_text())
    scenes=[s for s in scenes if s['name']!='01-welcome']
    results=json.loads(a.results.read_text())
    if not results.get('all_passed') or not results.get('checks') or not all(c['passed'] for c in results['checks']):
        p.error('This success walkthrough requires a completed passing run; inspect failed evidence first.')
    if not results.get('verification',{}).get('hash_matches') or not results.get('verification',{}).get('signature_valid'):
        p.error('The walkthrough requires verified report digest and signature evidence.')
    sample_count=results['configuration']['latency_samples_per_route']
    scenes += [
        {'name':'results','title':'Measured outcome | 30 live checks passed' if len(results['checks'])==30 and results['all_passed'] else 'Measured outcome',
         'caption':f'One client, {sample_count} sequential requests per route. Timings include network and hosting delays; these are not throughput or clinical-performance benchmarks.',
         'duration':16,'card':'metrics'},
        {'name':'scope','title':'What this demonstration proves',
         'caption':'The core clinical path and refusal checks passed. Blockchain, IPFS, S3, SMTP and independent multi-hospital training are not claimed as live integrations.',
         'duration':14,'card':'scope'},
        {'name':'reproduce','title':'Reproduce the evidence',
         'caption':'Run run_hosted_demo.py with your private administrator password. It creates fictional records and exports check results, timings, versions and the sample report.',
         'duration':14,'card':'reproduce'}]
    W,H=1440,1080
    fonts={n:ImageFont.truetype(str(a.font),n) for n in [18,21,26,29,33,38,45]}
    navy='#071a2c'; cyan='#33d3cb'; white='#eef7ff'; grey='#a7bdcf'
    render=a.output/'video-render';render.mkdir(exist_ok=True)
    source=a.output/'video-source';source.mkdir(exist_ok=True)
    source_manifest=[]; concat=[]; subtitles=[]; transcript=[]; clock=0; frame_no=0

    def lines(draw,text,font,max_width):
        out=[];line=''
        for word in text.split():
            candidate=(line+' '+word).strip()
            if draw.textlength(candidate,font=font)>max_width and line:
                out.append(line);line=word
            else:line=candidate
        if line:out.append(line)
        return out

    def stamp(seconds):
        ms=round(seconds*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

    def draw_frame(scene,screen,number):
        im=Image.new('RGB',(W,H),navy);d=ImageDraw.Draw(im)
        d.text((28,20),'QUANTUMCARE  /  WORKING DEMONSTRATION',font=fonts[18],fill=cyan)
        d.text((28,51),scene['title'],font=fonts[33],fill=white)
        d.text((W-110,25),f'{number:02}/{len(scenes):02}',font=fonts[21],fill=grey)
        if screen:
            shot=Image.open(screen).convert('RGB');shot.thumbnail((1384,779),Image.Resampling.LANCZOS)
            # Preserve the actual captured layout without cropping or reconstructing controls.
            im.paste(shot,((W-shot.width)//2,111+(779-shot.height)//2))
        else:
            d.rounded_rectangle((28,112,W-28,890),radius=18,fill='#102b43',outline='#22516b',width=2)
            if scene['card']=='metrics':
                d.text((65,150),f"{sum(c['passed'] for c in results['checks'])}/{len(results['checks'])} checks passed",font=fonts[45],fill=cyan)
                d.text((65,225),'Measured through the public Vercel URL',font=fonts[26],fill=white)
                d.text((65,310),'ROUTE',font=fonts[21],fill=grey)
                d.text((725,310),'MEDIAN',font=fonts[21],fill=grey)
                d.text((1040,310),'P95',font=fonts[21],fill=grey)
                y=360
                for name,data in results.get('latency',{}).items():
                    d.text((65,y),name.replace('_',' ').title(),font=fonts[33],fill=white)
                    d.text((725,y),str(data['median_ms'])+' ms',font=fonts[33],fill=cyan)
                    d.text((1040,y),str(data['p95_ms'])+' ms',font=fonts[33],fill=white);y+=100
                d.text((65,730),'ML-KEM-768  +  ML-DSA-65  |  digest and signature: verified',font=fonts[26],fill=white)
                d.text((65,790),'Synthetic CBC PDF: '+str(results['sample_pdf']['bytes'])+' bytes',font=fonts[26],fill=grey)
            else:
                text = ([
                    'VERIFIED: five-role sign-in and secure sessions',
                    'VERIFIED: consent, care assignment and access withdrawal',
                    'VERIFIED: doctor order -> lab report -> patient PDF',
                    'VERIFIED: digest, signature, role denial and logout',
                    'NOT LIVE: blockchain, IPFS publishing, S3 and SMTP',
                    'NOT EVALUATED: independent federation and every secondary workflow',
                    'Free Render database currently expires 23 November 2026.'
                ] if scene['card']=='scope' else [
                    '1  Open backend/demo/WORKING_DEMO.md',
                    '2  Run backend/demo/run_hosted_demo.py',
                    '3  Enter the administrator password privately',
                    '4  Review results.json, summary.md and sample-report.pdf',
                    '5  Compare source revisions, config and runner hash',
                    'Never publish the separately generated account credentials.',
                    'post-quantum-blockchain-phr-securit.vercel.app'
                ])
                y=155
                for paragraph in text:
                    for line in lines(d,paragraph,fonts[29],1280):
                        d.text((65,y),line,font=fonts[29],fill=white);y+=43
                    y+=36
        d.rectangle((0,909,W,1080),fill='#03111f')
        caplines=lines(d,scene['caption'],fonts[29],1350)
        if len(caplines)>3:raise ValueError('Caption too long: '+scene['name'])
        for i,line in enumerate(caplines):d.text((40,932+i*37),line,font=fonts[29],fill=white)
        d.text((40,1048),'FICTIONAL DATA  |  ACTUAL APP CAPTURES  |  PAUSES EDITED FOR READABILITY',font=fonts[18],fill=cyan)
        return im

    for number,scene in enumerate(scenes,1):
        duration=scene['duration']; selected=[]
        source_scene={k:v for k,v in scene.items() if k not in ['path','frames']}
        if 'frames' in scene:
            originals=scene['frames'];times=[f['time'] for f in originals]
            for i in range(round(duration*8)):
                target=i/8
                ix=max(0,bisect.bisect_right(times,target)-1)
                selected.append((originals[ix]['path'],1/8))
        else:selected=[(scene.get('path'),duration)]
        saved_map={};new_frames=[]
        for screen,seconds in selected:
            if screen:
                screen_path=Path(screen)
                if not screen_path.is_absolute():screen_path=a.manifest.parent/screen_path
                if str(screen_path) not in saved_map:
                    target=source/(scene['name']+'-'+str(len(saved_map)).zfill(3)+'.jpg')
                    shutil.copyfile(screen_path,target);saved_map[str(screen_path)]=target.name
                new_frames.append({'path':saved_map[str(screen_path)],'time':sum(x[1] for x in selected[:len(new_frames)])})
            path=render/(str(frame_no).zfill(5)+'.jpg');frame_no+=1
            draw_frame(scene,screen_path if screen else None,number).save(path,quality=92)
            concat += ["file '"+str(path.resolve())+"'",'duration '+str(seconds)]
        if 'frames' in scene:source_scene['frames']=new_frames
        elif scene.get('path'):source_scene['path']=next(iter(saved_map.values()))
        source_manifest.append(source_scene)
        subtitles += [str(number),stamp(clock)+' --> '+stamp(clock+duration),scene['caption'],'']
        transcript += [f'## {stamp(clock)} — {scene["title"]}', '', scene['caption'],'']
        clock+=duration
    concat.append(concat[-2])
    (render/'frames.txt').write_text('\n'.join(concat)+'\n')
    (source/'scenes.json').write_text(json.dumps(source_manifest[:-3],indent=2))
    (a.output/'captions.srt').write_text('\n'.join(subtitles))
    (a.output/'video-transcript.md').write_text('# Captioned demonstration transcript\n\n'+'\n'.join(transcript))
    exe=shutil.which('ffmpeg')
    if not exe:
        import imageio_ffmpeg
        exe=imageio_ffmpeg.get_ffmpeg_exe()
    output=a.output/'quantumcare-captioned-demo.mp4'
    subprocess.run([exe,'-y','-loglevel','error','-f','concat','-safe','0','-i',str(render/'frames.txt'),
                    '-vf','fps=24','-t',str(clock),'-c:v','libx264','-preset','fast','-crf','21',
                    '-pix_fmt','yuv420p','-movflags','+faststart','-an',str(output)],check=True)
    (a.output/'video-metadata.json').write_text(json.dumps({'duration_seconds':clock,'width':W,'height':H,'fps':24,
          'captions':'burned in','audio':'none; caption-led explanation','scenes':len(scenes),
          'source':'authorized screenshots and navigation-frame recordings of live app',
          'frame_count_input':frame_no,'bytes':output.stat().st_size},indent=2))
    print(json.dumps({'video':str(output),'seconds':clock,'scenes':len(scenes),'bytes':output.stat().st_size}))

if __name__=='__main__':main()
