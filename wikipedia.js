'use strict';
window.HeritageWiki=(()=>{
 const escape=value=>String(value??'').replace(/[&<>"']/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
 const link=(url,label)=>{
  try{if(!['https:','http:'].includes(new URL(url).protocol))return escape(label);}catch{return escape(label);}
  return `<a href="${escape(url)}" target="_blank" rel="noopener">${escape(label)}</a>`;
 };
 const paragraphs=text=>String(text).split(/\n+/).filter(Boolean).map(p=>`<p>${escape(p)}</p>`).join('');
 function read(id){
  if(!/^[\w-]+$/.test(id))return Promise.reject(Error('Invalid heritage ID'));
  return fetch(`data/wikipedia/${encodeURIComponent(id)}.json`,{cache:'no-cache'}).then(response=>{
   if(response.status===404)return {status:'not-collected'};
   if(!response.ok)throw Error('Local introduction unavailable');
   return response.json();
  });
 }
 async function mount(container,record,fallback){
  container.innerHTML='<p class="wiki-status" role="status">正在读取本地介绍…</p>';
  try{
   const article=await read(record.id);if(!container.isConnected)return;
   if(!article.text){
    container.innerHTML=(fallback?`<div class="wiki-copy">${paragraphs(fallback.description)}</div><p class="wiki-source">${link(fallback.source,'介绍来源 ↗')}</p>`:'')+`<p class="wiki-status">${article.status==='not-collected'?'这处文物的本地介绍尚未收录。':'暂未匹配到可靠的维基百科介绍。'}</p><p class="wiki-source">${link('https://zh.wikipedia.org/w/index.php?search='+encodeURIComponent(record.name),'在维基百科查找 ↗')}</p>`;
    return;
   }
   const isWiki=article.status==='ready';
   const photo=article.image,validPhoto=photo&&/^assets\/wikipedia\/[a-f0-9]+\.(jpg|png|webp)$/.test(photo.path);
   container.innerHTML=`${validPhoto?`<figure class="wiki-photo"><a href="${escape(photo.path)}" target="_blank" rel="noopener" aria-label="查看${escape(record.name)}完整图片"><img src="${escape(photo.path)}" alt="${escape(record.name)}，图片：${escape(photo.author)}" width="${Number(photo.width)||800}" height="${Number(photo.height)||600}" decoding="async"></a><figcaption>${photo.subject?escape(photo.subject)+'<br>':''}${link(photo.sourceUrl,'图片来源 ↗')} · ${escape(photo.author)}<br>${link(photo.licenseUrl,photo.license)}</figcaption></figure>`:'<p class="wiki-status">图片待补充</p>'}<div class="wiki-heading"><h3>${isWiki?'关于这处文物':'名录简介'}</h3><span>${isWiki?'维基百科':'公布名录'}</span></div><div class="wiki-copy">${paragraphs(article.text)}</div><div class="wiki-source">${isWiki?`${link(article.revisionUrl||article.sourceUrl,'维基百科 · '+article.title+' ↗')}<br>${escape(article.authors)} · ${link(article.licenseUrl,article.license)} · ${article.editorialNotes?.length?'内容整理':article.shortened?'内容节选':'导言摘录'}`:`${link(article.sourceUrl,'公布名录 · '+article.title+' ↗')}<br>据公布名录整理`}<span class="wiki-snapshot">本地收录 · ${escape(article.retrievedAt?.slice(0,10)||'')}</span></div>`;
   container.querySelector('img')?.addEventListener('error',()=>{
    const figure=container.querySelector('.wiki-photo');if(figure)figure.innerHTML='<p class="wiki-status">本地图片暂不可用</p>';
   },{once:true});
  }catch{
   if(container.isConnected)container.innerHTML='<p class="wiki-status">本地介绍暂未加载，请重新打开详情。</p>';
  }
 }
 return {mount};
})();
