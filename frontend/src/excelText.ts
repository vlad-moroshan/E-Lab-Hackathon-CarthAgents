/** Read cell values without evaluating formulas or assuming cached results exist. */
export function excelText(value:unknown):string {
 if(value==null)return '';
 if(value instanceof Date)return value.toISOString().slice(0,10);
 if(typeof value==='object'){
  const v=value as Record<string,unknown>;
  if('formula' in v||'sharedFormula' in v)return v.result==null?'[result not saved]':excelText(v.result);
  if(Array.isArray(v.richText))return v.richText.map(x=>String(x?.text??'')).join('');
  if('text' in v)return String(v.text??'');
  if('error' in v)return String(v.error);
  return '';
 }
 return String(value);
}
