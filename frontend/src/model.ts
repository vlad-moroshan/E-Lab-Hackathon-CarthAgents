import {adaptRuntime} from './runtimeResult.ts';
export type Pointer = {page?:number; bbox?:number[]; sheet?:string; cell?:string; cells?:Record<string,string>; field_bboxes?:Record<string,number[]>};
export type Provenance = {type:'extracted'|'calculated'; formula?:string; inputs?:string[]};
export type Row = {kind:string; year?:number; asset_no?:string; sub_no?:string; class?:string; account?:string; position?:string; name?:string; pointers?:Record<string,Pointer>; sourceUnits?:Record<string,string>; fields:Record<string,number|null>; printed?:Record<string,string>; pointer?:Pointer; flags?:Record<string,string>; provenance?:Record<string,Provenance>; id:string};
export type Result = {meta:{company?:string; doc_id?:string; doc_type?:string; years?:number[]; period_end?:string; format?:string; unit?:string}; rows:Row[]; workbook?:File};
export const FIELDS = [
 ['ahk_open','Opening cost','AHK 01.01.','ahk_01_01'],['zugang','Additions','Zugang','ahk_zugang'],['abgang','Disposals','Abgang','ahk_abgang'],['umbuchung','Transfers','Umbuchung (±)','ahk_umbuchung'],['ahk_close','Closing cost','AHK 31.12.','ahk_31_12'],['kum_afa_open','Opening depreciation','Kum. AfA 01.01.','afa_01_01'],['afa_gj','Annual depreciation','AfA des GJ','afa_gj'],['afa_abgang','Depreciation on disposals','AfA auf Abgang','afa_abgang'],['zuschreibung','Write-ups','Zuschreibung','zuschreibung'],['kum_afa_close','Closing depreciation','Kum. AfA 31.12.','afa_31_12'],['bw_close','Closing book value','Buchwert GJ','bw_31_12_gj'],['bw_prev','Prior book value','Buchwert VJ','bw_31_12_vj'],
 ['afa_gj_plan','Planned depreciation','Planmäßige AfA','afa_gj_plan'],['afa_gj_ausserplan','Unplanned depreciation','Außerplanmäßige AfA','afa_gj_ausserplan'],['afa_umbuchung','Depreciation transfers','AfA Umbuchung','afa_umbuchung'],['abgang_bw','Disposal book value','Abgang Buchwert','abgang_bw'],['net:bew_ahk','Net cost movement','Netto AHK','net_bew_ahk'],['net:bew_wb','Net depreciation movement','Netto WB','net_bew_wb'],
] as const;
export const formatCents=(value:number|null|undefined)=>value==null?'—':new Intl.NumberFormat('de-DE',{maximumFractionDigits:0}).format(value);
export function parseResult(input:unknown):Result {
 if(!input || typeof input!=='object')throw new Error('Choose a JSON object containing meta and rows.');
 const raw=input as Record<string,unknown>;
 const data=(raw.version===1?adaptRuntime(raw):raw) as unknown as Record<string,unknown>;
 if(!data.meta || typeof data.meta!=='object' || Array.isArray(data.meta) || !Array.isArray(data.rows))throw new Error('This file needs a meta object and a rows array, like the corpus key JSONs.');
 if(!data.rows.length)throw new Error('This result has no rows to review.');
 const meta=data.meta as Record<string,unknown>;
 for(const k of ['company','doc_id','doc_type','period_end','format','unit'])if(meta[k]!==undefined&&typeof meta[k]!=='string')throw new Error(`meta.${k} must be text.`);
 const rows=data.rows.map((entry:unknown,i:number)=>{
  if(!entry||typeof entry!=='object')throw new Error(`Row ${i+1} is not an object.`);
  const r=entry as Row;
  if(typeof r.kind!=='string'||!r.fields||typeof r.fields!=='object'||Array.isArray(r.fields))throw new Error(`Row ${i+1} needs a kind and a fields object.`);
  for(const [key,value] of Object.entries(r.fields))if(value!==null&&!Number.isSafeInteger(value))throw new Error(`Row ${i+1}, ${key}: amounts must be integer cents or null.`);
  for(const k of ['asset_no','sub_no','class','account','position','name'] as const)if(r[k]!=null&&typeof r[k]!=='string')throw new Error(`Row ${i+1}: ${k} must be text so identifiers keep their leading zeros.`);
  if(r.printed && (typeof r.printed!=='object'||Object.values(r.printed).some(v=>typeof v!=='string')))throw new Error(`Row ${i+1}: printed values must be text.`);
  const ptr=r.pointer;
  if(ptr && (typeof ptr!=='object'||Array.isArray(ptr)))throw new Error(`Row ${i+1}: pointer must be an object.`);
  if(ptr?.page!==undefined && (!Number.isInteger(ptr.page)||ptr.page<1))throw new Error(`Row ${i+1}: PDF page numbers must start at 1.`);
  if(ptr?.bbox && (!Array.isArray(ptr.bbox)||ptr.bbox.length!==4||ptr.bbox.some(v=>!Number.isFinite(v))))throw new Error(`Row ${i+1}: bbox must contain four coordinates.`);
  if(r.flags && (typeof r.flags!=='object'||Object.values(r.flags).some(v=>typeof v!=='string')))throw new Error(`Row ${i+1}: flags must map field names to explanations.`);
  if(r.provenance)for(const p of Object.values(r.provenance))if(!p||!['extracted','calculated'].includes(p.type))throw new Error(`Row ${i+1}: provenance type must be extracted or calculated.`);
  return {...r,id:`${i}:${r.year??''}:${r.kind}:${r.asset_no??r.class??r.position??''}:${r.sub_no??''}`};
 });
 return {meta:data.meta as Result['meta'],rows};
}
export const hasIssue=(r:Row)=>Object.keys(r.flags??{}).length>0||Object.values(r.fields).some(v=>v===null);
export const fieldIssue=(r:Row,key:string)=>r.flags?.[key]||r.flags?.['*']||(r.fields[key]===null?'unresolved':undefined);
export const isCalculated=(r:Row,key:string)=>r.provenance?.[key]?.type==='calculated';
export const rowLabel=(r:Row)=>r.name || (r.kind==='grand_total'?'Grand total':r.kind==='class_subtotal'?`Asset class ${r.class??''}`:r.kind==='account_subtotal'?`Account ${r.account??''}`:r.kind==='position_subtotal'?`Position ${r.position??''}`:r.kind==='carry_over'?'Carried forward':r.class?`Asset class ${r.class}`:r.position?`Position ${r.position}`:'Schedule row');
export const issueText=(flag:string)=>({glued:'Adjacent values are joined in the source. Review the printed figures before relying on this value.',non_tying:'The source contains a reconciliation discrepancy. The supplied value has been retained.',cut_off:'The source value may be cut off. Check the original document.',transfer_incomplete:'The source transfer information is incomplete.',unresolved:'The result leaves this value unresolved. It has not been replaced with zero.'}[flag]??flag);
export function evidence(r:Row,key:string){
 const direct=r.pointers?.[key]; const p=direct??r.pointer; const box=p?.field_bboxes?.[key]??p?.bbox;
 return {page:p?.page,box,cell:p?.cells?.[key]??p?.cell,sheet:p?.sheet,precision:direct?(p?.sheet?'cell':'field'):p?.field_bboxes?.[key]?'field':p?.cells?.[key]?'cell':'row'};
}
