import {AtlasScene} from './atlas-scene.js?v=moebius';

const byId = id => document.getElementById(id);
const national = {province:'',city:'',county:''};
const categories = ['古建筑','古遗址','古墓葬','石窟寺及石刻','近现代重要史迹及代表性建筑','其他'];
const eras = ['史前','夏商周','秦汉','魏晋南北朝','隋唐五代','宋辽金夏','元','明','清','近现代'];
const batchNames = '一二三四五六七八';
const number = new Intl.NumberFormat('zh-CN');
const featured = [
  {id:'wb-1-80',image:'ec91eae862196df54855b02b.jpg',note:'唐代木构遗珍'},
  {id:'wb-1-35',image:'6951378275becb752a03e0fe.jpg',note:'敦煌石窟艺术'},
  {id:'wb-1-34',image:'38418be6a1d24d3c728e58e9.jpg',note:'北魏石窟群'},
  {id:'wb-1-100',image:'7e0b78ce623e82eba4a42259.jpg',note:'明清皇家宫殿'},
  {id:'wb-1-107',image:'273a164c59554d30613ec303.jpg',note:'拉萨山巅宫堡'},
  {id:'wb-1-120',image:'9ae7a43981d84538923a4736.jpg',note:'诗人的成都故居'}
];
const state = {
  selection:{...national}, rows:[], rowsById:new Map(), admin:[], boundaries:new Map(),
  filtered:[], scene:null, features:[], labelField:null, points:false, listPage:0,
  featureIndex:0, mapRequest:0, tour:null, detail:null, fallback:false
};

const icon = name => {
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
  const use=document.createElementNS('http://www.w3.org/2000/svg','use');
  use.setAttribute('href','#i-'+name);
  svg.setAttribute('aria-hidden','true');
  svg.append(use);
  return svg;
};

async function json(url) {
  const response=await fetch(url);
  if(!response.ok) throw Error('数据加载失败 '+response.status);
  return response.json();
}

function options(select,values) {
  select.replaceChildren(...values.map(([value,label])=>new Option(label,value)));
}

function regionNodes(target) {
  const province=state.admin.find(node=>node.name===target.province);
  const city=province?.cities.find(node=>node.name===target.city);
  const county=city?.counties.find(node=>node.name===target.county);
  return {province,city,county};
}

function cleanRegion(target) {
  const {province,city,county}=regionNodes(target);
  return {province:province?.name||'',city:city?.name||'',county:county?.name||''};
}

function matchesFilters(row) {
  const category=byId('category-select').value;
  const era=byId('era-select').value;
  const batch=byId('batch-select').value;
  return (!category||row.category===category) && (!era||row.tags?.includes(era)) && (!batch||row.batch===Number(batch));
}

function scopeRows() {
  return state.rows.filter(row=>matchesFilters(row)&&Object.entries(state.selection).every(([key,value])=>!value||row[key]===value));
}

function writeUrl() {
  const url=new URL(location.href);
  for(const [key,value] of Object.entries(state.selection)) {
    if(value) url.searchParams.set(key,value);else url.searchParams.delete(key);
  }
  for(const field of ['category','era','batch']) {
    const value=byId(field+'-select').value;
    if(value) url.searchParams.set(field,value);else url.searchParams.delete(field);
  }
  history.replaceState(null,'',url);
}

function boundary(code) {
  if(!state.boundaryFiles.has(code)) return Promise.resolve(null);
  if(!state.boundaries.has(code)) {
    state.boundaries.set(code,json('data/boundaries/'+code+'.json').catch(error=>{
      state.boundaries.delete(code);
      throw error;
    }));
  }
  return state.boundaries.get(code);
}

function nationalFeatures() {
  return state.china.features.filter(f=>f.properties.name).map(feature=>{
    const region=state.admin.find(node=>node.code===String(feature.properties.adcode));
    if(!region) return feature;
    return {...feature,properties:{...feature.properties,name:region.name,target:{...national,province:region.name}}};
  });
}

async function regionFeatures(target) {
  const geo=window.HeritageGeo;
  const {province,city,county}=regionNodes(target);
  if(!province) return {features:nationalFeatures(),field:'province',fallback:false};
  const nationalFeature=state.china.features.find(f=>String(f.properties.adcode)===province.code);
  try {
    const provinceBoundary=await boundary(province.code);
    if(!provinceBoundary) return {features:[nationalFeature],field:null,fallback:true};
    const cities=geo.provinceView(province,provinceBoundary,nationalFeature).features;
    if(!city) return {features:cities.length?cities:[nationalFeature],field:cities.length?'city':null,fallback:!cities.length};
    const cityBoundary=await boundary(city.code);
    const counties=geo.cityView(province,city,cityBoundary||provinceBoundary).features;
    const cityFeature=cities.find(f=>f.properties.name===city.name)||nationalFeature;
    if(county) {
      const feature=counties.find(f=>f.properties.name===county.name);
      return {features:feature?[{...feature,properties:{...feature.properties,target:null}}]:[],field:null,fallback:!feature};
    }
    return {features:counties.length?counties:[{...cityFeature,properties:{...cityFeature.properties,target:null}}],
      field:counties.length?'county':null,fallback:!counties.length};
  }catch(error){
    console.warn('行政边界暂不可用',error);
    return {features:[nationalFeature],field:null,fallback:true};
  }
}

function renderRegionControls() {
  const {province,city,county}=regionNodes(state.selection);
  const breadcrumb=byId('breadcrumb');
  const parts=[['全国',national]];
  if(province) parts.push([province.name,{...national,province:province.name}]);
  if(city) parts.push([city.name,{...national,province:province.name,city:city.name}]);
  if(county) parts.push([county.name,state.selection]);
  breadcrumb.replaceChildren();
  parts.forEach(([name,target],index)=>{
    if(index) breadcrumb.append(document.createTextNode(' › '));
    const button=document.createElement('button');
    button.textContent=name;
    if(index===parts.length-1) button.setAttribute('aria-current','page');
    button.onclick=()=>{stopTour();void setRegion(target);};
    breadcrumb.append(button);
  });
  const children=county?[]:city?city.counties:province?province.cities:state.admin;
  const field=city?'county':province?'city':'province';
  const prompt=county?'已到区县':city?'选择区县':province?'选择城市':'选择省份';
  options(byId('region-select'),[['',prompt],...children.map(node=>[node.name,node.name])]);
  byId('region-select').disabled=!children.length;
  byId('region-select').onchange=event=>{
    const value=event.target.value;
    if(!value)return;
    stopTour();
    void setRegion({...state.selection,[field]:value});
  };
  byId('scene-name').textContent=county?.name||city?.name||province?.name||'全国地形展台';
}

function updateCounts() {
  state.filtered=scopeRows();
  byId('scope-count').textContent=number.format(state.filtered.length);
  const pointMode=state.points||!state.labelField;
  byId('points').setAttribute('aria-pressed',String(pointMode));
  byId('points').disabled=!state.scene||!state.labelField;
  const level={province:'省份',city:'城市',county:'区县'}[state.labelField];
  const located=state.filtered.filter(r=>r.coordinates).length;
  byId('map-hint').textContent=!state.filtered.length?'暂无匹配文物 · 可调整筛选':
    state.fallback?'该级边界暂不可用 · 可通过名录查看':
    pointMode?number.format(located)+' 处参考点位 · 点击光点查看':
    '拖动旋转 · 滚轮缩放 · 点击'+level+'探索';
  if(byId('catalogue').open) renderList();
}

async function setRegion(target) {
  const request=++state.mapRequest;
  state.selection=cleanRegion(target);
  state.labelField=state.selection.county?null:state.selection.city?'county':state.selection.province?'city':'province';
  renderRegionControls();
  updateCounts();
  writeUrl();
  byId('stage').setAttribute('aria-busy','true');
  const view=await regionFeatures(state.selection);
  if(request!==state.mapRequest) return false;
  state.features=view.features;
  state.labelField=view.field;
  state.fallback=view.fallback;
  updateCounts();
  const labels=view.field?view.features.map(f=>({
    name:f.properties.name,coordinates:window.HeritageGeo.center(f)
  })).filter(label=>label.name):[];
  state.scene?.setView(view.features,state.filtered,labels,state.points||!view.field,view.field==='province');
  byId('stage').setAttribute('aria-busy','false');
  byId('stage').dataset.level=state.selection.county?'county':state.selection.city?'city':state.selection.province?'province':'national';
  return true;
}

function openDialog(id) {
  for(const dialog of document.querySelectorAll('dialog[open]')) {
    if(dialog.id!==id) dialog.close();
  }
  const dialog=byId(id);
  if(!dialog.open) dialog.showModal();
}

function openCatalogue(global=true) {
  stopTour();
  byId('search-global').checked=global;
  byId('query').value='';
  state.listPage=0;
  renderList();
  openDialog('catalogue');
  byId('query').focus();
}

function renderList() {
  const global=byId('search-global').checked;
  const query=byId('query').value.trim().toLocaleLowerCase();
  const source=global?state.rows.filter(matchesFilters):state.filtered;
  const results=source.filter(row=>!query||row.searchText.includes(query));
  const size=8,pages=Math.max(1,Math.ceil(results.length/size));
  state.listPage=Math.min(state.listPage,pages-1);
  byId('list-summary').textContent=(global?'全国':'当前范围')+' · '+number.format(results.length)+' 条';
  byId('list-page').textContent=(state.listPage+1)+' / '+pages;
  byId('list-prev').disabled=state.listPage===0;
  byId('list-next').disabled=state.listPage>=pages-1;
  const list=byId('list-results');
  list.replaceChildren();
  for(const row of results.slice(state.listPage*size,(state.listPage+1)*size)) {
    const button=document.createElement('button');
    button.className='result';
    const text=document.createElement('div'),title=document.createElement('strong'),subtitle=document.createElement('small');
    title.textContent=row.name;
    subtitle.textContent=[row.province,row.city,row.era].filter(Boolean).join(' · ');
    text.append(title,subtitle);
    button.append(icon('pin'),text,icon('arrow'));
    button.onclick=()=>openDetail(row);
    list.append(button);
  }
  if(!results.length){
    const empty=document.createElement('p');
    empty.className='empty';
    empty.textContent='没有找到匹配文物。可以缩短关键词或调整筛选。';
    list.append(empty);
  }
}

function showToast(message) {
  const el=byId('toast');
  el.textContent=message;
  el.hidden=false;
  clearTimeout(state.toastTimer);
  state.toastTimer=setTimeout(()=>{el.hidden=true;},2400);
}

function openDetail(row) {
  if(!row) return;
  stopTour();
  state.detail=row;
  byId('detail-title').textContent=row.name;
  byId('detail-tag').textContent='第'+batchNames[row.batch-1]+'批 · '+row.category;
  byId('detail-address').textContent=[row.address||row.province,row.era].filter(Boolean).join(' · ');
  byId('detail-focus').disabled=!row.coordinates;
  const source=byId('detail-source');
  source.href=row.source;
  source.hidden=!row.source;
  const url=new URL(location.href);
  url.hash='unit='+encodeURIComponent(row.id);
  history.replaceState(null,'',url);
  openDialog('detail');
  byId('detail-scroll').scrollTop=0;
  const content=document.createElement('section');
  content.setAttribute('aria-live','polite');
  byId('detail-content').replaceChildren(content);
  const description=state.meta?.research?.featured_descriptions?.find(item=>item.name===row.name);
  void window.HeritageWiki.mount(content,row,description);
}

async function locate(row) {
  if(!row?.coordinates) return;
  stopTour();
  byId('detail').close();
  if(!state.scene) {
    const url=new URL('map-2d.html',location.href);
    url.hash='unit='+encodeURIComponent(row.id);
    location.href=url.href;
    return;
  }
  for(const field of ['category','era','batch']) byId(field+'-select').value='';
  if(await setRegion(row)){
    state.scene.focus(row,34);
    showToast('已定位 · '+row.name);
  }
}

function displayFeatured(index) {
  state.featureIndex=(index+featured.length)%featured.length;
  const item=featured[state.featureIndex],row=state.rowsById.get(item.id);
  if(!row) return null;
  byId('feature-image').src='assets/wikipedia/'+item.image;
  byId('feature-image').alt=row.name;
  byId('featured-title').textContent=row.name;
  byId('feature-location').textContent=[row.province,row.city].filter(Boolean).join(' · ');
  byId('feature-era').textContent=item.note;
  byId('feature-number').textContent=String(state.featureIndex+1).padStart(2,'0')+' / '+String(featured.length).padStart(2,'0');
  byId('feature-card').setAttribute('aria-label','查看'+row.name+'详情');
  [...byId('feature-dots').children].forEach((button,i)=>{
    button.classList.toggle('current',i===state.featureIndex);
    button.setAttribute('aria-pressed',String(i===state.featureIndex));
  });
  return row;
}

async function chooseFeature(index) {
  stopTour();
  const row=displayFeatured(index);
  if(!row||!state.scene) return;
  if(state.selection.province && !await setRegion(national)) return;
  state.scene.focus(row,62);
}

function renderTourButton(running) {
  const button=byId('tour');
  button.querySelector('use').setAttribute('href',running?'#i-pause':'#i-play');
  button.querySelector('span').textContent=running?'停止巡游':'开始巡游';
  button.setAttribute('aria-pressed',String(running));
}

function stopTour() {
  if(!state.tour) return;
  clearTimeout(state.tour.timer);
  state.tour=null;
  renderTourButton(false);
}

async function startTour() {
  if(state.tour){stopTour();return;}
  if(!state.scene){openCatalogue();return;}
  const tour={remaining:featured.length,index:state.featureIndex,timer:null};
  state.tour=tour;
  renderTourButton(true);
  for(const field of ['category','era','batch']) byId(field+'-select').value='';
  state.points=false;
  if(!await setRegion(national)||state.tour!==tour) return;
  const step=()=>{
    if(state.tour!==tour) return;
    if(tour.remaining--<=0){stopTour();state.scene.fit();return;}
    const row=displayFeatured(tour.index++);
    state.scene.focus(row,52);
    tour.timer=setTimeout(step,4600);
  };
  step();
}

function sceneFallback(message) {
  const status=byId('scene-status');
  status.hidden=false;
  status.replaceChildren(document.createTextNode(message+' '));
  const link=document.createElement('a');
  link.href='map-2d.html'+location.search+location.hash;
  link.textContent='打开二维地图 ↗';
  status.append(link);
  for(const id of ['points','zoom-in','zoom-out','reset-view']) byId(id).disabled=true;
}

function setBindings() {
  for(const dialog of document.querySelectorAll('dialog')){
    dialog.querySelector('[data-close]').onclick=()=>dialog.close();
    dialog.addEventListener('click',event=>{
      if(event.target!==dialog) return;
      const rect=dialog.getBoundingClientRect();
      if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom) dialog.close();
    });
  }
  byId('detail').addEventListener('close',()=>{
    if(location.hash.startsWith('#unit=')){
      const url=new URL(location.href);url.hash='';
      history.replaceState(null,'',url);
    }
  });
  byId('nav-map').onclick=()=>{stopTour();void setRegion(national);};
  byId('nav-list').onclick=()=>openCatalogue();
  byId('nav-about').onclick=()=>{stopTour();openDialog('about');};
  byId('scope-list').onclick=()=>openCatalogue(false);
  byId('search-open').onclick=()=>openCatalogue();
  byId('query').oninput=byId('search-global').onchange=()=>{state.listPage=0;renderList();};
  byId('list-prev').onclick=()=>{state.listPage=Math.max(0,state.listPage-1);renderList();};
  byId('list-next').onclick=()=>{state.listPage++;renderList();};
  byId('detail-focus').onclick=()=>void locate(state.detail);
  byId('detail-share').onclick=async()=>{
    try { await navigator.clipboard.writeText(location.href);showToast('条目链接已复制'); }
    catch { showToast('可从地址栏复制条目链接'); }
  };
  byId('tour').onclick=()=>void startTour();
  byId('feature-card').onclick=()=>openDetail(state.rowsById.get(featured[state.featureIndex].id));
  byId('feature-prev').onclick=()=>void chooseFeature(state.featureIndex-1);
  byId('feature-next').onclick=()=>void chooseFeature(state.featureIndex+1);
  featured.forEach((item,index)=>{
    const button=document.createElement('button');
    button.setAttribute('aria-label','选择'+(state.rowsById.get(item.id)?.name||'馆藏 '+(index+1)));
    button.onclick=()=>void chooseFeature(index);
    byId('feature-dots').append(button);
  });
  byId('reset-view').onclick=()=>{stopTour();state.scene?.fit();};
  byId('zoom-in').onclick=()=>{stopTour();state.scene?.zoom(.77);};
  byId('zoom-out').onclick=()=>{stopTour();state.scene?.zoom(1.29);};
  byId('points').onclick=()=>{
    stopTour();
    state.points=!state.points;
    updateCounts();
    state.scene?.setRows(state.filtered,state.points||!state.labelField);
  };
  for(const field of ['category','era','batch']){
    byId(field+'-select').onchange=()=>{
      stopTour();
      updateCounts();
      state.scene?.setRows(state.filtered,state.points||!state.labelField);
      writeUrl();
    };
  }
  document.addEventListener('keydown',event=>{
    if(event.key==='/'&&!document.querySelector('dialog[open]')&&!event.ctrlKey&&!event.metaKey){
      event.preventDefault();
      openCatalogue();
    }
  });
  addEventListener('hashchange',()=>{
    if(location.hash.startsWith('#unit=')) openDetail(state.rowsById.get(location.hash.slice(6)));
  });
}

async function init() {
  const params=new URLSearchParams(location.search);
  const initialId=location.hash.startsWith('#unit=')?location.hash.slice(6):null;
  try {
    const [heritage,china,admin,index]=await Promise.all([
      json('data/heritage.json'),json('data/china.json'),json('data/admin-index.json'),json('data/boundaries/index.json')
    ]);
    state.rows=heritage.rows.map(row=>({...row,searchText:[
      row.name,row.address,row.province,row.city,row.county,row.era,...(row.aliases||[])
    ].filter(Boolean).join(' ').toLocaleLowerCase()}));
    state.rowsById=new Map(state.rows.map(row=>[row.id,row]));
    state.meta=heritage.meta;
    state.china=china;
    state.admin=admin;
    state.boundaryFiles=new Set(index.files);
    byId('record-count').textContent=number.format(state.rows.length);
    options(byId('category-select'),[['','不限类型'],...categories.map(name=>[name,name.startsWith('近现代')?'近现代史迹':name])]);
    options(byId('era-select'),[['','不限时代'],...eras.map(name=>[name,name])]);
    options(byId('batch-select'),[['','不限批次'],...Array.from(batchNames,(name,index)=>[String(index+1),'第'+name+'批'])]);
    for(const field of ['category','era','batch']){
      const select=byId(field+'-select');
      const value=params.get(field);
      if([...select.options].some(option=>option.value===value)) select.value=value;
    }
    setBindings();
    const initialFeature=displayFeatured(0);
    try {
      state.scene=new AtlasScene(byId('scene'),byId('map-labels'),byId('map-tooltip'),{
        region:target=>{stopTour();void setRegion(target);},
        site:openDetail,
        interaction:()=>stopTour(),
        contextLost:()=>sceneFallback('三维场景暂时中断。'),
        contextRestored:()=>{
          byId('scene-status').hidden=true;
          for(const id of ['zoom-in','zoom-out','reset-view']) byId(id).disabled=false;
          updateCounts();
        }
      });
      byId('scene-status').hidden=true;
    }catch(error){
      console.warn('Three.js 场景不可用',error);
      sceneFallback('此设备暂时无法显示三维地形。');
    }
    await setRegion(Object.fromEntries(Object.keys(national).map(key=>[key,params.get(key)||''])));
    if(!state.selection.province) state.scene?.setFocus(initialFeature);
    if(initialId) openDetail(state.rowsById.get(initialId));
    else if(params.get('search')) {
      byId('query').value=params.get('search');
      openCatalogue();
    }
  }catch(error){
    console.error('观迹初始化失败',error);
    sceneFallback('地图数据暂时无法加载。');
  }
}

if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',init,{once:true});
else void init();
