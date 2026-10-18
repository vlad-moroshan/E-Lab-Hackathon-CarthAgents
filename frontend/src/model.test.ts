import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parseResult,money,hasIssue,fieldIssue,evidence,isCalculated} from './model.ts';
const fixture=(fields:Record<string,number|null>)=>({meta:{company:'Test'},rows:[{kind:'asset',asset_no:'001',year:2025,fields}]});
test('zero stays a populated value while null remains unresolved',()=>{const r=parseResult(fixture({zugang:0,abgang:null})).rows[0];assert.equal(money(r.fields.zugang),'0,00');assert.equal(money(r.fields.abgang),'—');assert.equal(fieldIssue(r,'zugang'),undefined);assert.equal(fieldIssue(r,'abgang'),'unresolved');assert.ok(hasIssue(r));});
test('money is interpreted as integer cents and rejects invalid values',()=>{assert.equal(money(1942596),'19.425,96');assert.equal(money(-100),'-1,00');assert.throws(()=>parseResult(fixture({zugang:1.5})),/integer cents/);assert.throws(()=>parseResult({meta:{},rows:[]}),/no rows/);});
test('field pointers take priority and row pointers retain honest precision',()=>{const r=parseResult(fixture({zugang:1})).rows[0];r.pointer={page:2,bbox:[1,2,3,4]};assert.equal(evidence(r,'zugang').precision,'row');r.pointer={sheet:'Sheet1',cell:'A8',cells:{zugang:'D8'}};assert.equal(evidence(r,'zugang').cell,'D8');assert.equal(evidence(r,'zugang').precision,'cell');});
test('calculated provenance is explicit, not inferred',()=>{const r=parseResult(fixture({zugang:1})).rows[0];assert.equal(isCalculated(r,'zugang'),false);r.provenance={zugang:{type:'calculated',inputs:['a','b']}};assert.equal(isCalculated(r,'zugang'),true);});
test('duplicate asset IDs remain distinct and planted annotations are discarded',()=>{const f=fixture({zugang:0});const r=parseResult({...f,rows:[f.rows[0],f.rows[0]],planted:[{issue:'test'}]});assert.notEqual(r.rows[0].id,r.rows[1].id);assert.equal('planted' in r,false);});

test('versioned extraction values keep per-field evidence and abstentions',()=>{
 const input={schema_version:'1.0',meta:{doc_id:'sample',years:[2025]},rows:[{row_id:'r1',kind:'asset',year:2025,fields:{
  zugang:{amount:0,status:'observed',printed:'0,00',pointer:{page:2,bbox:[1,2,3,4]}},
  abgang:{amount:null,status:'unreadable',reason:'Unreadable crop'}
 }}],findings:[{row_id:'r1',field:'zugang',message:'Printed subtotal mismatch'}]};
 const r=parseResult(input).rows[0];
 assert.equal(r.fields.zugang,0);assert.equal(r.fields.abgang,null);
 assert.equal(fieldIssue(r,'abgang'),'Unreadable crop');
 assert.equal(fieldIssue(r,'zugang'),'Printed subtotal mismatch');
 assert.deepEqual(evidence(r,'zugang'),{page:2,box:[1,2,3,4],cell:undefined,sheet:undefined,precision:'field'});
 assert.equal(typeof input.rows[0].fields.zugang,'object');
});
