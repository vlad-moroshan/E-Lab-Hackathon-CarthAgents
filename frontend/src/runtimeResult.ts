import type {Row,Result,Pointer} from './model.ts';

/** Adapt runtime per-value output without losing page/cell precision. */
export function adaptRuntime(input:Record<string,unknown>):Result {
 const doc=input.document as Record<string,unknown>|undefined;
 if(input.version!==1||!doc||typeof doc.id!=='string'||!Array.isArray(input.rows)||!Array.isArray(input.values)||!Array.isArray(input.flags))throw new Error('Invalid backend extraction result.');
 if(!input.rows.length||!input.values.length)throw new Error(`No extracted values to review. ${input.flags.join('; ')}`);
 const rows=new Map<string,Row>();
 for(const item of input.rows){
  if(!item||typeof item.id!=='string'||rows.has(item.id))throw new Error('Invalid or duplicate backend row identity.');
  rows.set(item.id,{...item,fields:{},printed:{},flags:{},pointers:{},sourceUnits:{}});
 }
 for(const v of input.values){
  const row=rows.get(v.row);
  if(!row||typeof v.field!=='string'||Object.hasOwn(row.fields,v.field))throw new Error('Unknown row or duplicate backend value.');
  if(v.value!==null&&!Number.isSafeInteger(v.value))throw new Error('Backend amounts must be integer cents or null.');
  if(!Array.isArray(v.flags)||v.flags.some((f:unknown)=>typeof f!=='string'))throw new Error('Invalid backend value flags.');
  row.fields[v.field]=v.value;
  if(typeof v.trace?.raw==='string')row.printed![v.field]=v.trace.raw;
  if(typeof v.trace?.unit==='string')row.sourceUnits![v.field]=v.trace.unit;
  if(v.pointer){
   const p=v.pointer as Pointer;
   if(p.page!==undefined&&(!Number.isInteger(p.page)||p.page<1||!Array.isArray(p.bbox)||p.bbox.length!==4||p.bbox.some(n=>!Number.isFinite(n))))throw new Error('Invalid backend PDF pointer.');
   if(p.page===undefined&&(typeof p.sheet!=='string'||typeof p.cell!=='string'))throw new Error('Invalid backend Excel pointer.');
   row.pointers![v.field]=p;
  }
  if(v.flags.length)row.flags![v.field]=v.flags.join('; ');
  if(input.flags.length)row.flags!['*']=input.flags.join('; ');
 }
 return {meta:{doc_id:doc.id,company:doc.id,doc_type:'Extracted schedule',years:[...new Set([...rows.values()].flatMap(r=>r.year===undefined?[]:[r.year]))],unit:'EUR'},rows:[...rows.values()]};
}
