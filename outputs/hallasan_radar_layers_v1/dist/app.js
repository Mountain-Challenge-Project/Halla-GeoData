/* Local static data + immutable radar snapshots. No KMA client or keys. */
'use strict';
const $=id=>document.getElementById(id), C=40075016.68557849, R=C/(2*Math.PI);
let data, snapshot=null, dynamic=null, selected=null, mode='local', live=true, loading=false, token=0;
let center=[0,0], scale=1, width=1, height=1, vkey='', tiles=new Map(), verrors=0, known=[];
const canvas=$('map'), ctx=canvas.getContext('2d'), bg=new Image(), slopeImg=new Image();
const rainColors=['#7ec8e3','#329bdf','#2968c8','#e5ca45','#f38b32','#d43545'];
const rainBounds=[0.1,1,5,10,20,30];
const merc=([lon,lat])=>[R*lon*Math.PI/180,R*Math.log(Math.tan(Math.PI/4+lat*Math.PI/360))];
const screen=([x,y])=>[(x-center[0])*scale+width/2,(center[1]-y)*scale+height/2];
const value=(x,d=1)=>x==null||!Number.isFinite(Number(x))?'—':Number(x).toFixed(d);
const kst=t=>new Intl.DateTimeFormat('ko-KR',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false}).format(new Date(t));
function rainColor(x){if(x===null||x===undefined)return null;if(x<0.1)return '#ffffff';let i=rainBounds.findLastIndex(b=>x>=b);return rainColors[Math.max(0,i)];}
function path(geometry){ctx.beginPath();let rings;
  if(geometry.type==='Polygon')rings=geometry.coordinates;
  else if(geometry.type==='MultiPolygon')rings=geometry.coordinates.flat();
  else if(geometry.type==='LineString')rings=[geometry.coordinates];
  else if(geometry.type==='MultiLineString')rings=geometry.coordinates;
  else return;
  for(const ring of rings){ring.forEach((p,i)=>{const q=screen(merc(p));i?ctx.lineTo(...q):ctx.moveTo(...q);});if(geometry.type.includes('Polygon'))ctx.closePath();}
}
function fit(){let b=data.bounds3857;center=[(b[0]+b[2])/2,(b[1]+b[3])/2];scale=Math.min(width/(b[2]-b[0]),height/(b[3]-b[1]))*.96;draw();}
function raster(image){if(!image.complete||!image.naturalWidth)return;const b=data.bounds3857,p=screen([b[0],b[3]]),q=screen([b[2],b[1]]);ctx.drawImage(image,p[0],p[1],q[0]-p[0],q[1]-p[1]);}
function vworld(){if(!vkey)return;let z=Math.max(7,Math.min(18,Math.round(Math.log2(scale*C/256)))),n=2**z,size=C/n;
 const minX=Math.floor((center[0]-width/(2*scale)+C/2)/size),maxX=Math.floor((center[0]+width/(2*scale)+C/2)/size);
 const minY=Math.floor((C/2-center[1]-height/(2*scale))/size),maxY=Math.floor((C/2-center[1]+height/(2*scale))/size);
 for(let x=minX;x<=maxX;x++)for(let y=minY;y<=maxY;y++){if(x<0||y<0||x>=n||y>=n)continue;const id=`${z}/${y}/${x}`;let im=tiles.get(id);
  if(!im){im=new Image();im.onload=()=>{if(mode==='vworld'){$('vworldStatus').textContent='VWorld 배경 타일 연결됨';draw();}};im.onerror=()=>{verrors++;$('vworldStatus').textContent='타일 연결 실패 · 키/등록 도메인/이용 권한을 확인하세요.';};im.src=`https://api.vworld.kr/req/wmts/1.0.0/${encodeURIComponent(vkey)}/Base/${z}/${y}/${x}.png`;tiles.set(id,im);}
  if(im.complete&&im.naturalWidth){const p=screen([x*size-C/2,C/2-y*size]);ctx.drawImage(im,p[0],p[1],size*scale+.5,size*scale+.5);}
 }if(tiles.size>700)tiles.clear();
}
const hatchCanvas=document.createElement('canvas');hatchCanvas.width=hatchCanvas.height=8;const hc=hatchCanvas.getContext('2d');hc.strokeStyle='#c5d2d7';hc.lineWidth=1;hc.beginPath();hc.moveTo(0,8);hc.lineTo(8,0);hc.stroke();const hatch=ctx.createPattern(hatchCanvas,'repeat');
function draw(){if(!data)return;ctx.clearRect(0,0,width,height);ctx.fillStyle='#193c48';ctx.fillRect(0,0,width,height);
 if(mode==='vworld')vworld();else raster(bg);
 if($('slope').checked){ctx.globalAlpha=.58;raster(slopeImg);ctx.globalAlpha=1;}
 if($('rain').checked&&dynamic){for(const f of dynamic.grid.features){const p=f.properties,v=p.rain_mean_mm_h;path(f.geometry);
   if(v==null){ctx.globalAlpha=.38;ctx.fillStyle=hatch;ctx.fill();}else if(v>=.1){ctx.globalAlpha=+$('opacity').value/100;ctx.fillStyle=rainColor(v);ctx.fill();}
   if(v!=null&&p.rain_valid_pct<99.9){ctx.globalAlpha=.9;ctx.strokeStyle='#d5dfe1';ctx.lineWidth=1;ctx.setLineDash([3,3]);ctx.stroke();ctx.setLineDash([]);}ctx.globalAlpha=1;
 }}
 if($('grid').checked){ctx.strokeStyle='#d5e0e16e';ctx.lineWidth=.6;for(const f of data.grid_slope_500m.features){path(f.geometry);ctx.stroke();}}
 if($('routes').checked){for(const f of data.course_summary.features){path(f.geometry);ctx.strokeStyle='#16232bc9';ctx.lineWidth=6;ctx.stroke();ctx.strokeStyle=selected===f.properties.course?'#fff583':'#fff';ctx.lineWidth=selected===f.properties.course?4:2.5;ctx.stroke();}}
 if($('steep').checked){ctx.strokeStyle='#ff925c';ctx.lineWidth=3.5;for(const f of data.steep_sections.features){path(f.geometry);ctx.stroke();}}
 if($('routes').checked){ctx.font='600 12px "Malgun Gothic",sans-serif';ctx.textAlign='center';for(const f of data.course_summary.features){const coords=f.geometry.type==='MultiLineString'?f.geometry.coordinates[0]:f.geometry.coordinates;const p=screen(merc(coords[Math.floor(coords.length*.55)]));ctx.lineWidth=4;ctx.strokeStyle='#152d39';ctx.strokeText(f.properties.course,p[0],p[1]-8);ctx.fillStyle='#fff';ctx.fillText(f.properties.course,p[0],p[1]-8);}}
 const lat=2*Math.atan(Math.exp(center[1]/R))-Math.PI/2, groundPixel=1/(scale)*Math.cos(lat);let meter=1000;if(1000/groundPixel>150)meter=500;if(1000/groundPixel<40)meter=2000;
 $('scale').style.width=(meter/groundPixel)+'px';$('scale').textContent=meter>=1000?meter/1000+' km':meter+' m';
}
function resize(){const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;canvas.width=width*devicePixelRatio;canvas.height=height*devicePixelRatio;ctx.setTransform(devicePixelRatio,0,0,devicePixelRatio,0,0);draw();}
function renderTable(){const tb=$('courses');tb.replaceChildren();for(const row of data.course_rows){const p=dynamic?.courses.features.find(f=>f.properties.course===row.course)?.properties;const tr=document.createElement('tr');if(row.course===selected)tr.className='selected';
  [row.course,row.length_m?value(+row.length_m/1000,2):'선형 없음',row.mean_deg?value(+row.mean_deg):'—',row.max_deg?value(+row.max_deg):'—',value(p?.rain_mean_mm_h),value(p?.rain_max_mm_h),p?value(p.rain_valid_pct):'—'].forEach(v=>{const td=document.createElement('td');td.textContent=v;tr.append(td);});tr.onclick=()=>{selected=selected===row.course?null:row.course;renderTable();draw();};tb.append(tr);
 }}
function updateStatus(){if(!snapshot?.observed_at){$('state').textContent='레이더 미연결 · 실제 자료 대기';$('obs').textContent='실제 레이더 입력 대기';$('delay').textContent='빈 값(—)은 강수 0을 뜻하지 않습니다.';return;}
 const minutes=Math.max(0,(Date.now()-Date.parse(snapshot.observed_at))/60000),stale=minutes>snapshot.stale_after_seconds/60;
 $('obs').textContent=kst(snapshot.observed_at)+' KST';$('delay').textContent=`관측 후 ${Math.floor(minutes)}분 경과 · ${snapshot.source_product}`;
 $('state').textContent=!live?'과거 자료 열람':stale?'갱신 지연 · 마지막 관측 표시':'최신 로컬 자료 추적';
 $('mapnote').textContent=(stale?'오래된 자료 · ':'')+'강우강도 mm/h · 참고격자 면적가중 평균 · 관측시각 확인';
}
async function readJSON(path){const r=await fetch(path,{cache:'no-store'});if(!r.ok)throw new Error('자료 읽기 실패 '+r.status);return r.json();}
function safeAsset(url){if(typeof url!=='string'||!/^frames\/[A-Za-z0-9-]+\/[A-Za-z_]+\.(geojson|csv|tif)$/.test(url))throw new Error('잘못된 자료 경로');return url;}
async function applyFrame(frame){if(!frame.frame_id){snapshot=frame;dynamic=null;updateStatus();renderTable();draw();return;}
 if(snapshot?.frame_id===frame.frame_id){updateStatus();return;}
 const generation=++token;const [grid,courses,steep]=await Promise.all(['grid','courses','steep'].map(k=>readJSON(safeAsset(frame.assets[k]))));
 if(generation!==token)return;
 if([grid,courses,steep].some(fc=>fc.features.some(f=>f.properties.frame_id!==frame.frame_id)))throw new Error('레이어 간 관측시각 불일치');
 dynamic={grid,courses,steep};snapshot=frame;$('download').href=safeAsset(frame.assets.course_csv);$('download').download='course_rain_'+frame.frame_id+'.csv';$('download').hidden=false;updateStatus();renderTable();draw();
}
async function poll(){if(loading)return;loading=true;try{const [latest,history]=await Promise.all([readJSON('state/latest.json'),readJSON('state/history.json')]);known=history.frames;const old=$('history').value;$('history').replaceChildren();
 if(!known.length){const op=new Option('저장된 자료 없음','');$('history').add(op);}else for(const f of [...known].reverse())$('history').add(new Option(kst(f.observed_at)+' · r'+f.revision,f.frame_id));
 if(!live)$('history').value=old;else{await applyFrame(latest);if(live)$('history').value=latest.frame_id||'';}
 try{const s=await readJSON('state/collector.json');$('collector').textContent=(s.status==='error'?'입력 오류 · ':'')+s.message;}catch{}
 }catch(e){$('state').textContent='갱신 실패 · 마지막 화면 유지';$('delay').textContent=e.message;}finally{loading=false;}}
document.querySelectorAll('.mode').forEach(b=>b.onclick=()=>{mode=b.dataset.mode;document.querySelectorAll('.mode').forEach(x=>x.classList.toggle('active',x===b));$('vworldPanel').hidden=mode!=='vworld';$('qgisPanel').hidden=mode!=='qgis';$('maptag').textContent=mode==='vworld'?'VWorld 배경 + 공통 한라산 레이어':mode==='qgis'?'QGIS 연결 안내 · 지도는 공통 자료 미리보기':'기존 위성·항공영상 + Copernicus 지형';$('attribution').textContent=(mode==='vworld'?'배경 연결 시: 공간정보 오픈플랫폼(브이월드). ':'')+data.credits;draw();});
$('connectVworld').onclick=()=>{const key=$('vkey').value.trim();if(!/^[A-Za-z0-9-]{10,150}$/.test(key)){$('vworldStatus').textContent='VWorld 웹용 키 형식을 확인하세요.';return;}vkey=key;$('vkey').value='';tiles.clear();verrors=0;$('vworldStatus').textContent='VWorld 배경 타일 연결 중';draw();};
const qgisCommand="from pathlib import Path; exec((Path(QgsProject.instance().fileName()).parent / 'sync_layers.py').read_text(encoding='utf-8'))";
$('copyQgis').onclick=async()=>{try{await navigator.clipboard.writeText(qgisCommand);$('qgisCopyStatus').textContent='복사했습니다. QGIS Python 콘솔에 붙여넣으세요.';}catch{$('qgisCopyStatus').textContent=qgisCommand;}};
for(const id of ['rain','routes','steep','grid','slope','opacity'])$(id).oninput=()=>{$('slopeLegend').hidden=!$('slope').checked;draw();};
$('refresh').onclick=poll;$('live').onclick=()=>{live=true;token++;$('live').classList.add('active');poll();};
$('history').onchange=async()=>{const f=known.find(x=>x.frame_id===$('history').value);if(f){live=false;$('live').classList.remove('active');try{await applyFrame(f);}catch(e){$('state').textContent=e.message;}}};
function zoom(f,x=width/2,y=height/2){const old=scale;scale=Math.max(.003,Math.min(.65,scale*f));center[0]+=(x-width/2)*(1/old-1/scale);center[1]-=(y-height/2)*(1/old-1/scale);draw();}
$('zoomIn').onclick=()=>zoom(1.4);$('zoomOut').onclick=()=>zoom(1/1.4);$('fit').onclick=fit;
$('exportPng').onclick=()=>{
 if(mode==='vworld'){$('mapnote').textContent='PNG 저장은 ① 전용 웹지도에서 사용할 수 있습니다.';return;}
 // Resizing resets any prior cross-origin canvas state from a VWorld session.
 resize();const out=document.createElement('canvas'),w=Math.max(1200,Math.round(width)),h=Math.round(height*w/width);out.width=w;out.height=h+205;const c=out.getContext('2d');
 c.fillStyle='#102d39';c.fillRect(0,0,w,out.height);c.fillStyle='#fff';c.font='bold 25px "Malgun Gothic",sans-serif';c.fillText('한라산 · 지형과 강수',24,36);c.font='14px "Malgun Gothic",sans-serif';
 c.fillStyle='#f4dc9c';c.fillText(snapshot?.observed_at?'관측시각 '+kst(snapshot.observed_at)+' KST · '+snapshot.source_product:'실제 레이더 자료 미입력 · 강수값 없음',24,63);c.drawImage(canvas,0,82,w,h);
 let y=h+107;c.font='13px "Malgun Gothic",sans-serif';c.fillStyle='#fff';c.fillText('표시: '+[$('routes').checked?'탐방로':null,$('steep').checked?'20° 이상 지형 구간':null,$('grid').checked?'500m 참고격자':null,$('slope').checked?'Copernicus 지형 경사':null].filter(Boolean).join(' · '),24,y);
 if($('slope').checked){y+=23;data.slope_colors.forEach((col,i)=>{c.fillStyle=col;c.fillRect(24+i*62,y-10,60,9);c.fillStyle='#fff';c.font='10px "Malgun Gothic",sans-serif';c.fillText(i===9?'45°+':`${i*5}–${i*5+5}°`,24+i*62,y+12);});}
 if(dynamic&&$('rain').checked){y+=38;c.font='12px "Malgun Gothic",sans-serif';c.fillStyle='#fff';c.fillText('강우강도 mm/h: 0.1 / 1 / 5 / 10 / 20 / 30+ · 유효 관측 부분만 평균',24,y);}
 c.font='10px "Malgun Gothic",sans-serif';c.fillStyle='#c7dadd';c.fillText(data.credits,24,out.height-23);c.fillText('경사는 보행면 기울기가 아니며 레이더 원격자와 참고격자의 정렬은 동일하다고 가정하지 않음.',24,out.height-7);
 const a=document.createElement('a');a.download='hallasan_layers_'+(snapshot?.frame_id||'waiting')+'.png';a.href=out.toDataURL('image/png');a.click();
};
canvas.addEventListener('wheel',e=>{e.preventDefault();const r=canvas.getBoundingClientRect();zoom(e.deltaY<0?1.15:1/1.15,e.clientX-r.left,e.clientY-r.top);},{passive:false});
let drag=null;canvas.onpointerdown=e=>{drag=[e.clientX,e.clientY];canvas.setPointerCapture(e.pointerId);};canvas.onpointermove=e=>{if(!drag)return;center[0]-=(e.clientX-drag[0])/scale;center[1]+=(e.clientY-drag[1])/scale;drag=[e.clientX,e.clientY];draw();};canvas.onpointerup=()=>drag=null;canvas.onpointercancel=()=>drag=null;
rainColors.forEach((c,i)=>{const row=document.createElement('div');row.className='legendrow';row.innerHTML=`<span class="swatch" style="background:${c}"></span><span>${rainBounds[i]}${i===rainBounds.length-1?' 이상':' – '+rainBounds[i+1]+' 미만'}</span>`;$('rainLegend').append(row);});
(async()=>{try{data=await readJSON('data/static.json');bg.onload=draw;slopeImg.onload=draw;bg.src='data/background.png';slopeImg.src='data/slope.png';$('attribution').textContent=data.credits;new ResizeObserver(resize).observe(canvas);resize();fit();renderTable();await poll();setInterval(poll,60000);setInterval(updateStatus,30000);}catch(e){$('state').textContent='로컬 서버에서 실행하세요';$('delay').textContent=e.message;}})();
