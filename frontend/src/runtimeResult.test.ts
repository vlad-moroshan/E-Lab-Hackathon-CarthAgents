import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseResult,evidence} from './model.ts';
import {processDocument} from './processing.ts';
const runtime=()=>({version:1,document:{id:'schedule'},rows:[{id:'r1',kind:'asset',year:2025,asset_no:'001'}],flags:[],values:[
 {row:'r1',field:'ahk_open',value:12345,flags:[],pointer:{page:1,bbox:[1,2,3,4]},trace:{raw:'123,45',unit:'EUR'}},
 {row:'r1',field:'zugang',value:0,flags:[],pointer:{page:2,bbox:[5,6,7,8]},trace:{raw:'',unit:'EUR'}},
 {row:'r1',field:'abgang',value:null,flags:['unreadable'],pointer:null,trace:null}
]});
test('runtime output preserves cents, nulls, flags, raw text and distinct per-field pages',()=>{
 const r=parseResult(runtime()).rows[0];
 assert.equal(r.fields.ahk_open,12345);assert.equal(r.fields.zugang,0);assert.equal(r.fields.abgang,null);
 assert.equal(r.printed?.zugang,'');assert.equal(r.flags?.abgang,'unreadable');
 assert.equal(evidence(r,'ahk_open').page,1);assert.equal(evidence(r,'zugang').page,2);
 assert.equal(evidence(r,'zugang').precision,'field');assert.equal(evidence(r,'abgang').page,undefined);
});
test('missing layouts and duplicate fields cannot masquerade as extraction',()=>{
 assert.throws(()=>parseResult({...runtime(),rows:[],values:[],flags:['needs_layout']}),/needs_layout/);
 const r=runtime();r.values.push(r.values[0]);assert.throws(()=>parseResult(r),/duplicate/);
});
test('runtime response makes its workbook available and surfaces backend diagnostics',async()=>{
 const result=await processDocument(new File(['x'],'x.pdf'),'/api/process',new AbortController().signal,async()=>Response.json({result:runtime(),workbook:{name:'Arbeitsversion.xlsx',base64:btoa('workbook')}}));
 assert.equal(await result.workbook?.text(),'workbook');
 await assert.rejects(processDocument(new File(['x'],'x.pdf'),'/api/process',new AbortController().signal,async()=>Response.json({error:'Document needs a reviewed layout'},{status:422})),/reviewed layout/);
});
