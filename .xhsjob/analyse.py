from PIL import Image
import glob, subprocess, collections

RAMP = " .:-=+*#%@"

def layout_map(im, cols=36, rows=76):
    g = im.convert('L').resize((cols, rows), Image.LANCZOS)
    px = list(g.getdata()); lo, hi = min(px), max(px); rng = max(1, hi-lo)
    return [''.join(RAMP[min(9,(px[r*cols+c]-lo)*10//rng)] for c in range(cols)) for r in range(rows)]

def bands(im, n=10):
    small = im.resize((60, 60*n), Image.LANCZOS)
    out=[]
    for b in range(n):
        q = small.crop((0,b*60,60,(b+1)*60)).quantize(colors=3, method=Image.MEDIANCUT).convert('RGB')
        cnt = collections.Counter(q.getdata())
        out.append(f"  y{b*10:3d}-{(b+1)*10:3d}%: " + "  ".join(f"#{r:02x}{g:02x}{bl:02x}:{c*100//3600}%" for (r,g,bl),c in cnt.most_common(3)))
    return out

def ocr(path):
    try:
        out = subprocess.run(['tesseract', path, 'stdout', '-l','chi_sim+eng','--psm','11','tsv'],
                             capture_output=True, text=True, timeout=240).stdout
    except Exception as e:
        return f"  OCR ERR {e}"
    rows=[]
    for i,row in enumerate(out.strip().split('\n')):
        p=row.split('\t')
        if i==0 or len(p)<12: continue
        try: conf=float(p[10])
        except: continue
        t=p[11].strip()
        if conf<45 or not t: continue
        rows.append((int(p[7]),int(p[6]),int(p[8]),int(p[9]),t,conf))
    if not rows: return "  (no text detected)"
    W,H = Image.open(path).size
    rows.sort()
    return '\n'.join(f"  conf{conf:3.0f} y={top*100//H:3d}% x={l*100//W:3d}% box={w}x{h} «{t}»" for top,l,w,h,t,conf in rows)

def edgemap(im, cols=36, rows=38):
    from PIL import ImageFilter
    e = im.convert('L').resize((cols*4, rows*4), Image.LANCZOS).filter(ImageFilter.FIND_EDGES)
    px=list(e.getdata()); W=cols*4
    out=[]
    for r in range(rows):
        line=''
        for c in range(cols):
            tot=sum(px[(r*4+dy)*W + c*4+dx] for dy in range(4) for dx in range(4))/16
            line += '#' if tot>45 else ('+' if tot>22 else ('.' if tot>8 else ' '))
        out.append(line)
    return out

for f in sorted(glob.glob('raw/*.png')):
    im = Image.open(f).convert('RGB'); W,H = im.size
    print(f"\n===== {f}  {W}x{H} =====")
    print("--- edge/detail map (# = high detail, likely text or line art) ---")
    for l in edgemap(im): print('|'+l+'|')
    print("--- luminance ---")
    for l in layout_map(im): print('|'+l+'|')
    print("--- colours ---")
    for b in bands(im): print(b)
    print("--- OCR ---")
    print(ocr(f))
