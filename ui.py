HTML = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>악보 영상 → PDF</title>
<style>
:root{--b:#2b6cb0;--bg:#f6f7f9;--bd:#d9dde3}
*{box-sizing:border-box}body{font-family:-apple-system,"Malgun Gothic",sans-serif;background:var(--bg);margin:0;color:#222}
main{max-width:1100px;margin:0 auto;padding:24px}
h1{margin:0 0 4px}h2{margin:0 0 12px;font-size:18px}.sub{color:#666;margin-bottom:18px}
section{background:#fff;border:1px solid var(--bd);border-radius:10px;padding:18px;margin-bottom:16px}
input[type=text],select{padding:9px;border:1px solid var(--bd);border-radius:6px;font-size:15px}
input[type=text]{width:100%}
button{background:var(--b);color:#fff;border:0;border-radius:6px;padding:10px 18px;font-size:15px;cursor:pointer}
button:disabled{background:#aab;cursor:default}button.sec{background:#fff;color:var(--b);border:1px solid var(--b)}
.row{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-top:10px}
.crop{display:grid;grid-template-columns:2fr 1fr;gap:18px}@media(max-width:800px){.crop{grid-template-columns:1fr}}
.crop img{width:100%;border:1px solid var(--bd);border-radius:6px}
label.sl{display:block;font-size:13px;margin-top:8px}label.sl input{width:100%}
.bar{height:8px;background:#e3e6ea;border-radius:4px;overflow:hidden;margin-top:10px}.bar>div{height:100%;width:0;background:var(--b);transition:width .2s}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.card{border:1px solid var(--bd);border-radius:8px;padding:8px}.card img{width:100%}.card.off{opacity:.35}
.msg{margin-top:10px;font-size:14px}.ok{color:#18794e}.err{color:#c0392b}.hide{display:none}
details{margin-top:10px}small{color:#777}
</style></head><body><main>
<h1>🎼 악보 영상 → PDF</h1><div class="sub">유튜브 링크를 넣으면 영상 아래쪽 악보를 캡처해 PDF로 만들고, 구글 드라이브에 정리합니다.</div>

<section><h2>① 유튜브 링크</h2>
<input type="text" id="url" placeholder="https://www.youtube.com/watch?v=...">
<div class="row"><select id="q"><option>720</option><option>1080</option><option>480</option></select><small>다운로드 화질(악보가 작으면 1080)</small>
<button id="btnLoad" onclick="load()">영상 불러오기</button></div>
<div class="bar hide" id="bar1"><div></div></div><div class="msg" id="m1"></div></section>

<section id="s2" class="hide"><h2>② 악보 영역 지정 <small id="vinfo"></small></h2>
<div class="crop"><div><img id="prev"></div><div>
<label class="sl">미리보기 시점 <span id="vt"></span><input type="range" id="t" min="0" value="10"></label>
<label class="sl">위쪽 경계 <span id="vtop"></span>%<input type="range" id="top" min="0" max="95" value="55"></label>
<label class="sl">아래쪽 경계 <span id="vbot"></span>%<input type="range" id="bottom" min="5" max="100" value="100"></label>
<label class="sl">왼쪽 경계 <span id="vl"></span>%<input type="range" id="left" min="0" max="50" value="0"></label>
<label class="sl">오른쪽 경계 <span id="vr"></span>%<input type="range" id="right" min="50" max="100" value="100"></label>
</div></div>
<details><summary>고급 설정</summary>
<label class="sl">검사 간격(초) <span id="vi"></span><input type="range" id="interval" min="0.2" max="2" step="0.1" value="0.5"></label>
<label class="sl">페이지 바뀜 민감도 <span id="vc"></span> <small>(같은 장이 중복되면 올리고, 놓치면 내리세요)</small><input type="range" id="change" min="0.005" max="0.2" step="0.005" value="0.05"></label>
<label class="sl">중복 판정 기준 <span id="vd"></span><input type="range" id="dup" min="0" max="0.1" step="0.005" value="0.02"></label></details>
<div class="row"><button id="btnExtract" onclick="extract()">③ 악보 캡처 시작</button></div>
<div class="bar hide" id="bar2"><div></div></div><div class="msg" id="m2"></div></section>

<section id="s3" class="hide"><h2>④ 캡처 결과 <small id="cnt"></small></h2>
<small>필요 없는 장은 체크를 해제하세요.</small><div class="grid" id="grid" style="margin-top:10px"></div></section>

<section id="s4" class="hide"><h2>⑤ PDF · 구글 드라이브 정리</h2>
<div class="row"><label>악기 <select id="inst"></select></label><input type="text" id="instCustom" placeholder="악기 직접 입력" style="width:180px;display:none"></div>
<div class="row"><label>PDF 배치 <select id="layout"><option value="stack">A4 세로에 이어 붙이기 (인쇄용)</option><option value="single">캡처 1장 = 1페이지</option></select></label></div>
<div class="row"><label>저장 방식 <select id="mode"><option value="folder">드라이브 데스크톱 폴더 (간단)</option><option value="api">Drive API 업로드</option><option value="none">저장 안 함</option></select></label></div>
<div class="row" id="rootRow"><input type="text" id="root" placeholder="‘내 드라이브’ 폴더 경로"></div>
<small id="where"></small>
<div class="row"><button id="btnFinish" onclick="finish()">PDF 만들고 정리하기</button><a id="dl" class="hide" href="/api/pdf"><button class="sec" type="button">📄 PDF 다운로드</button></a></div>
<div class="msg" id="m4"></div></section>

</main><script>
const $=id=>document.getElementById(id);let N=0,cfg={};
const api=(p,b)=>fetch(p,b?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(b)}:{}).then(r=>r.json());
async function poll(job,bar,onDone){const b=$(bar);b.classList.remove('hide');
 while(true){const j=await api('/api/job/'+job);b.firstChild.style.width=(j.progress*100)+'%';
  if(j.status!=='running'){b.classList.add('hide');return j}await new Promise(r=>setTimeout(r,500))}}
async function init(){cfg=await api('/api/config');$('inst').innerHTML=cfg.instruments.map(i=>`<option>${i}</option>`).join('')+'<option>직접 입력</option>';$('root').value=cfg.drive_root||''}
init();
async function load(){$('btnLoad').disabled=true;$('m1').textContent='';
 const r=await api('/api/load',{url:$('url').value.trim(),quality:+$('q').value});
 const j=await poll(r.job,'bar1');$('btnLoad').disabled=false;
 if(j.status!=='done'){$('m1').innerHTML='<span class=err>다운로드 실패: '+(j.error||'')+'</span>';return}
 const v=j.result;$('m1').innerHTML='<span class=ok>불러옴: '+v.title+'</span>';$('s2').classList.remove('hide');
 $('t').max=Math.floor(v.duration);$('t').value=Math.min(10,Math.floor(v.duration));$('vinfo').textContent=`(${v.width}×${v.height}, ${(v.duration/60).toFixed(1)}분)`;
 $('inst').value=v.guess;onInst();preview()}
const ids=['t','top','bottom','left','right','interval','change','dup'];
const lab={t:'vt',top:'vtop',bottom:'vbot',left:'vl',right:'vr',interval:'vi',change:'vc',dup:'vd'};
let tm;ids.forEach(i=>$(i).addEventListener('input',()=>{$(lab[i]).textContent=$(i).value;clearTimeout(tm);tm=setTimeout(preview,150)}));
ids.forEach(i=>$(lab[i]).textContent=$(i).value);
function preview(){$('prev').src=`/api/frame?t=${$('t').value}&top=${$('top').value}&bottom=${$('bottom').value}&left=${$('left').value}&right=${$('right').value}&_=${Date.now()}`}
async function extract(){$('btnExtract').disabled=true;$('m2').textContent='';
 const r=await api('/api/extract',{top:+$('top').value/100,bottom:+$('bottom').value/100,left:+$('left').value/100,right:+$('right').value/100,interval:+$('interval').value,change:+$('change').value,dup:+$('dup').value});
 const j=await poll(r.job,'bar2');$('btnExtract').disabled=false;
 if(j.status!=='done'||!j.result.count){$('m2').innerHTML='<span class=err>악보를 찾지 못했습니다. 영역이나 민감도를 조정해 보세요. '+(j.error||'')+'</span>';return}
 N=j.result.count;$('grid').innerHTML=j.result.times.map((t,i)=>`<div class=card id=c${i}><img src="/api/page/${i}?_=${Date.now()}"><label><input type=checkbox checked data-i=${i} onchange="$('c${i}').classList.toggle('off',!this.checked)"> ${i+1}번 (${Math.floor(t/60)}:${String(Math.floor(t%60)).padStart(2,'0')})</label></div>`).join('');
 $('cnt').textContent=N+'장';$('s3').classList.remove('hide');$('s4').classList.remove('hide');upd()}
function onInst(){$('instCustom').style.display=$('inst').value==='직접 입력'?'':'none';upd()}
$('inst').onchange=onInst;$('instCustom').oninput=upd;
$('mode').onchange=()=>{$('rootRow').style.display=$('mode').value==='folder'?'':'none'};
function instName(){return $('inst').value==='직접 입력'?$('instCustom').value.trim():$('inst').value}
function upd(){$('where').textContent='저장 위치: 악보 / '+(instName()||'?')+' / (영상 제목) /  — PNG 낱장 + PDF'}
async function finish(){$('btnFinish').disabled=true;$('m4').textContent='처리 중…';
 const keep=[...document.querySelectorAll('#grid input:checked')].map(e=>+e.dataset.i);
 const r=await api('/api/finish',{keep,layout:$('layout').value,instrument:instName(),mode:$('mode').value,root:$('root').value.trim()});
 $('btnFinish').disabled=false;
 if(r.error){$('m4').innerHTML='<span class=err>'+r.error+'</span>';if(r.pdf)$('dl').classList.remove('hide');return}
 $('dl').classList.remove('hide');$('m4').innerHTML='<span class=ok>완료! '+(r.saved||'')+'</span>'}
</script></body></html>"""
