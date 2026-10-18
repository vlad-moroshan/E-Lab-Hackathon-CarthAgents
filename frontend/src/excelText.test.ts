import {test} from 'node:test';
import assert from 'node:assert/strict';
import {excelText} from './excelText.ts';
test('source preview distinguishes blank, zero and missing formula caches',()=>{
 assert.equal(excelText(null),'');assert.equal(excelText(0),'0');
 assert.equal(excelText({formula:'A1+1',result:null}),'[result not saved]');
 assert.equal(excelText({formula:'A1+1',result:0}),'0');
 assert.equal(excelText({richText:[{text:'Source '},{text:'value'}]}),'Source value');
 assert.equal(excelText({text:'Reference',hyperlink:'https://example.com'}),'Reference');
});
