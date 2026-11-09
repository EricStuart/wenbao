import * as THREE from 'three';
import {OrbitControls} from './vendor/three/OrbitControls.js';

const radians = Math.PI / 180;
const longitudeScale = Math.cos(35 * radians);
const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)').matches;
const categoryColors = ['#974a3e','#3f7169','#76527e','#815633','#3e608c','#545d61'];
const categoryNames = ['古建筑','古遗址','古墓葬','石窟寺及石刻','近现代重要史迹及代表性建筑','其他'];
const clamp = THREE.MathUtils.clamp;
const mix = THREE.MathUtils.lerp;

function polygons(feature) {
  return feature.geometry.type === 'Polygon' ? [feature.geometry.coordinates] : feature.geometry.coordinates;
}

function projection(features, rows) {
  const bounds = new THREE.Box2();
  for (const feature of features) {
    for (const polygon of polygons(feature)) {
      for (const [lon, lat] of polygon[0]) bounds.expandByPoint(new THREE.Vector2(lon * longitudeScale, -lat));
    }
  }
  if (bounds.isEmpty()) {
    for (const {coordinates} of rows) {
      if (coordinates) bounds.expandByPoint(new THREE.Vector2(coordinates[0] * longitudeScale, -coordinates[1]));
    }
  }
  if (bounds.isEmpty()) return null;
  const size = bounds.getSize(new THREE.Vector2());
  const center = bounds.getCenter(new THREE.Vector2());
  const scale = 104 / Math.max(size.x, size.y, .04);
  return {
    width: Math.max(8, size.x * scale), depth: Math.max(8, size.y * scale),
    point([lon, lat]) { return [(lon * longitudeScale - center.x) * scale, (-lat - center.y) * scale]; },
    geo(x, z) { return [(x / scale + center.x) / longitudeScale, -(z / scale + center.y)]; }
  };
}

function terrain(x, z, view) {
  const [lon, lat] = view.geo(x, z);
  const plateau = Math.exp(-((lon - 88) ** 2 / 360 + (lat - 31) ** 2 / 50));
  const range = Math.exp(-((lon - 102) ** 2 / 450 + (lat - 37) ** 2 / 94));
  const ridges = Math.sin(x * .21 + Math.sin(z * .12) * 1.8) * Math.cos(z * .18 - x * .10);
  return 0.55 + plateau * 2.7 + ridges ** 2 * (.35 + plateau * 1.45 + range * .5);
}

function ringPoints(ring, view) {
  const points = [];
  for (const coordinate of ring) {
    const [x, z] = view.point(coordinate);
    const previous = points.at(-1);
    if (!previous || Math.hypot(x - previous.x, z - previous.y) > .045) points.push(new THREE.Vector2(x, -z));
  }
  if (points.length > 3 && points[0].distanceTo(points.at(-1)) < .05) points.pop();
  return points;
}

function area(points) { return Math.abs(THREE.ShapeUtils.area(points)); }

const maxEdgeSquared = 12;

function addTriangle(a, b, c, positions) {
  const ab = a.distanceToSquared(b), bc = b.distanceToSquared(c), ca = c.distanceToSquared(a);
  const longest = Math.max(ab, bc, ca);
  if (longest < maxEdgeSquared) {
    positions.push(a.x,a.y,b.x,b.y,c.x,c.y);
    return;
  }
  if (longest === bc) [a,b,c] = [b,c,a];
  else if (longest === ca) [a,b,c] = [c,a,b];
  const center = a.clone().lerp(b,.5);
  addTriangle(a,center,c,positions);
  addTriangle(center,b,c,positions);
}

function addRim(a, b, view, walls) {
  if (a.distanceToSquared(b) >= maxEdgeSquared) {
    const center = a.clone().lerp(b,.5);
    addRim(a,center,view,walls);
    addRim(center,b,view,walls);
    return;
  }
  const h1=terrain(a.x,-a.y,view), h2=terrain(b.x,-b.y,view);
  walls.push(a.x,h1,-a.y,b.x,h2,-b.y,a.x,-1.55,-a.y, a.x,-1.55,-a.y,b.x,h2,-b.y,b.x,-1.55,-b.y);
}

function buffer(positions, colors, normals=false) {
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));
  if (colors) geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3));
  if(normals) geometry.computeVertexNormals();
  return geometry;
}

function makeLand(feature, view) {
  const surface = [], walls = [], colors = [], normals = [];
  const low = new THREE.Color('#9dbeb1');
  const middle = new THREE.Color('#e7c699');
  const high = new THREE.Color('#ce999c');
  const shade = new THREE.Color();
  const normal = new THREE.Vector3();
  const normalStep = .15;
  for (const polygon of polygons(feature)) {
    const outer = ringPoints(polygon[0],view);
    if (outer.length < 3 || area(outer) < .004) continue;
    const holes = polygon.slice(1).map(ring=>ringPoints(ring,view)).filter(ring=>ring.length >= 3 && area(ring) >= .004);
    const vertices = [...outer,...holes.flat()];
    const triangles = THREE.ShapeUtils.triangulateShape(outer,holes);
    const flat = [];
    for (const [a,b,c] of triangles) addTriangle(vertices[a],vertices[b],vertices[c],flat);
    for (let i=0;i<flat.length;i+=2) {
      const x=flat[i], z=-flat[i+1], y=terrain(x,z,view);
      surface.push(x,y,z);
      // Sample the shared height field so lighting stays continuous across faces and regions.
      const dx = terrain(x+normalStep,z,view) - terrain(x-normalStep,z,view);
      const dz = terrain(x,z+normalStep,view) - terrain(x,z-normalStep,view);
      normal.set(-dx,2*normalStep,-dz).normalize();
      normals.push(normal.x,normal.y,normal.z);
      const elevation = clamp((y-.43)/4.5,0,1);
      shade.copy(low).lerp(middle,clamp(elevation*2.7,0,1)).lerp(high,clamp(elevation*1.45-.45,0,1));
      colors.push(shade.r,shade.g,shade.b);
    }
    for (const ring of [outer,...holes]) {
      for (let i=0;i<ring.length;i++) {
        addRim(ring[i],ring[(i+1)%ring.length],view,walls);
      }
    }
  }
  if (!surface.length) return null;
  const surfaceGeometry = buffer(surface,colors);
  surfaceGeometry.setAttribute('normal',new THREE.Float32BufferAttribute(normals,3));
  const roof = new THREE.Mesh(surfaceGeometry, new THREE.MeshStandardMaterial({
    vertexColors:true, roughness:1, emissive:'#000000'
  }));
  roof.userData.feature = feature;
  const rim = new THREE.Mesh(buffer(walls,null,true),new THREE.MeshStandardMaterial({
    color:'#9a8ca4', roughness:1, side:THREE.DoubleSide
  }));
  const group = new THREE.Group();
  group.add(rim,roof);
  return {group,roof};
}

function provinceBorders(features, view) {
  const edges = new Map();
  for (const feature of features) {
    for (const polygon of polygons(feature)) {
      for (const ring of polygon) {
        for (let i=1; i<ring.length; i++) {
          const a = ring[i-1], b = ring[i];
          const from = a.join(','), to = b.join(',');
          if (from === to) continue;
          const key = from < to ? `${from};${to}` : `${to};${from}`;
          const edge = edges.get(key);
          if (!edge) edges.set(key,{a,b,feature,shared:false});
          else if (edge.feature !== feature) edge.shared = true;
        }
      }
    }
  }

  const positions = [];
  for (const {a,b,shared} of edges.values()) {
    if (!shared) continue;
    for (const coordinate of [a,b]) {
      const [x,z] = view.point(coordinate);
      positions.push(x,terrain(x,z,view)+.065,z);
    }
  }
  return new THREE.LineSegments(buffer(positions),new THREE.LineBasicMaterial({
    color:'#4c5168',transparent:true,opacity:.63,depthWrite:false,toneMapped:false
  }));
}

function disposeChildren(group) {
  while (group.children.length) {
    const child=group.children[0];
    group.remove(child);
    child.traverse(object=>{
      object.geometry?.dispose();
      object.material?.dispose();
    });
  }
}

function stageDecoration() {
  const surface = new THREE.Mesh(new THREE.PlaneGeometry(152,152),new THREE.ShaderMaterial({
    transparent:true, depthWrite:false,
    vertexShader:'varying vec2 vUv; void main(){vUv=uv;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
    fragmentShader:'varying vec2 vUv; void main(){float d=length((vUv-.5)*2.);float a=.20*(1.-smoothstep(.10,.81,d));gl_FragColor=vec4(.41,.47,.57,a);}'
  }));
  surface.rotation.x=-Math.PI/2;
  surface.position.y=-2.6;
  return surface;
}

function dustField() {
  let seed=98765;
  const next=()=>{ seed=(1664525*seed+1013904223)>>>0; return seed/4294967296; };
  const vertices=[], phases=[];
  for(let i=0;i<65;i++){
    vertices.push((next()-.5)*150, next()*17-1, (next()-.5)*116);
    phases.push(next()*6.283);
  }
  const geometry=new THREE.BufferGeometry();
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(vertices,3));
  geometry.setAttribute('phase',new THREE.Float32BufferAttribute(phases,1));
  const material=new THREE.ShaderMaterial({
    uniforms:{time:{value:0},pixelRatio:{value:1}},transparent:true,depthWrite:false,
    vertexShader:'attribute float phase; uniform float time; uniform float pixelRatio; varying float a; void main(){vec3 p=position;p.y+=.7*sin(time*.36+phase);p.x+=sin(time*.13+phase);vec4 m=modelViewMatrix*vec4(p,1.);gl_Position=projectionMatrix*m;gl_PointSize=clamp(235./-m.z,1.,3.4)*pixelRatio;a=.15+.24*(.5+.5*sin(phase+time*.66));}',
    fragmentShader:'varying float a; void main(){float r=length(gl_PointCoord-.5)*2.;gl_FragColor=vec4(.39,.36,.46,.54*a*(1.-smoothstep(0.,1.,r)));}'
  });
  return new THREE.Points(geometry,material);
}

function signal() {
  return new THREE.Mesh(new THREE.OctahedronGeometry(.42),new THREE.MeshStandardMaterial({
    color:'#a54e40',emissive:'#9e4837',emissiveIntensity:.23,roughness:1
  }));
}

export class AtlasScene {
  constructor(container, labels, tooltip, actions) {
    this.container=container;
    this.labelContainer=labels;
    this.tooltip=tooltip;
    this.actions=actions;
    this.scene=new THREE.Scene();
    this.camera=new THREE.PerspectiveCamera(41,1,.1,700);
    this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'high-performance'});
    this.renderer.setPixelRatio(Math.min(devicePixelRatio,1.65));
    this.renderer.toneMapping=THREE.ACESFilmicToneMapping;
    this.renderer.toneMappingExposure=1.04;
    this.renderer.setClearColor(0x000000,0);
    this.renderer.domElement.setAttribute('aria-label','三维地形，可拖动旋转和缩放');
    container.append(this.renderer.domElement);
    this.controls=new OrbitControls(this.camera,this.renderer.domElement);
    this.controls.enableDamping=!reducedMotion;
    this.controls.dampingFactor=.12;
    this.controls.rotateSpeed=.55;
    this.controls.minPolarAngle=.16;
    this.controls.maxPolarAngle=1.36;
    this.controls.minDistance=9;
    this.controls.maxDistance=340;
    this.controls.enablePan=true;
    this.controls.target.set(0,0,0);
    this.camera.position.set(6,74,119);
    this.controls.update();
    this.controls.addEventListener('start',()=>{this.flight=null;this.homeView=false;this.actions.interaction();});
    this.scene.add(new THREE.HemisphereLight('#fff1dd','#878aa6',1.55));
    const sun=new THREE.DirectionalLight('#ffe6ca',2.25);
    sun.position.set(-49,73,43);
    const rim=new THREE.DirectionalLight('#d6deff',.55);
    rim.position.set(52,26,-63);
    this.scene.add(sun,rim,stageDecoration());
    this.dust=dustField();
    this.dust.material.uniforms.pixelRatio.value=this.renderer.getPixelRatio();
    this.scene.add(this.dust);
    this.land=new THREE.Group();
    this.pins=new THREE.Group();
    this.scene.add(this.land,this.pins);
    this.signal=signal();
    this.signal.visible=false;
    this.scene.add(this.signal);
    this.raycaster=new THREE.Raycaster();
    this.pointer=new THREE.Vector2();
    this.targets=[];
    this.labels=[];
    this.rows=[];
    this.pinLabels=[];
    this.pinLabelElements=[];
    this.casterTargets=[];
    this.projected=new THREE.Vector3();
    this.renderer.domElement.addEventListener('pointerdown',e=>{this.press={x:e.clientX,y:e.clientY};});
    this.renderer.domElement.addEventListener('pointerup',e=>this.select(e));
    this.renderer.domElement.addEventListener('pointermove',e=>this.hover(e));
    this.renderer.domElement.addEventListener('pointerleave',()=>this.clearHover());
    this.renderer.domElement.addEventListener('webglcontextlost',event=>{
      event.preventDefault();
      this.renderer.setAnimationLoop(null);
      this.actions.contextLost();
    });
    this.renderer.domElement.addEventListener('webglcontextrestored',()=>{
      this.actions.contextRestored();
      this.renderer.setAnimationLoop(time=>this.frame(time));
    });
    this.resizeObserver=new ResizeObserver(()=>this.resize());
    this.resizeObserver.observe(container);
    this.resize();
    this.renderer.setAnimationLoop(time=>this.frame(time));
  }

  resize() {
    const width=this.container.clientWidth, height=this.container.clientHeight;
    if (!width || !height) return;
    this.camera.aspect=width/height;
    this.camera.updateProjectionMatrix();
    this.renderer.setSize(width,height,false);
    if(this.view && this.homeView) this.fit(false);
  }

  setView(features, rows, labels, pointMode, showProvinceBorders) {
    this.clearHover();
    disposeChildren(this.land);
    this.targets=[];
    this.view=projection(features,rows);
    this.pointMode=pointMode;
    this.labels=[];
    this.labelContainer.replaceChildren();
    this.pinLabelElements=[];
    if(!this.view) {
      this.setRows(rows,pointMode);
      this.setFocus(null);
      return;
    }
    for (const feature of features) {
      const object=makeLand(feature,this.view);
      if(!object) continue;
      this.land.add(object.group);
      if(feature.properties.target) this.targets.push(object);
    }
    if(showProvinceBorders) this.land.add(provinceBorders(features,this.view));
    for(const label of labels) this.addLabel(label);
    this.setRows(rows,pointMode);
    this.setFocus(null);
    this.revealStart=performance.now();
    this.fit(true);
  }

  addLabel({name,coordinates}) {
    if(!coordinates) return;
    const element=document.createElement('span');
    element.className='map-label';
    element.textContent=name;
    this.labelContainer.append(element);
    const [x,z]=this.view.point(coordinates);
    this.labels.push({element,position:new THREE.Vector3(x,terrain(x,z,this.view)+.42,z)});
  }

  setRows(rows,pointMode) {
    disposeChildren(this.pins);
    this.pointMode=pointMode;
    this.rows=[];
    this.pinLabels=[];
    this.pinMesh=null;
    if(!this.view) return;
    const extentX=this.view.width*.76+5, extentZ=this.view.depth*.76+5;
    const items=[];
    for(const row of rows){
      if(!row.coordinates) continue;
      const [x,z]=this.view.point(row.coordinates);
      if(Math.abs(x)>extentX||Math.abs(z)>extentZ) continue;
      items.push({row,x,z});
    }
    if(!items.length) return;
    const size=pointMode ? (items.length>500?.29:.60) : .15;
    const material=new THREE.MeshBasicMaterial({color:'#ffffff',toneMapped:false});
    this.pinMesh=new THREE.InstancedMesh(new THREE.IcosahedronGeometry(size,0),material,items.length);
    const positions=[], colors=[];
    const helper=new THREE.Object3D(), color=new THREE.Color();
    items.forEach(({row,x,z},index)=>{
      const y=terrain(x,z,this.view)+size+.12;
      helper.position.set(x,y,z);
      helper.scale.setScalar(pointMode?1:0.84+(index%5)*.07);
      helper.updateMatrix();
      this.pinMesh.setMatrixAt(index,helper.matrix);
      color.set(categoryColors[Math.max(0,categoryNames.indexOf(row.category))]);
      if(!pointMode) color.multiplyScalar(.74);
      this.pinMesh.setColorAt(index,color);
      positions.push(x,y,z);
      colors.push(color.r,color.g,color.b);
      this.rows.push(row);
      if(pointMode) this.pinLabels.push({name:row.name,position:new THREE.Vector3(x,y+size+.23,z)});
    });
    this.pins.add(this.pinMesh);
    const cloud=buffer(positions,colors);
    const glow=new THREE.Points(cloud,new THREE.PointsMaterial({
      size:pointMode?.65:.34,vertexColors:true,transparent:true,opacity:.13,depthWrite:false,toneMapped:false
    }));
    this.pins.add(glow);
  }

  setFocus(row) {
    this.focusLabel?.element.remove();
    this.focusLabel=null;
    this.signal.visible=Boolean(row?.coordinates && this.view);
    if(!this.signal.visible) return;
    const [x,z]=this.view.point(row.coordinates);
    const y=terrain(x,z,this.view);
    this.signal.position.set(x,y+1.2,z);
    const element=document.createElement('span');
    element.className='map-label featured-label';
    element.textContent=row.name;
    this.labelContainer.append(element);
    this.focusLabel={element,position:new THREE.Vector3(x,y+3,z)};
  }

  fit(animate=true) {
    if(!this.view) return;
    const distance=Math.max(this.view.width/Math.max(.65,this.camera.aspect),this.view.depth*.8+12)/(2*Math.tan(41*radians/2))*1.12;
    const target=new THREE.Vector3(0,.2,0);
    const position=new THREE.Vector3(.045,.65,.76).normalize().multiplyScalar(distance);
    this.homeView=true;
    this.moveTo(position,target,animate ? 800 : 0);
  }

  moveTo(position,target,duration) {
    if(reducedMotion || !duration){
      this.camera.position.copy(position);
      this.controls.target.copy(target);
      this.controls.update();
      this.flight=null;
      return;
    }
    this.flight={from:this.camera.position.clone(),to:position,targetFrom:this.controls.target.clone(),targetTo:target,start:performance.now(),duration};
  }

  focus(row,distance=44) {
    this.setFocus(row);
    if(!this.signal.visible) return;
    this.homeView=false;
    const target=this.signal.position.clone();
    target.y=1.3;
    const position=target.clone().add(new THREE.Vector3(-.11,.62,.77).normalize().multiplyScalar(distance));
    this.moveTo(position,target,1250);
  }

  zoom(factor) {
    this.homeView=false;
    const target=this.controls.target.clone();
    const delta=this.camera.position.clone().sub(target);
    delta.setLength(clamp(delta.length()*factor,this.controls.minDistance,this.controls.maxDistance));
    this.moveTo(target.clone().add(delta),target,250);
  }

  getHit(event) {
    const rect=this.renderer.domElement.getBoundingClientRect();
    this.pointer.set((event.clientX-rect.left)/rect.width*2-1,1-(event.clientY-rect.top)/rect.height*2);
    this.raycaster.setFromCamera(this.pointer,this.camera);
    if(this.pointMode && this.pinMesh) {
      const point=this.raycaster.intersectObject(this.pinMesh)[0];
      if(point) return {row:this.rows[point.instanceId]};
    }
    const hit=this.raycaster.intersectObjects(this.targets.map(object=>object.roof))[0];
    if(hit) return {feature:hit.object.userData.feature,object:hit.object};
    return null;
  }

  select(event) {
    if(event.button!==0 || !this.press || Math.hypot(event.clientX-this.press.x,event.clientY-this.press.y)>6) return;
    this.press=null;
    const hit=this.getHit(event);
    if(hit?.row) this.actions.site(hit.row);
    else if(hit?.feature) this.actions.region(hit.feature.properties.target);
  }

  hover(event) {
    if(event.buttons || event.pointerType==='touch' || (performance.now()-(this.lastHover||0))<70) return;
    this.lastHover=performance.now();
    const hit=this.getHit(event);
    this.clearHover();
    if(!hit) return;
    if(hit.object) {
      this.highlight=hit.object;
      hit.object.material.emissive.set('#b26355');
      hit.object.material.emissiveIntensity=.3;
    }
    this.renderer.domElement.style.cursor='pointer';
    const rect=this.container.getBoundingClientRect();
    this.tooltip.style.left=Math.max(4,Math.min(rect.width-150,event.clientX-rect.left+12))+'px';
    this.tooltip.style.top=Math.max(4,event.clientY-rect.top-27)+'px';
    this.tooltip.textContent=hit.row?.name || hit.feature.properties.name;
    this.tooltip.hidden=false;
  }

  clearHover() {
    this.highlight?.material.emissive.set('#000000');
    this.highlight=null;
    this.tooltip.hidden=true;
    this.renderer.domElement.style.cursor='';
  }

  frame(time) {
    const sec=time*.001;
    this.dust.material.uniforms.time.value=reducedMotion?0:sec;
    if(this.flight){
      const {from,to,targetFrom,targetTo,start,duration}=this.flight;
      const progress=clamp((time-start)/duration,0,1);
      const t=progress*progress*(3-2*progress);
      this.camera.position.lerpVectors(from,to,t);
      this.controls.target.lerpVectors(targetFrom,targetTo,t);
      if(progress===1) this.flight=null;
    }
    this.controls.update();
    if(this.revealStart) {
      const progress=reducedMotion?1:clamp((time-this.revealStart)/580,0,1);
      this.land.scale.y=mix(.62,1,1-(1-progress)**3);
      if(progress===1) this.revealStart=null;
    }
    if(this.signal.visible && !reducedMotion){
      this.signal.rotation.y=sec*.7;
    }
    this.renderer.render(this.scene,this.camera);
    this.placeLabels();
  }

  placeLabels(){
    const width=this.container.clientWidth,height=this.container.clientHeight;
    const boxes=[];
    const closeUp=this.pointMode && this.camera.position.distanceToSquared(this.controls.target)<34**2;
    const measure=name=>Math.min(width-8,name.length*(width<600?10:12)+12);
    const project=(position,w)=>{
      this.projected.copy(position).project(this.camera);
      const x=(this.projected.x+1)*width/2;
      const y=(1-this.projected.y)*height/2;
      if(this.projected.z>1 || this.projected.z< -1 || x<10 || x>width-10 || y<20 || y>height-12) return null;
      const left=clamp(x,w/2+3,width-w/2-3);
      if(boxes.some(box=>Math.abs(left-box.x)<(w+box.w)/2&&Math.abs(y-box.y)<21)) return null;
      const box={x:left,y,w};
      boxes.push(box);
      return box;
    };
    const place=(element,box)=>{
      element.hidden=!box;
      if(!box) return;
      element.style.left=box.x+'px';
      element.style.top=box.y+'px';
    };
    const labels=this.focusLabel?[this.focusLabel,...this.labels]:this.labels;
    for(const {position,element} of labels){
      const visible=!closeUp || element===this.focusLabel?.element;
      place(element,visible?project(position,measure(element.textContent)):null);
    }
    let used=0;
    if(closeUp) for(const {name,position} of this.pinLabels){
      if(name===this.focusLabel?.element.textContent) continue;
      const box=project(position,measure(name));
      if(!box) continue;
      let element=this.pinLabelElements[used];
      if(!element){
        element=document.createElement('span');
        element.className='map-label pin-label';
        this.pinLabelElements.push(element);
        this.labelContainer.append(element);
      }
      if(element.textContent!==name) element.textContent=name;
      place(element,box);
      if(++used===36) break;
    }
    for(const element of this.pinLabelElements.slice(used)) element.hidden=true;
  }
}
