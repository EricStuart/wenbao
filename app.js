'use strict';
const $=id=>document.getElementById(id),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const numbers='一二三四五六七八',fields=['province','city','county','category','era','batch'];
const categories=['古建筑','古遗址','古墓葬','石窟寺及石刻','近现代重要史迹及代表性建筑','其他'],eras=['史前','夏商周','秦汉','魏晋南北朝','隋唐五代','宋辽金夏','元','明','清','近现代'];
const shortCategory=c=>c==='近现代重要史迹及代表性建筑'?'近现代史迹':c;
const state={rows:[],filtered:[],meta:null,china:null,chart:null,page:1,pageSize:20,admin:[],boundaryFiles:new Set(),boundaryCache:new Map(),mapEpoch:0,mapView:null,focusId:null,streetMap:null,streetMarker:null,streetLoaded:false};
const collator=new Intl.Collator('zh-CN'),sortNames=a=>[...new Set(a)].sort(collator.compare);
function options(el,a,label){const old=el.value;el.innerHTML=`<option value="">${label}</option>`+a.map(x=>`<option value="${esc(x)}">${esc(x)}</option>`).join('');el.value=a.includes(old)?old:'';}
function syncLocations(){
 const province=state.admin.find(p=>p.name===$('province').value),rows=state.rows.filter(r=>r.province===$('province').value);
 options($('city'),province?sortNames([...province.cities.map(c=>c.name),...rows.map(r=>r.city)]):[],'全部城市');$('city').disabled=!province;
 const city=province?.cities.find(c=>c.name===$('city').value);
 options($('county'),$('city').value?sortNames([...(city?.counties.map(c=>c.name)||[]),...rows.filter(r=>r.city===$('city').value).map(r=>r.county)]):[],'全部区县');$('county').disabled=!$('city').value;
}
function filterRows(){const q=$('search').value.trim().toLocaleLowerCase();return state.rows.filter(r=>(!q||[r.name,r.address,r.province,r.city,r.county,r.era,...r.aliases||[]].join(' ').toLocaleLowerCase().includes(q))&&fields.every(f=>!$(f).value||(f==='era'?r.tags.includes($(f).value):String(r[f])===$(f).value)));}
function update(){state.focusId=null;state.page=1;state.filtered=filterRows();updateFilterCount();syncPickerControls();const count=state.filtered.length.toLocaleString();$('filter-count').textContent=count;const region=$('county').value||$('city').value||$('province').value||'全国';$('region-label').textContent=region;$('type-label').textContent=shortCategory($('category').value)||'类型';$('era-label').textContent=$('era').value||'时代';$('batch-label').textContent=$('batch').value?'第'+numbers[Number($('batch').value)-1]+'批':'批次';document.querySelector('.search-bar').classList.toggle('has-query',!!$('search').value.trim());$('list-subtitle').textContent=`${region} · ${count} 条名录`;$('reset').hidden=!['search',...fields].some(f=>$(f).value);$('reset-row').hidden=$('reset').hidden;$('filter-dot').hidden=!['category','era','batch'].some(f=>$(f).value);const located=state.filtered.filter(r=>r.coordinates).length;$('map-hint').textContent=state.filtered.length===0?'没有匹配结果，试试其他关键词':!$('province').value?'轻点省份，发现历史':`${located} 处参考点位 · 轻点查看${state.filtered.length-located?' · '+(state.filtered.length-located)+' 处待定位':''}`;renderCards();renderMap();const url=new URL(location.href);url.hash='';for(const f of ['search',...fields]){const v=$(f).value;if(v)url.searchParams.set(f,v);else url.searchParams.delete(f);}history.replaceState(null,'',url);}
function reset(){for(const f of ['search',...fields])$(f).value='';syncLocations();update();}
function renderCards(){const rows=state.filtered;const pages=Math.max(1,Math.ceil(rows.length/state.pageSize));state.page=Math.min(state.page,pages);$('cards').innerHTML=rows.slice((state.page-1)*state.pageSize,state.page*state.pageSize).map(r=>`<button class="heritage-card" data-id="${esc(r.id)}" aria-label="查看${esc(r.name)}详情"><span class="list-marker"><svg><use href="#map-icon"/></svg></span><div><h3>${esc(r.name)}</h3><p>${esc(r.era)} · ${esc(shortCategory(r.category))}<br>${esc([r.province,r.city==='待核对'?'':r.city,r.county==='待核对'?'':r.county].filter((v,i,a)=>v&&a.indexOf(v)===i).join(' · '))}${r.coordinates?'':' · 待定位'}</p></div><span>›</span></button>`).join('');$('empty').hidden=rows.length>0;$('page-status').textContent=`${state.page} / ${pages}`;$('prev').disabled=state.page<=1;$('next').disabled=state.page>=pages;$('cards').querySelectorAll('[data-id]').forEach(el=>el.addEventListener('click',()=>showDetail(el.dataset.id)));}
function currentSelection(){return {province:$('province').value,city:$('city').value,county:$('county').value,focus:state.focusId};}
function navigateTo(target){
 $('province').value=target.province||'';syncLocations();$('city').value=target.city||'';syncLocations();$('county').value=target.county||'';update();
}
function showBreadcrumbs(){
 const path=[{label:'全国',target:{}}],s=currentSelection();
 if(s.province)path.push({label:s.province,target:{province:s.province}});
 if(s.city)path.push({label:s.city,target:{province:s.province,city:s.city}});
 if(s.county)path.push({label:s.county,target:{province:s.province,city:s.city,county:s.county}});
 if(s.focus)path.push({label:'文物位置',focus:true});
 $('breadcrumbs').hidden=path.length===1;document.querySelector('.phone').classList.toggle('has-region-path',path.length>1);$('map-back').hidden=path.length===1;
 $('breadcrumbs').innerHTML=path.map((part,i)=>`${i?'<span aria-hidden="true">›</span>':''}<button data-level="${i}" ${i===path.length-1?'aria-current="location"':''}>${esc(part.label)}</button>`).join('');
 $('breadcrumbs').querySelectorAll('button').forEach((el,i)=>el.addEventListener('click',()=>{if(!path[i].focus)navigateTo(path[i].target);}));
 $('breadcrumbs').scrollLeft=$('breadcrumbs').scrollWidth;
}
async function loadBoundary(code){
 if(!state.boundaryFiles.has(String(code)))return null;
 if(!state.boundaryCache.has(code))state.boundaryCache.set(code,fetch(`data/boundaries/${code}.json`).then(r=>{if(!r.ok)throw Error('行政边界加载失败');return r.json();}).catch(error=>{state.boundaryCache.delete(code);throw error;}));
 return state.boundaryCache.get(code);
}
function mapClick(params){
 if(params.data?.id){showDetail(params.data.id);return;}
 const target=params.data?.target||(params.componentType==='geo'?state.mapView?.features.find(f=>f.properties.name===params.name)?.properties.target:null);
 if(target)navigateTo(target);
}
function focusRecord(id){
 const r=state.rows.find(r=>r.id===id);if(!r?.coordinates){showDetail(id);return;}
 if($('province').value!==r.province||$('city').value!==r.city||$('county').value!==r.county){
  navigateTo({province:r.province,city:r.city==='待核对'?'':r.city,county:r.county==='待核对'?'':r.county});
 }
 state.focusId=id;renderMap();
}
function wrapMapName(name,limit=12){
 const letters=Array.from(name),lines=[];
 for(let i=0;i<letters.length;i+=limit)lines.push(letters.slice(i,i+limit).join(''));
 return lines.join('\n');
}
function mapLabelLayout(params){
 const width=state.chart.getWidth(),height=state.chart.getHeight(),rect=params.labelRect;
 const anchorX=params.rect.x+params.rect.width/2,anchorY=params.rect.y+params.rect.height/2;
 const top=document.querySelector('.top').offsetHeight+12,bottom=height-94;
 // Only labels for visible anchors participate; keep their complete text inside the map.
 if(anchorX<0||anchorX>width||anchorY<0||anchorY>height)return {hideOverlap:true};
 return {x:Math.max(10,Math.min(width-rect.width-10,rect.x)),y:Math.max(top,Math.min(bottom-rect.height,rect.y)),align:'left',verticalAlign:'top',moveOverlap:state.labelZoom>=8?'shiftY':undefined,hideOverlap:state.labelZoom<8};
}
function refreshMapLabels(){
 if(!state.chart||!state.mapMarkers)return;
 const zoom=state.chart.getOption().geo[0].zoom,width=state.chart.getWidth(),height=state.chart.getHeight();
 state.labelZoom=zoom;
 const data=state.mapMarkers.map(marker=>{
  const pixel=state.chart.convertToPixel({geoIndex:0},marker.value.slice(0,2));
  const visible=pixel&&pixel[0]>=0&&pixel[0]<=width&&pixel[1]>=0&&pixel[1]<=height;
  return {...marker,label:{show:!!visible&&(!!state.mapField||!!state.focusId||state.mapMarkers.length<=15||zoom>=2)}};
 });
 state.chart.setOption({series:[{data,labelLayout:mapLabelLayout}]});
 $('map').dataset.zoom=String(zoom);
 if(!state.focusId){$('zoom-in').disabled=zoom>=40;$('zoom-out').disabled=zoom<=.7;}
}
function updateFilterCount(){
 const count=String(state.filtered.length),button=$('scope-count');
 button.textContent=count;button.dataset.digits=count.length;
 button.setAttribute('aria-label',`当前筛选范围内 ${count} 处文物，打开国保列表`);
 button.title=`当前筛选范围内 ${count} 处文物`;
}
function openHeritageList(){
 state.page=1;
 const region=$('county').value||$('city').value||$('province').value||'全国';
 $('list-subtitle').textContent=`${region} · ${state.filtered.length.toLocaleString()} 条名录`;
 renderCards();openSheet('results');
}
function scheduleMapLabels(){
 cancelAnimationFrame(state.labelFrame);state.labelFrame=requestAnimationFrame(refreshMapLabels);
}
function resizeMapChrome(){
 if(state.chart){state.chart.resize();scheduleMapLabels();}
 if(state.streetMap){state.streetMap.invalidateSize();placeStreetTooltip();}
}
function placeStreetTooltip(){
 if(!state.focusId||!state.streetMarker)return;
 const tooltip=state.streetMarker.getTooltip(),label=tooltip?.getElement();if(!label)return;
 tooltip.options.offset=L.point(0,-38);tooltip.update();
 const map=$('focus-map').getBoundingClientRect(),box=label.getBoundingClientRect();
 const anchor=state.streetMap.latLngToContainerPoint(state.streetMarker.getLatLng());
 if(anchor.x<0||anchor.x>map.width||anchor.y<0||anchor.y>map.height)return;
 const top=document.querySelector('.top').getBoundingClientRect().bottom+12;
 const controls=document.querySelector('.map-tools').getBoundingClientRect();
 let bottom=map.bottom-94;
 if(box.right>controls.left-10&&box.left<controls.right&&box.bottom>controls.top-10)bottom=Math.min(bottom,controls.top-10);
 const dx=Math.max(map.left+12,Math.min(map.right-box.width-12,box.left))-box.left;
 const dy=Math.max(top,Math.min(bottom-box.height,box.top))-box.top;
 if(Math.abs(dx)>.5||Math.abs(dy)>.5){const offset=L.point(tooltip.options.offset);tooltip.options.offset=offset.add([dx,dy]);tooltip.update();}
}
function renderStreetMap(record){
 if(!record||!window.L){$('focus-map').hidden=true;return;}
 $('focus-map').hidden=false;
 if(!state.streetMap){
  state.streetMap=L.map('focus-map',{zoomControl:false,attributionControl:true,minZoom:3,maxZoom:19});
  state.streetMap.attributionControl.setPrefix(false);
  const tiles=L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,keepBuffer:1,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap contributors</a>'}).addTo(state.streetMap);
  tiles.on('tileload',()=>{state.streetLoaded=true;});
  tiles.on('tileerror',()=>{if(state.focusId&&!state.streetLoaded)$('map-hint').textContent='街道底图暂未加载 · 标记为参考位置';});
  L.control.scale({position:'bottomleft',imperial:false,maxWidth:75}).addTo(state.streetMap);
  state.streetMap.on('moveend zoomend',()=>{placeStreetTooltip();$('zoom-in').disabled=state.streetMap.getZoom()>=19;$('zoom-out').disabled=state.streetMap.getZoom()<=3;});
 }
 state.streetMap.invalidateSize();
 const position=[record.coordinates[1],record.coordinates[0]];
 state.streetMap.setView(position,16,{animate:false});
 if(state.streetMarker)state.streetMarker.remove();
 state.streetMarker=L.marker(position,{icon:L.divIcon({className:'heritage-pin',html:'<span></span>',iconSize:[30,40],iconAnchor:[15,38]}),title:record.name}).addTo(state.streetMap).bindTooltip(esc(record.name),{permanent:true,direction:'top',offset:[0,-38],className:'heritage-tooltip'}).on('click',()=>showDetail(record.id));
 $('zoom-in').disabled=false;$('zoom-out').disabled=false;
 placeStreetTooltip();
}
async function renderMap(){
 if(!state.chart)return;const epoch=++state.mapEpoch,s=currentSelection();if(!s.focus)$('focus-map').hidden=true;showBreadcrumbs();$('map').setAttribute('aria-busy','true');
 const G=HeritageGeo,province=state.admin.find(p=>p.name===s.province),city=province?.cities.find(c=>c.name===s.city),focus=state.rows.find(r=>r.id===s.focus);
 let view=state.china,field='province',fallback=false,bounds;
 try{
  if(province){
   const national=state.china.features.find(f=>String(f.properties.adcode)===province.code),pb=await loadBoundary(province.code);
   view=G.provinceView(province,pb,national);field='city';
   if(s.city){
    if(city){
     const cb=await loadBoundary(city.code);const countyView=G.cityView(province,city,cb||pb);
     const cityFeature=view.features.find(f=>f.properties.name===city.name);
     view=countyView.features.length?countyView:G.collection(cityFeature?[cityFeature]:[national]);field=countyView.features.length?'county':null;
     if(s.county){const f=view.features.find(f=>f.properties.name===s.county);if(f)view=G.collection([f]);else fallback=true;field=null;}
    }else{view=G.collection([national]);field=null;fallback=true;}
   }
  }else{
   view=G.collection(state.china.features.map(f=>{const p=state.admin.find(p=>p.code===String(f.properties.adcode));return p?{...f,properties:{...f.properties,name:p.name,target:{province:p.name,city:'',county:''}}}:f;}));
  }
 }catch(error){
  fallback=true;field=null;const national=state.china.features.find(f=>String(f.properties.adcode)===province?.code);view=national?G.collection([national]):state.china;
 }
 if(epoch!==state.mapEpoch)return;
 const points=state.filtered.filter(r=>r.coordinates);
 if(focus){bounds=G.boundsForPoints([focus.coordinates],.018);field=null;}
 else if(fallback)bounds=G.boundsForPoints(points.map(r=>r.coordinates),.12);
 state.mapView=view;echarts.registerMap('drill-map',view);
 const grouped=field?G.groups(view,state.filtered,field):[],unmapped=field?state.filtered.length-grouped.reduce((n,g)=>n+g.count,0):0;
 const pinRows=focus?[focus]:points;
 state.mapField=field;state.labelZoom=1;
 state.mapMarkers=field?grouped.map(g=>({name:g.name,target:g.target,value:[...g.coordinates,g.count]})):pinRows.map(r=>({name:r.name,id:r.id,value:r.coordinates}));
 const series=field?{type:'scatter',coordinateSystem:'geo',symbolSize:5,data:state.mapMarkers,label:{show:true,position:'top',distance:7,formatter:p=>`${wrapMapName(p.name,9)}\n{count|${p.value[2]} 处}`,fontSize:11,lineHeight:17,color:'#496344',backgroundColor:'#ffffffe8',borderColor:'#ffffff',borderWidth:1,borderRadius:11,padding:[5,9],rich:{count:{fontSize:12,fontWeight:650,lineHeight:21,color:'#326951'}}},labelLayout:mapLabelLayout,labelLine:{show:true,lineStyle:{color:'#8ba481',width:1}},itemStyle:{color:'#78966d',borderColor:'#fff',borderWidth:1},emphasis:{scale:1.2}}:
 {type:'scatter',coordinateSystem:'geo',symbol:focus?'pin':'circle',symbolSize:focus?42:pinRows.length<50?12:8,data:state.mapMarkers,label:{show:!!focus||pinRows.length<=15,position:'top',formatter:p=>wrapMapName(p.name),fontSize:11,lineHeight:17,color:'#3e5b3a',backgroundColor:'#ffffffe0',borderRadius:8,padding:[5,8],distance:8},labelLayout:mapLabelLayout,labelLine:{show:true,lineStyle:{color:'#8ba481',width:1}},itemStyle:{color:focus?'#b77550':'#5a8360',borderColor:'#fff',borderWidth:1.5,shadowBlur:5,shadowColor:'#305b3540'},emphasis:{scale:1.4}};
 state.chart.setOption({animationDuration:300,animationDurationUpdate:0,tooltip:{show:false},geo:{map:'drill-map',roam:true,zoom:1,scaleLimit:{min:.7,max:40},boundingCoords:bounds,layoutCenter:['50%',s.province?'53%':'49%'],layoutSize:s.province?'74%':'94%',label:{show:false},itemStyle:{areaColor:'#f1f3e2',borderColor:'#c1cfb2',borderWidth:.9,shadowColor:'#718a6230',shadowBlur:10},emphasis:{label:{show:false},itemStyle:{areaColor:'#d8e3c8'}},select:{disabled:true}},series:[series]},true);
 refreshMapLabels();
 const level=focus?'文物位置':s.county?'区县':s.city?'城市':s.province?'省份':'全国';
 $('map').dataset.level=level;$('map').dataset.featureCount=String(view.features.length);$('map').setAttribute('aria-busy','false');$('map').setAttribute('aria-label',`${level}地图：${focus?.name||s.county||s.city||s.province||'全国'}，可点击地图继续探索`);
 $('map-hint').textContent=focus?`参考位置 · ${focus.coordinates.map(n=>n.toFixed(5)).join(', ')}`:fallback?'该级边界未匹配 · 展示参考点位':field?`轻点${{province:'省份',city:'城市',county:'区县'}[field]}继续探索${unmapped?' · '+unmapped+' 条地址待核对':''}`:`${points.length} 处参考点位 · 轻点定位${state.filtered.length-points.length?' · '+(state.filtered.length-points.length)+' 处待定位':''}`;
 if(state.filtered.length===0)$('map-hint').textContent='该区域暂无匹配记录 · 可返回上一级';renderStreetMap(focus);
}
function openSheet(id){for(const d of document.querySelectorAll('dialog[open]'))d.close();$(id).showModal();}
function closeSheet(id){
 const returnTo=['types','regions'].includes(id)?state.pickerReturn:null;
 const field=state.pickerField;state.pickerReturn=null;$(id).close();
 if(returnTo){openSheet(returnTo);document.querySelector(`[data-picker="${field}"]`)?.focus();}
}
function syncPickerControls(){
 document.querySelectorAll('[data-picker]').forEach(button=>{
  const select=$(button.dataset.picker),value=select.selectedOptions[0]?.textContent||'';
  button.querySelector('.selection-value').textContent=value;
  button.disabled=select.disabled;button.classList.toggle('is-selected',!!select.value);
 });
}
function openTagPicker(field,returnTo=null){
 state.pickerReturn=returnTo;state.pickerField=field;
 const config={category:{title:'文物类型',empty:'不限类型',values:categories},era:{title:'时代',empty:'不限时代',values:eras},batch:{title:'公布批次',empty:'不限批次',values:numbers.split('').map((_,i)=>String(i+1))}}[field];
 $('types-title').textContent=config.title;$('types').querySelector('[data-close]').setAttribute('aria-label','关闭'+config.title+'选择');$('type-options').setAttribute('aria-label',config.title+'标签');
 const label=value=>!value?config.empty:field==='batch'?'第'+numbers[Number(value)-1]+'批':value;
 $('type-options').innerHTML=['',...config.values].map(value=>`<button class="type-tag" type="button" data-value="${esc(value)}" aria-pressed="${$(field).value===value}">${esc(label(value))}</button>`).join('');
 $('type-options').querySelectorAll('[data-value]').forEach(button=>button.addEventListener('click',()=>{
  $(field).value=button.dataset.value;update();closeSheet('types');
 }));
 openSheet('types');
}
function renderRegionPicker(level){
 const locationFields=['province','city','county'],province=$('province').value,city=$('city').value;
 const path=[{label:'全国',level:'province'},...(province?[{label:province,level:'city'}]:[]),...(city?[{label:city,level:'county'}]:[])];
 $('region-path').hidden=path.length===1;
 $('region-path').innerHTML=path.map(part=>`<button type="button" data-region-level="${part.level}" ${part.level===level?'aria-current="page"':''}>${esc(part.label)}</button>`).join('<span aria-hidden="true">›</span>');
 $('region-path').querySelectorAll('[data-region-level]').forEach(button=>button.addEventListener('click',()=>renderRegionPicker(button.dataset.regionLevel)));
 $('region-options').innerHTML=Array.from($(level).options).filter(option=>!['待核对','跨市','跨区县'].includes(option.value)).map(option=>`<button class="type-tag" type="button" data-region="${esc(option.value)}" aria-pressed="${$(level).value===option.value}">${esc(option.textContent)}</button>`).join('');
 $('region-options').querySelectorAll('[data-region]').forEach(button=>button.addEventListener('click',()=>{
  const target={province,city,county:$('county').value},index=locationFields.indexOf(level);
  target[level]=button.dataset.region;for(const child of locationFields.slice(index+1))target[child]='';
  navigateTo(target);closeSheet('regions');
 }));
 $('regions').scrollTop=0;
}
function openRegionPicker(level=null,returnTo=null){
 state.pickerReturn=returnTo;state.pickerField=level;
 renderRegionPicker(level||($('city').value?'county':$('province').value?'city':'province'));openSheet('regions');
}
function toggleSearch(open){
 const searchBar=document.querySelector('.search-bar');
 searchBar.classList.toggle('is-open',open);$('search').hidden=!open;
 $('search-toggle').setAttribute('aria-expanded',String(open));
 $('search-toggle').setAttribute('aria-label',open?'收起搜索':'搜索文物');
 if(open)$('search').focus();else $('search-toggle').focus();
}
function showDetail(id){const r=state.rows.find(r=>r.id===id);if(!r)return;const description=state.meta.research.featured_descriptions?.find(x=>x.name===r.name);$('detail-body').innerHTML=`<span class="detail-type">全国重点文物保护单位 · 第${numbers[r.batch-1]}批</span><h2 class="detail-title">${esc(r.name)}</h2><div class="tags">${[r.category,r.era].map(t=>`<span class="tag">${esc(shortCategory(t))}</span>`).join('')}</div><section id="wiki-content" class="wiki-content" aria-live="polite"></section><dl class="detail-facts"><dt>所在地</dt><dd>${esc([r.province,r.city,r.county].join(' · '))}</dd><dt>原始地址</dt><dd>${esc(r.address||'未注明')}</dd><dt>位置</dt><dd>${r.coordinates?'第三方参考点位':'待定位 · 暂未匹配可靠坐标'}</dd></dl><div class="detail-actions"><button id="locate-record" class="primary" ${r.coordinates?'':'disabled'}>在地图上查看</button><a class="secondary" href="${esc(r.source)}" target="_blank" rel="noopener" style="text-align:center">原文来源 ↗</a></div><div class="detail-foot"><span>国保名录 · 第${numbers[r.batch-1]}批</span><button id="share-record">分享条目 ↗</button></div>`;openSheet('detail');$('detail').scrollTop=0;HeritageWiki.mount($('wiki-content'),r,description);$('locate-record').addEventListener('click',()=>{focusRecord(r.id);$('detail').close();});$('share-record').addEventListener('click',async()=>{const url=new URL(location.href);url.hash=`unit=${encodeURIComponent(r.id)}`;try{await navigator.clipboard.writeText(url.href);toast('条目链接已复制');}catch{history.replaceState(null,'',url);toast('请复制地址栏链接');}});}
function toast(message){$('toast').textContent=message;$('toast').classList.add('visible');clearTimeout(toast.timer);toast.timer=setTimeout(()=>$('toast').classList.remove('visible'),2600);}
async function main(){try{const [data,china,admin,boundaries]=await Promise.all(['data/heritage.json','data/china.json','data/admin-index.json','data/boundaries/index.json'].map(async url=>{const r=await fetch(url);if(!r.ok)throw new Error('数据加载失败');return r.json();}));state.rows=data.rows;state.meta=data.meta;state.china=china;state.admin=admin;state.boundaryFiles=new Set(boundaries.files);options($('province'),sortNames(state.rows.map(r=>r.province)),'全国');options($('category'),categories,'全部类型');options($('era'),eras,'全部时代');$('batch').innerHTML='<option value="">全部批次</option>'+numbers.split('').map((n,i)=>`<option value="${i+1}">第${n}批</option>`).join('');const initialId=location.hash.startsWith('#unit=')?decodeURIComponent(location.hash.slice(6)):null,params=new URLSearchParams(location.search);for(const f of ['search','province','category','era','batch'])if(params.has(f))$(f).value=params.get(f);syncLocations();if(params.has('city'))$('city').value=params.get('city');syncLocations();if(params.has('county'))$('county').value=params.get('county');$('coverage-note').textContent='整理 5,058 条名录，覆盖 31 个省级行政区。5,016 条有参考点位，42 条待定位。4,756 条可解析到城市，3,709 条可解析到单一区县。';$('batches').innerHTML=data.meta.research.batches.map(b=>`<a class="batch-link" href="${esc(b.source)}" target="_blank" rel="noopener"><span>第${numbers[b.batch-1]}批 · ${b.date}</span><span>${b.count.toLocaleString()} 处 ↗</span></a>`).join('');
if(window.echarts){echarts.registerMap('china',china);state.chart=echarts.init($('map'));state.chart.on('click',mapClick);state.chart.on('georoam',scheduleMapLabels);const mapResize=new ResizeObserver(resizeMapChrome);mapResize.observe($('map'));}else throw new Error('地图组件加载失败，请刷新重试');
document.querySelectorAll('[data-picker]').forEach(button=>button.addEventListener('click',()=>{const field=button.dataset.picker;if(['province','city','county'].includes(field))openRegionPicker(field,'filters');else openTagPicker(field,'filters');}));for(const f of fields)$(f).addEventListener('change',()=>{if(f==='province'){$('city').value='';$('county').value='';syncLocations();}if(f==='city'){$('county').value='';syncLocations();}update();});let timer;$('search').addEventListener('input',()=>{clearTimeout(timer);timer=setTimeout(update,180);});$('filter-open').addEventListener('click',()=>openSheet('filters'));$('region-open').addEventListener('click',()=>openRegionPicker());$('search-toggle').addEventListener('click',()=>toggleSearch($('search').hidden));$('search').addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();toggleSearch(false);}});for(const [id,field] of [['type-open','category'],['era-open','era'],['batch-open','batch']])$(id).addEventListener('click',()=>openTagPicker(field));$('source-open').addEventListener('click',()=>openSheet('info'));$('scope-count').addEventListener('click',openHeritageList);$('map-back').addEventListener('click',()=>{const next=HeritageGeo.parentSelection(currentSelection());if(state.focusId){state.focusId=null;renderMap();}else navigateTo(next);});$('filters-apply').addEventListener('click',()=>$('filters').close());for(const id of ['filters-clear','reset','empty-reset'])$(id).addEventListener('click',reset);for(const d of document.querySelectorAll('dialog')){d.querySelector('[data-close]')?.addEventListener('click',()=>closeSheet(d.id));d.addEventListener('cancel',event=>{if(['types','regions'].includes(d.id)){event.preventDefault();closeSheet(d.id);}});d.addEventListener('click',e=>{if(e.target===d){const b=d.getBoundingClientRect();if(e.clientX<b.left||e.clientX>b.right||e.clientY<b.top||e.clientY>b.bottom)closeSheet(d.id);}});}for(const [id,step] of [['prev',-1],['next',1]])$(id).addEventListener('click',()=>{state.page+=step;renderCards();$('results').scrollTop=0;});for(const [id,factor] of [['zoom-in',1.3],['zoom-out',1/1.3]])$(id).addEventListener('click',()=>{if(state.focusId&&state.streetMap){state.streetMap.setZoom(state.streetMap.getZoom()+(factor>1?1:-1));return;}const zoom=state.chart.getOption().geo[0].zoom;state.chart.setOption({geo:{zoom:Math.max(.7,Math.min(40,zoom*factor))}});refreshMapLabels();});$('loading').hidden=true;update();if(initialId)showDetail(initialId);window.addEventListener('hashchange',()=>{if(location.hash.startsWith('#unit='))showDetail(decodeURIComponent(location.hash.slice(6)));});
}catch(error){$('loading').textContent='地图暂未加载，请刷新重试';console.error(error);}}
main();
