import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {createFacultyClient, validateResponse, safeSourceUrl, doiUrl} from '../integration/faculty-assistant/api.js';
const real=JSON.parse(fs.readFileSync('datasets/openalex/01-machine-learning.json','utf8'));
const insufficient=JSON.parse(fs.readFileSync('datasets/openalex/08-unrelated-query.json','utf8'));
test('POST contract and unchanged live response mapping',async()=>{
 let request;
 const api=createFacultyClient('https://backend.example.test/',{fetchImpl:async(url,options)=>{request={url,options};return new Response(JSON.stringify(real),{status:200})}});
 assert.deepEqual(await api.search(' machine learning '),real);
 assert.equal(request.url,'https://backend.example.test/api/faculty/search');
 assert.equal(request.options.method,'POST');
 assert.deepEqual(JSON.parse(request.options.body),{query:'machine learning',top_k:10});
 assert.equal(request.options.credentials,'omit');
});
test('insufficient evidence never leaks cards',()=>{
 assert.equal(validateResponse(insufficient).matches.length,0);
 assert.equal(validateResponse({...insufficient,matches:real.matches}).matches.length,0);
});
test('reject malformed responses and fixture data',()=>{
 assert.throws(()=>validateResponse({...real,corpus_source:'fixture'}),{code:'non_live_source'});
 assert.throws(()=>validateResponse({status:'ok',matches:'bad'}),{code:'invalid_response'});
 assert.throws(()=>validateResponse({...real,matches:[{faculty_id:'x',faculty_name:'x',score:'unknown'}]}),{code:'invalid_response'});
});
test('invalid queries do not make network calls',async()=>{
 const api=createFacultyClient('https://backend.example.test',{fetchImpl:()=>{throw Error('must not call')}});
 await assert.rejects(api.search(' '),{code:'validation'});
 await assert.rejects(api.search('topic',{topK:100}),{code:'validation'});
});
test('HTTP failures surface as errors, without fallback faculty',async()=>{
 const api=createFacultyClient('https://backend.example.test',{fetchImpl:async()=>new Response('failure',{status:503})});
 await assert.rejects(api.search('topic'),{code:'http_503'});
});
test('unsafe URLs are not turned into links',()=>{
 assert.equal(safeSourceUrl('javascript:alert(1)'),null);
 assert.equal(safeSourceUrl('/relative'),null);
 assert.equal(doiUrl('10.1234/example'),'https://doi.org/10.1234/example');
 assert.throws(()=>createFacultyClient('https://name:password@example.test'),{code:'configuration'});
});
test('timeout and user cancellation are distinct',async()=>{
 const fetchImpl=(_,options)=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>reject(new DOMException('Aborted','AbortError')),{once:true}));
 const api=createFacultyClient('https://backend.example.test',{fetchImpl,timeoutMs:5});
 await assert.rejects(api.search('topic'),{code:'timeout'});
 const controller=new AbortController();const pending=api.search('topic',{signal:controller.signal});controller.abort();
 await assert.rejects(pending,{name:'AbortError'});
});
