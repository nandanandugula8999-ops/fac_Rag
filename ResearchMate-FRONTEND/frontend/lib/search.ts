import corpus from './data/corpus.json';
export const {faculty,publications,topics,metadata}=corpus;
export type Faculty=typeof faculty[number];
export type Publication=typeof publications[number];
export type Filters={department:string;topic:string;year:string;type:string;name:string;statedOnly:boolean};
export const emptyFilters:Filters={department:'all',topic:'all',year:'all',type:'all',name:'',statedOnly:false};
const stops=new Set('a an the on in for of and or to who works working faculty researchers researcher professors professor find show me research related using with by are is'.split(' '));
export const tokens=(s:string)=>s.toLowerCase().replace(/[^a-z0-9\s]/g,' ').split(/\s+/).filter(x=>x&&!stops.has(x));
const hasPhrase=(s:string,p:string)=>(' '+s.toLowerCase().replace(/[^a-z0-9]/g,' ').replace(/\s+/g,' ')+' ').includes(' '+p.toLowerCase().replace(/[^a-z0-9]/g,' ').replace(/\s+/g,' ')+' ');
export function conceptVector(s:string){return topics.map(t=>[t.name,...t.aliases].some(a=>hasPhrase(s,a))?1:0)}
function cosine(a:number[],b:number[]){let dot=0,aa=0,bb=0;for(let i=0;i<a.length;i++){dot+=a[i]*b[i];aa+=a[i]**2;bb+=b[i]**2;}return aa&&bb?dot/Math.sqrt(aa*bb):0;}
const documents=publications.map(p=>{const f=faculty.find(f=>f.id===p.facultyId)!;const text=[p.title,p.abstract,...p.topics,f.name,...f.aliases,...f.statedExpertise].join(' ');const ts=tokens(text);return {p,f,ts,vector:conceptVector([...p.topics,...f.statedExpertise].join(' '))}});
const avg=documents.reduce((a,d)=>a+d.ts.length,0)/documents.length;
const df=new Map<string,number>();documents.forEach(d=>new Set(d.ts).forEach(t=>df.set(t,(df.get(t)||0)+1)));
export function searchFaculty(query:string,filters:Filters=emptyFilters){
 const qt=tokens(query),qv=conceptVector(query),active=qt.length>0;
 const ranked=documents.filter(({p,f})=>(filters.department==='all'||f.department===filters.department)&&(filters.topic==='all'||(filters.statedOnly?f.statedExpertise:[...f.statedExpertise,...p.topics]).includes(filters.topic))&&(filters.year==='all'||p.year===Number(filters.year))&&(filters.type==='all'||p.type===filters.type)&&(!filters.name||[f.name,...f.aliases].join(' ').toLowerCase().includes(filters.name.toLowerCase()))).map(d=>{
  let bm25=0;qt.forEach(t=>{const tf=d.ts.filter(x=>x===t).length;if(tf){const idf=Math.log(1+(documents.length-(df.get(t)||0)+.5)/((df.get(t)||0)+.5));bm25+=idf*(tf*2.2)/(tf+1.2*(.25+.75*d.ts.length/avg));}});
  const similarity=cosine(qv,d.vector); const stated=cosine(qv,conceptVector(d.f.statedExpertise.join(' ')))>0||qt.some(t=>tokens(d.f.statedExpertise.join(' ')).includes(t));
  return {...d,bm25,similarity,stated,score:0};
 }).filter(d=>!active||(d.bm25>0||d.similarity>0)&&(!filters.statedOnly||d.stated));
 const lexical=[...ranked].filter(x=>x.bm25>0).sort((a,b)=>b.bm25-a.bm25);const conceptual=[...ranked].filter(x=>x.similarity>0).sort((a,b)=>b.similarity-a.similarity);
 ranked.forEach(d=>{const l=lexical.indexOf(d),c=conceptual.indexOf(d);d.score=(l>=0?1/(60+l+1):0)+(c>=0?1/(60+c+1):0)});
 ranked.sort((a,b)=>b.score-a.score||b.p.year-a.p.year);
 const found=new Map<string,{faculty:Faculty;publication:Publication;publications:Publication[];score:number;stated:boolean;match:string}>();
 ranked.forEach(d=>{const prev=found.get(d.f.id);if(prev)prev.publications.push(d.p);else found.set(d.f.id,{faculty:d.f,publication:d.p,publications:[d.p],score:d.score,stated:d.stated,match:active?(d.stated?'Stated expertise':'Related through publications'):'Explore profile'})});
 return [...found.values()];
}
