import {excelText} from './excelText';
import {useEffect,useRef,useState} from 'react';
import type {Workbook} from 'exceljs';
import {FileSpreadsheet,LoaderCircle} from 'lucide-react';
function columnName(n:number){let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;}
export default function ExcelViewer({file,sheet,cell}:{file:File|null;sheet?:string;cell?:string}){
 const [loaded,setLoaded]=useState<{file:File;book:Workbook}|null>(null),[error,setError]=useState('');
 const focus=useRef<HTMLTableCellElement>(null),scroll=useRef<HTMLDivElement>(null);
 useEffect(()=>{let active=true;setLoaded(null);setError('');if(!file)return;
  void (async()=>{try{const ExcelJS=await import('exceljs');const book=new ExcelJS.default.Workbook();await book.xlsx.load(await file.arrayBuffer());if(active)setLoaded({file,book});}catch{if(active)setError('This workbook could not be previewed. Open the original source in Excel.');}})();
  return()=>{active=false;};
 },[file]);
 useEffect(()=>{if(focus.current&&scroll.current)scroll.current.scrollLeft=Math.max(0,focus.current.offsetLeft-scroll.current.clientWidth/2+focus.current.clientWidth/2);},[loaded,sheet,cell]);
 const book=loaded?.file===file?loaded.book:null;
 const ws=sheet?book?.getWorksheet(sheet):undefined;
 const match=cell?.replaceAll('$','').match(/^([A-Z]+)([1-9]\d*)$/i);
 const row=match?Number(match[2]):0,col=match?[...match[1].toUpperCase()].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0):0;
 const valid=!!ws&&row>0&&row<=ws.rowCount&&col>0&&col<=ws.columnCount;
 const rr=valid?Array.from({length:Math.min(ws!.rowCount,row+3)-Math.max(1,row-3)+1},(_,i)=>Math.max(1,row-3)+i):[];
 const cc=valid?[...new Set([1,...Array.from({length:Math.min(ws!.columnCount,col+2)-Math.max(1,col-2)+1},(_,i)=>Math.max(1,col-2)+i)])]:[];
 const target=valid?ws!.getCell(row,col):null;
 return <section className="xlsx-preview" aria-label="Excel source evidence">
  <div className="xlsx-toolbar"><FileSpreadsheet size={15}/><span title={file?.name}>{file?.name??'Source workbook not attached'}</span></div>
  {error?<p className="xlsx-message" role="alert">{error}</p>:!file?<p className="xlsx-message">Upload the original Excel document to view its source cells.</p>:!book?<p className="xlsx-message" role="status"><LoaderCircle className="spin" size={16}/>Loading source workbook…</p>:!sheet||!cell?<p className="xlsx-message">Select an amount to view its source cell. Values without a source reference cannot be highlighted.</p>:!valid?<p className="xlsx-message" role="alert">The reference {sheet}!{cell} could not be found in this workbook.</p>:<>
   <div className="xlsx-location"><strong>{sheet}</strong><span>{cell}</span></div>
   <div ref={scroll} className="xlsx-scroll"><table aria-label={`${sheet}, source cell ${cell}`}><thead><tr><th aria-label="Row number"/>{cc.map(c=><th key={c} className={c===col?'source-axis':''}>{columnName(c)}</th>)}</tr></thead><tbody>{rr.map(r=><tr key={r}><th className={r===row?'source-axis':''}>{r}</th>{cc.map(c=>{const v=ws!.getCell(r,c),selected=r===row&&c===col;return <td ref={selected?focus:undefined} key={c} className={selected?'source-cell':''} aria-current={selected?'true':undefined} title={`${v.address}: ${excelText(v.value)}${v.formula?` · Formula: ${v.formula}`:''}`}><span>{excelText(v.value)||'\u00a0'}</span></td>;})}</tr>)}</tbody></table></div>
   <div className="xlsx-cell-value"><span>Source cell {cell}</span><strong>{excelText(target!.value)===''?'[blank cell]':excelText(target!.value)}</strong>{target!.formula&&<small>Formula: {target!.formula} · Saved result only; not recalculated.</small>}{target!.isMerged&&<small>Merged cell · Anchor {target!.master.address}</small>}</div>
   <p className="xlsx-caption">Original workbook values · Nearby cells shown · Formatting simplified</p>
  </>}
 </section>;
}
