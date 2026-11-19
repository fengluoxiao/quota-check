"""Reuse the existing Expo app icon in a native iPhone/iPad asset catalog."""
import json
from pathlib import Path
import subprocess
import sys

source=Path(sys.argv[1]).resolve()
catalog=Path(sys.argv[2]).resolve()
folder=catalog/'AppIcon.appiconset';folder.mkdir(parents=True,exist_ok=True)
(catalog/'Contents.json').write_text(json.dumps({'info':{'author':'xcode','version':1}}),encoding='utf-8')
images=[]
for idiom,sizes,scales in [('iphone',[20,29,40,60],[2,3]),('ipad',[20,29,40,76],[1,2]),('ipad',[83.5],[2]),('ios-marketing',[1024],[1])]:
    for size in sizes:
        for scale in scales:
            pixels=int(size*scale);name=f'{idiom}-{size:g}-{scale}x.png'
            subprocess.run(['sips','-z',str(pixels),str(pixels),str(source),'--out',str(folder/name)],check=True,stdout=subprocess.DEVNULL)
            images.append({'idiom':idiom,'size':f'{size:g}x{size:g}','scale':f'{scale}x','filename':name})
(folder/'Contents.json').write_text(json.dumps({'images':images,'info':{'author':'xcode','version':1}},indent=2),encoding='utf-8')
