#!/usr/bin/env python3
"""
parallax_web.py —— 把「壁纸 + 深度图」打包成一个零依赖的网页 3D 壁纸（陀螺仪 / 鼠标视差）

手机浏览器打开 index.html：倾斜手机，近景远景反向移动（iOS 需点一下「开启陀螺仪」授权）；
电脑上用鼠标晃；没有输入时自动缓慢漂移。整页只有一个 WebGL 片元着色器，和 depthy / SceneShift /
wagerfield-parallax 是一个原理。它也可以直接丢给 Lively Wallpaper / Wallpaper Engine 当「网页壁纸」。

用法：
  python3 scripts/parallax_web.py IMG_DIR --depth-dir DEPTH_DIR --out WEB_DIR [--glob "金鱼*.png"] [--width 1080] [--title 金鱼福气]
输出：WEB_DIR/index.html + img/NN.jpg（缩到 --width 宽）+ depth/NN.png
"""
import argparse, glob, html, json, os
import cv2

PAGE = r"""<!doctype html><html lang="zh"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover,user-scalable=no">
<title>__TITLE__ · 3D 视差壁纸</title>
<style>
html,body{margin:0;height:100%;background:#000;overflow:hidden;font-family:-apple-system,system-ui,sans-serif;color:#eee}
canvas{position:fixed;inset:0;width:100vw;height:100vh;display:block}
#ui{position:fixed;left:0;right:0;bottom:0;padding:10px 12px calc(10px + env(safe-area-inset-bottom));display:flex;gap:8px;flex-wrap:wrap;justify-content:center;background:linear-gradient(transparent,rgba(0,0,0,.55))}
button,select{font:14px system-ui;padding:8px 12px;border-radius:10px;border:0;background:rgba(255,255,255,.18);color:#fff;backdrop-filter:blur(8px)}
#hint{position:fixed;top:10px;left:0;right:0;text-align:center;font-size:12px;opacity:.75;pointer-events:none}
.hide #ui,.hide #hint{display:none}
</style></head><body>
<canvas id="c"></canvas>
<div id="hint">倾斜手机 / 移动鼠标 → 近景远景反向移动 · 双击隐藏按钮</div>
<div id="ui"><select id="pick"></select><button id="gyro">开启陀螺仪</button><button id="amp">幅度 中</button><button id="fs">全屏</button></div>
<script>
const ITEMS=__ITEMS__;
const cv=document.getElementById('c'),gl=cv.getContext('webgl',{antialias:false,preserveDrawingBuffer:false});
const VS=`attribute vec2 p;varying vec2 v;void main(){v=vec2(p.x*.5+.5,.5-p.y*.5);gl_Position=vec4(p,0.,1.);}`;
const FS=`precision highp float;varying vec2 v;uniform sampler2D img,dep;uniform vec2 tilt,fit;uniform float focus,amp;
void main(){
  vec2 uv=(v-.5)*fit+.5;                       // cover 裁切
  uv=(uv-.5)*(1.0-2.2*amp)+.5;                  // 预留安全边
  float d=texture2D(dep,uv).r;
  vec2 o=(d-focus)*tilt*amp;                    // 近景顺着倾斜方向走，远景反向
  // 6 步小步长遮挡修正：近处像素优先（steep parallax 的廉价版）
  vec2 best=uv+o; float bd=-1.;
  for(int i=0;i<6;i++){float t=float(i)/5.;vec2 q=uv+o*t;float dq=texture2D(dep,q).r;if(dq>=d-0.08*(1.-t)&&dq>bd){bd=dq;best=q;}}
  gl_FragColor=texture2D(img,clamp(best,0.002,0.998));
}`;
function sh(t,s){const x=gl.createShader(t);gl.shaderSource(x,s);gl.compileShader(x);if(!gl.getShaderParameter(x,gl.COMPILE_STATUS))throw gl.getShaderInfoLog(x);return x}
const pr=gl.createProgram();gl.attachShader(pr,sh(gl.VERTEX_SHADER,VS));gl.attachShader(pr,sh(gl.FRAGMENT_SHADER,FS));gl.linkProgram(pr);gl.useProgram(pr);
const buf=gl.createBuffer();gl.bindBuffer(gl.ARRAY_BUFFER,buf);gl.bufferData(gl.ARRAY_BUFFER,new Float32Array([-1,-1,1,-1,-1,1,1,1]),gl.STATIC_DRAW);
const lp=gl.getAttribLocation(pr,'p');gl.enableVertexAttribArray(lp);gl.vertexAttribPointer(lp,2,gl.FLOAT,false,0,0);
const U=n=>gl.getUniformLocation(pr,n);
function tex(unit,src,cb){const t=gl.createTexture();const im=new Image();im.onload=()=>{gl.activeTexture(gl.TEXTURE0+unit);gl.bindTexture(gl.TEXTURE_2D,t);gl.texImage2D(gl.TEXTURE_2D,0,gl.RGBA,gl.RGBA,gl.UNSIGNED_BYTE,im);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MIN_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_MAG_FILTER,gl.LINEAR);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_S,gl.CLAMP_TO_EDGE);gl.texParameteri(gl.TEXTURE_2D,gl.TEXTURE_WRAP_T,gl.CLAMP_TO_EDGE);cb&&cb(im)};im.src=src}
let aspect=3/4,target=[0,0],cur=[0,0],idle=true,amp=0.035,focus=0.45,lastInput=0;
const AMPS=[['小',0.02],['中',0.035],['大',0.055]];let ai=1;
function load(i){const it=ITEMS[i];tex(0,it.img,im=>{aspect=im.width/im.height});tex(1,it.depth);gl.uniform1i(U('img'),0);gl.uniform1i(U('dep'),1);location.hash=i}
function resize(){const dpr=Math.min(devicePixelRatio||1,2);cv.width=innerWidth*dpr;cv.height=innerHeight*dpr;gl.viewport(0,0,cv.width,cv.height)}
addEventListener('resize',resize);resize();
function frame(t){
  const sa=innerWidth/innerHeight,fit=sa>aspect?[1,aspect/sa]:[sa/aspect,1];
  if(idle||t-lastInput>2500){target=[Math.sin(t/2600)*0.6,Math.cos(t/3300)*0.4]}
  cur[0]+=(target[0]-cur[0])*0.08;cur[1]+=(target[1]-cur[1])*0.08;
  gl.uniform2f(U('tilt'),cur[0],cur[1]);gl.uniform2f(U('fit'),fit[0],fit[1]);gl.uniform1f(U('focus'),focus);gl.uniform1f(U('amp'),amp);
  gl.drawArrays(gl.TRIANGLE_STRIP,0,4);requestAnimationFrame(frame)}
requestAnimationFrame(frame);
addEventListener('pointermove',e=>{idle=false;lastInput=performance.now();target=[(e.clientX/innerWidth-.5)*2,(e.clientY/innerHeight-.5)*2]});
function onOri(e){if(e.gamma==null)return;idle=false;lastInput=performance.now();target=[Math.max(-1,Math.min(1,e.gamma/25)),Math.max(-1,Math.min(1,(e.beta-45)/25))]}
document.getElementById('gyro').onclick=async()=>{try{if(typeof DeviceOrientationEvent!=='undefined'&&DeviceOrientationEvent.requestPermission){const r=await DeviceOrientationEvent.requestPermission();if(r!=='granted')return alert('没有授权陀螺仪')}addEventListener('deviceorientation',onOri);document.getElementById('gyro').textContent='陀螺仪已开'}catch(err){alert(err)}};
if(typeof DeviceOrientationEvent!=='undefined'&&!DeviceOrientationEvent.requestPermission)addEventListener('deviceorientation',onOri);
document.getElementById('amp').onclick=e=>{ai=(ai+1)%3;amp=AMPS[ai][1];e.target.textContent='幅度 '+AMPS[ai][0]};
document.getElementById('fs').onclick=()=>{(document.fullscreenElement?document.exitFullscreen():document.documentElement.requestFullscreen&&document.documentElement.requestFullscreen())};
const pick=document.getElementById('pick');ITEMS.forEach((it,i)=>{const o=document.createElement('option');o.value=i;o.textContent=it.name;pick.appendChild(o)});
pick.onchange=()=>load(+pick.value);
addEventListener('dblclick',()=>document.body.classList.toggle('hide'));
const start=Math.min(ITEMS.length-1,Math.max(0,parseInt(location.hash.slice(1))||0));pick.value=start;load(start);
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("img_dir")
    ap.add_argument("--depth-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--glob", default="*.png")
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--title", default="3D 视差壁纸")
    a = ap.parse_args()
    os.makedirs(os.path.join(a.out, "img"), exist_ok=True)
    os.makedirs(os.path.join(a.out, "depth"), exist_ok=True)
    items = []
    for f in sorted(glob.glob(os.path.join(a.img_dir, a.glob))):
        name = os.path.splitext(os.path.basename(f))[0]
        dp = os.path.join(a.depth_dir, name + ".png")
        if not os.path.exists(dp):
            print("[skip] 没有深度图：", name); continue
        im = cv2.imread(f); h, w = im.shape[:2]
        if w > a.width:
            im = cv2.resize(im, (a.width, int(h * a.width / w)), interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(a.out, "img", name + ".jpg"), im, [cv2.IMWRITE_JPEG_QUALITY, 88])
        d = cv2.imread(dp, cv2.IMREAD_GRAYSCALE)
        d = cv2.resize(d, (im.shape[1] // 2, im.shape[0] // 2), interpolation=cv2.INTER_AREA)
        cv2.imwrite(os.path.join(a.out, "depth", name + ".png"), d)
        items.append({"name": name, "img": f"img/{name}.jpg", "depth": f"depth/{name}.png"})
        print("[web]", name)
    page = PAGE.replace("__ITEMS__", json.dumps(items, ensure_ascii=False)).replace("__TITLE__", html.escape(a.title))
    with open(os.path.join(a.out, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(page)
    print("[index]", os.path.join(a.out, "index.html"), len(items), "张")


if __name__ == "__main__":
    main()
