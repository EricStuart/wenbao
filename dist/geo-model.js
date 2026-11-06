(function(root,factory){const api=factory();if(typeof module==='object'&&module.exports)module.exports=api;else root.HeritageGeo=api;})(typeof globalThis!=='undefined'?globalThis:this,()=>{
  const collection=features=>({type:'FeatureCollection',features});
  const center=f=>f?.properties?.centroid||f?.properties?.center;
  const matches=(feature,node)=>String(feature.properties.adcode)===node.code||feature.properties.name===node.name;
  function named(feature,name,target){return {...feature,properties:{...feature.properties,name,target}};}
  function combined(features,name,code,target){
    if(!features.length)return null;
    const centers=features.map(center).filter(Boolean);
    const coordinates=features.flatMap(f=>f.geometry.type==='MultiPolygon'?f.geometry.coordinates:[f.geometry.coordinates]);
    return {type:'Feature',properties:{name,adcode:code,target,center:centers.length?[centers.reduce((n,c)=>n+c[0],0)/centers.length,centers.reduce((n,c)=>n+c[1],0)/centers.length]:null},geometry:{type:'MultiPolygon',coordinates}};
  }
  function provinceView(province,provinceBoundary,nationalFeature){
    return collection(province.cities.map(city=>{
      const target={province:province.name,city:city.name,county:''};
      if(city.municipality)return named(nationalFeature,city.name,target);
      const feature=provinceBoundary.features.find(f=>matches(f,city));
      if(feature)return named(feature,city.name,target);
      return combined(provinceBoundary.features.filter(f=>city.counties.some(c=>matches(f,c))),city.name,city.code,target);
    }).filter(Boolean));
  }
  function cityView(province,city,boundary){
    return collection(boundary.features.flatMap(f=>{
      const county=city.counties.find(c=>matches(f,c));
      return county?[named(f,county.name,{province:province.name,city:city.name,county:county.name})]:[];
    }));
  }
  function groups(view,rows,field){
    const counts=new Map();for(const r of rows)counts.set(r[field],(counts.get(r[field])||0)+1);
    return view.features.map(f=>({name:f.properties.name,target:f.properties.target,count:counts.get(f.properties.name)||0,coordinates:center(f)})).filter(g=>g.coordinates&&g.count>0);
  }
  function boundsForPoints(points,minSpan=.05){
    if(!points.length)return undefined;
    const xs=points.map(p=>p[0]),ys=points.map(p=>p[1]);const x1=Math.min(...xs),x2=Math.max(...xs),y1=Math.min(...ys),y2=Math.max(...ys);
    const dx=Math.max((x2-x1)*.18,minSpan/2),dy=Math.max((y2-y1)*.18,minSpan/2);
    return [[x1-dx,y2+dy],[x2+dx,y1-dy]];
  }
  function parentSelection(selection){
    if(selection.focus)return {...selection,focus:null};
    if(selection.county)return {...selection,county:''};
    if(selection.city)return {...selection,city:'',county:''};
    return {...selection,province:'',city:'',county:''};
  }
  return {collection,center,matches,provinceView,cityView,groups,boundsForPoints,parentSelection};
});
