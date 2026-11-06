const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const G=require('./dist/geo-model.js');
const read=path=>JSON.parse(fs.readFileSync(path,'utf8'));
const admin=read('dist/data/admin-index.json'),china=read('dist/data/china.json'),rows=read('dist/data/heritage.json').rows;
const boundary=code=>read(`dist/data/boundaries/${code}.json`);
function provinceView(name){const p=admin.find(p=>p.name===name);return [p,G.provinceView(p,boundary(p.code),china.features.find(f=>String(f.properties.adcode)===p.code))];}
test('全国到省：31省均有地级导航边界，子级目标归属正确',()=>{
 for(const p of admin){const [,view]=provinceView(p.name);assert.ok(view.features.length,p.name);for(const f of view.features){assert.equal(f.properties.target.province,p.name);assert.ok(p.cities.some(c=>c.name===f.properties.target.city));}}
});
test('山西→忻州→五台县使用独立市县边界',()=>{
 const [p,view]=provinceView('山西');assert.equal(view.features.length,11);
 const city=p.cities.find(c=>c.name==='忻州市');assert.equal(city.code,'140900');
 const countyView=G.cityView(p,city,boundary(city.code));assert.equal(countyView.features.length,14);
 const wutai=countyView.features.find(f=>f.properties.name==='五台县');assert.equal(wutai.properties.adcode,140922);
 assert.deepEqual(wutai.properties.target,{province:'山西',city:'忻州市',county:'五台县'});
 assert.notDeepEqual(wutai.geometry,view.features.find(f=>f.properties.name==='忻州市').geometry);
});
test('内蒙古与直辖市可逐级导航；北京城市层保留16个区',()=>{
 const [im,imView]=provinceView('内蒙古');assert.equal(imView.features.length,12);
 const [bj,bjView]=provinceView('北京');assert.equal(bjView.features.length,1);assert.equal(bjView.features[0].properties.target.city,'北京市');
 const counties=G.cityView(bj,bj.cities[0],boundary(bj.code));assert.equal(counties.features.length,16);assert.ok(counties.features.some(f=>f.properties.name==='东城区'));
});
test('河南省直辖县级组从真实县界组合，不伪造行政中心点',()=>{
 const [p,view]=provinceView('河南');const group=view.features.find(f=>f.properties.name==='省直辖县级行政区划');assert.ok(group);
 const city=p.cities.find(c=>c.name===group.properties.name);const counties=G.cityView(p,city,boundary(p.code));assert.ok(counties.features.some(f=>f.properties.name==='济源市'));
});
test('城市聚合计数包含未定位条目，不能误算为已定位点数',()=>{
 const [p,view]=provinceView('山西');const selected=rows.filter(r=>r.province===p.name);const groups=G.groups(view,selected,'city');
 for(const group of groups)assert.equal(group.count,selected.filter(r=>r.city===group.name).length);
 assert.ok(groups.reduce((n,g)=>n+g.count,0)<=selected.length);
});
test('文物聚焦采用真实坐标附近的固定小范围；支持逐级返回',()=>{
 const r=rows.find(r=>r.name==='佛光寺');const b=G.boundsForPoints([r.coordinates],.018);
 assert.ok(b[0][0]<r.coordinates[0]&&b[1][0]>r.coordinates[0]);assert.ok(b[0][1]>r.coordinates[1]&&b[1][1]<r.coordinates[1]);assert.ok(Math.abs(b[1][0]-b[0][0]-.018)<1e-10);
 let s={province:'山西',city:'忻州市',county:'五台县',focus:r.id};s=G.parentSelection(s);assert.equal(s.focus,null);assert.equal(s.county,'五台县');s=G.parentSelection(s);assert.equal(s.county,'');s=G.parentSelection(s);assert.equal(s.city,'');s=G.parentSelection(s);assert.equal(s.province,'');
 assert.equal(G.boundsForPoints([]),undefined);
});
