#!/usr/bin/env python3
"""Release-only font build; requires fontTools 4.60.2, never used at runtime.
Pass the public NotoSansSC-VF.ttf from the pinned source in font-source.json.
"""
import argparse,hashlib,json
from pathlib import Path
from fontTools.ttLib import TTFont
from fontTools.subset import Subsetter,Options
from fontTools.varLib.instancer import instantiateVariableFont
ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--source',required=True);a=ap.parse_args()
    source=Path(a.source);font=TTFont(source)
    chars=set(chr(n) for n in range(32,127))
    for p in (ROOT/'scripts/pindou').glob('*.py'):
        chars.update(c for c in p.read_text() if ord(c)>127)
    opts=Options();opts.name_IDs=['*'];opts.name_legacy=True;opts.name_languages=['*']
    sub=Subsetter(options=opts);sub.populate(text=''.join(sorted(chars)));sub.subset(font)
    font=instantiateVariableFont(font,{'wght':400},inplace=True)
    for record in font['name'].names:
        if record.nameID in (1,3,4,6,16,17):
            value={1:'Kang Pindou UI',3:'KangPindouUI-Regular-0.2',4:'Kang Pindou UI Regular',6:'KangPindouUI-Regular',16:'Kang Pindou UI',17:'Regular'}[record.nameID]
            record.string=value.encode(record.getEncoding())
    out=ROOT/'assets/fonts/KangPindouUI-Regular.ttf';out.parent.mkdir(parents=True,exist_ok=True);font.save(out)
    missing=chars-set(chr(n) for n in font.getBestCmap())
    assert not missing,repr(missing)
    data={'source_repository':'https://github.com/notofonts/noto-cjk','source_commit':'f8d157532fbfaeda587e826d4cd5b21a49186f7c','source_path':'Sans/Variable/TTF/Subset/NotoSansSC-VF.ttf','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'license':'SIL Open Font License 1.1; licenses/noto-cjk-OFL.txt','modification':'Chinese UI + ASCII subset, weight 400, renamed Kang Pindou UI','build_fonttools':'4.60.2','subset_sha256':hashlib.sha256(out.read_bytes()).hexdigest(),'bytes':out.stat().st_size,'codepoints':sorted(ord(c) for c in chars)}
    (ROOT/'references/font-source.json').write_text(json.dumps(data,indent=2)+'\n');print(out, out.stat().st_size)
if __name__=='__main__':main()
