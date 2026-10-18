import {parseResult,type Result} from './model.ts';

export function validateSource(file:{name:string;size:number}):void {
 if(!/\.(pdf|xlsx)$/i.test(file.name))throw new Error('Choose a PDF or Excel (.xlsx) source document.');
 if(file.size===0)throw new Error('This file is empty. Choose another document.');
 if(file.size>50*1024*1024)throw new Error('Choose a source document smaller than 50 MB for this demo.');
}

/** POST one source file; accept runtime output plus workbook, or legacy key-style JSON. */
export async function processDocument(file:File,endpoint:string,signal:AbortSignal,request:typeof fetch=fetch):Promise<Result>{
 validateSource(file);
 if(!endpoint.trim())throw new Error('The processing backend is not connected yet. Use a prepared sample or load the matching result JSON under development tools.');
 const body=new FormData();body.append('file',file,file.name);
 const response=await request(endpoint,{method:'POST',body,signal});
 if(!response.ok){let detail='';try{const body=await response.json();if(typeof body.error==='string')detail=body.error;}catch{}throw new Error(detail||`Processing failed (${response.status}). Please retry or check the backend connection.`);}
 let data:unknown;
 try{data=await response.json();}catch{throw new Error('The backend did not return JSON. Check the processing endpoint.');}
 const envelope=data as {result?:unknown;workbook?:{name?:unknown;base64?:unknown}};
 const result=parseResult(envelope?.result??data);
 if(envelope?.workbook){
  const {name,base64}=envelope.workbook;
  if(typeof name!=='string'||!name.endsWith('.xlsx')||typeof base64!=='string')throw new Error('Invalid workbook returned by the backend.');
  const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
  result.workbook=new File([bytes],name,{type:'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'});
 }
 return result;
}
