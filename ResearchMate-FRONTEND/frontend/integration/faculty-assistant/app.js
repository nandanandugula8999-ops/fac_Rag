import {createFacultyClient, safeSourceUrl, doiUrl} from './api.js';
const form=document.querySelector('#search-form'), input=document.querySelector('#query'), button=document.querySelector('#search-button'), cancel=document.querySelector('#cancel-button'), status=document.querySelector('#status'), results=document.querySelector('#results'), answer=document.querySelector('#answer'), raw=document.querySelector('#raw-response');
let active=null,sequence=0,client;
const element=(tag,text,className)=>{const node=document.createElement(tag);if(text!==undefined)node.textContent=String(text);if(className)node.className=className;return node};
const asText=(v)=>typeof v==='string'?v:'';
function sourceLink(url,label){const safe=safeSourceUrl(url);if(!safe)return element('span',label+' unavailable','meta');const a=element('a',label);a.href=safe;a.target='_blank';a.rel='noopener noreferrer';return a}
function tags(values,empty='Not provided by the backend'){const box=element('div',undefined,'tags');const list=Array.isArray(values)?values.filter(v=>typeof v==='string'&&v):[];if(!list.length)box.append(element('span',empty,'meta'));else list.forEach(v=>box.append(element('span',v,'tag')));return box}
function section(title,content,extra=''){const s=element('section',undefined,'section '+extra);s.append(element('h3',title),content);return s}
function renderFaculty(match,payload){
 const card=element('article',undefined,'faculty-card'),heading=element('div',undefined,'heading'),identity=element('div');identity.append(element('h2',match.faculty_name));identity.append(element('p',(match.institutions||[]).map(i=>asText(i.name)).filter(Boolean).join(' · ')||'Institution not provided'));heading.append(identity,element('span','Relevance score: '+String(match.score),'score'));card.append(heading);
 card.append(section('Stated expertise',tags(match.stated_topics)));
 const stated=new Set(match.stated_topics||[]);card.append(section('Inferred / publication-derived topics',tags((match.matched_topics||[]).filter(t=>!stated.has(t))),'derived'));
 const why=element('ul',undefined,'reasons');for(const signal of match.signals||[])if(signal.explanation)why.append(element('li',signal.explanation));for(const note of match.notes||[])if(typeof note==='string')why.append(element('li',note));card.append(section('Why this faculty matches',why.childNodes.length?why:element('p','No explanation provided by the backend.','meta')));
 const pubs=element('ul',undefined,'publications');for(const p of match.supporting_publications||[]){const li=element('li');li.append(element('strong',p.title||'Untitled publication'),element('div',p.year==null?'Year unavailable':'Publication year: '+p.year,'meta'),sourceLink(doiUrl(p.doi)||p.citation_url,'DOI / source'));pubs.append(li)}card.append(section('Supporting publications',pubs.childNodes.length?pubs:element('p','No publications provided.','meta')));
 const evidence=element('div');for(const e of match.evidence||[]){const quote=element('div',undefined,'evidence');quote.append(element('h3',e.title||'Supporting passage'),element('p',e.quote||'Quote unavailable'),element('p',e.year==null?'Year unavailable':'Year: '+e.year,'meta'),sourceLink(doiUrl(e.doi)||e.source_url,'View source'));const linked=(payload.claims||[]).filter(c=>(c.citations||[]).some(citation=>citation.faculty_id===match.faculty_id&&(citation.quote===e.quote||(citation.work_id&&citation.work_id===e.work_id))));const supported=linked.length>0&&linked.every(c=>c.status==='supported');quote.append(element('p',supported?'✓ Associated claim verified by backend':'Verification not confirmed for this passage','verification '+(supported?'verified':'unverified')));evidence.append(quote)}card.append(section('Evidence passages',evidence.childNodes.length?evidence:element('p','No evidence passage provided.','meta')));
 card.append(element('p','Expertise classification: '+(match.expertise_type||'Not provided'),'meta'));
 return card;
}
function render(payload){
 raw.hidden=false;document.querySelector('#raw-json').textContent=JSON.stringify(payload,null,2);
 if(payload.status==='insufficient_evidence'){status.textContent='No sufficient faculty evidence found for this research topic.';for(const w of payload.warnings||[])status.append(element('p',w,'warning'));return}
 status.textContent=payload.matches.length+' faculty results · Source: '+payload.corpus_source;
 answer.hidden=false;answer.append(element('h2','Research evidence'),element('p',payload.answer_text||'No answer text provided.'));
 answer.append(element('p',payload.verified===true?'✓ Answer verified by backend':'Answer verification not confirmed','verification '+(payload.verified===true?'verified':'unverified')));
 for(const w of payload.warnings||[])answer.append(element('p',w,'warning'));
 for(const match of payload.matches)results.append(renderFaculty(match,payload));
}
async function search(query){const id=++sequence;active?.abort();active=new AbortController();const controller=active;results.replaceChildren();answer.replaceChildren();answer.hidden=true;raw.hidden=true;status.className='status loading';status.textContent='Searching academic sources and checking evidence…';results.setAttribute('aria-busy','true');button.disabled=true;cancel.hidden=false;
 try{const payload=await client.search(query,{topK:10,signal:controller.signal});if(id!==sequence)return;status.className='status';render(payload)}catch(error){if(id!==sequence)return;status.className=controller.signal.aborted?'status':'status error';status.textContent=controller.signal.aborted?'Search cancelled.':error.message}finally{if(id===sequence){button.disabled=false;cancel.hidden=true;results.setAttribute('aria-busy','false');active=null}}
}
try{client=createFacultyClient(window.FACULTY_CONFIG?.apiBaseUrl)}catch(error){status.className='status error';status.textContent=error.message;button.disabled=true}
form.addEventListener('submit',e=>{e.preventDefault();if(client)search(input.value)});
cancel.addEventListener('click',()=>active?.abort());
for(const example of document.querySelectorAll('.examples button'))example.addEventListener('click',()=>{input.value=example.textContent;if(client)search(input.value)});
