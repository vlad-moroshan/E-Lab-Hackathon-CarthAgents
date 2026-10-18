import {useEffect,useRef,useState} from 'react';
import {getDocument,GlobalWorkerOptions,type PDFDocumentProxy} from 'pdfjs-dist';
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url';
import {ChevronLeft,ChevronRight,ZoomIn,ZoomOut,FileSearch,LoaderCircle} from 'lucide-react';
GlobalWorkerOptions.workerSrc=workerUrl;
type Props={url:string|null;page?:number;box?:number[];precision:string;fileName:string;onAttach:()=>void};
export default function PdfViewer({url,page=1,box,precision,fileName,onAttach}:Props){
 const canvas=useRef<HTMLCanvasElement>(null),container=useRef<HTMLDivElement>(null);
 const [doc,setDoc]=useState<PDFDocumentProxy|null>(null),[current,setCurrent]=useState(page),[zoom,setZoom]=useState(1),[width,setWidth]=useState(500),[size,setSize]=useState({width:842,height:595}),[error,setError]=useState(''),[loading,setLoading]=useState(false),[rendering,setRendering]=useState(false);
 useEffect(()=>{const el=container.current;if(!el)return;const ro=new ResizeObserver(([e])=>setWidth(e.contentRect.width));ro.observe(el);return()=>ro.disconnect();},[]);
 useEffect(()=>{setCurrent(page);},[page,box]);
 useEffect(()=>{
  setDoc(null);setError('');if(!url)return;setLoading(true);let active=true;const task=getDocument({url});
  task.promise.then(d=>{if(active){setDoc(d);setLoading(false);}}).catch(e=>{if(active){setError(`Could not open this PDF. ${e.message}`);setLoading(false);}});
  return()=>{active=false;void task.destroy();};
 },[url]);
 useEffect(()=>{
  if(!doc)return;
  if(current<1||current>doc.numPages){setError(`Page ${current} is outside this PDF (${doc.numPages} pages). Check that the PDF matches this result.`);return;}
  let stopped=false;let renderTask:ReturnType<Awaited<ReturnType<PDFDocumentProxy['getPage']>>['render']>|undefined;
  setError('');setRendering(true);
  doc.getPage(current).then(p=>{
   if(stopped||!canvas.current)return;
   const original=p.getViewport({scale:1});setSize({width:original.width,height:original.height});
   const scale=Math.max(0.2,(width-32)/original.width)*zoom;const viewport=p.getViewport({scale});
   const c=canvas.current;const ratio=window.devicePixelRatio||1;c.width=viewport.width*ratio;c.height=viewport.height*ratio;c.style.width=`${viewport.width}px`;c.style.height=`${viewport.height}px`;
   renderTask=p.render({canvas:c,viewport,transform:ratio===1?undefined:[ratio,0,0,ratio,0,0]});
   return renderTask.promise;
  }).then(()=>{if(!stopped)setRendering(false);}).catch(e=>{if(!stopped&&e.name!=='RenderingCancelledException'){setError('Unable to render this page. Try another PDF.');setRendering(false);}});
  return()=>{stopped=true;renderTask?.cancel();};
 },[doc,current,width,zoom]);
 const scale=Math.max(0.2,(width-32)/size.width)*zoom;
 return <div className="pdf-viewer">
  <div className="pdf-toolbar"><span title={fileName}>{fileName||'Source document'}</span><div className="pdf-tools"><button className="icon-button" aria-label="Zoom out" disabled={zoom<=0.75} onClick={()=>setZoom(z=>Math.max(.75,z-.25))}><ZoomOut size={15}/></button><span>{Math.round(zoom*100)}%</span><button className="icon-button" aria-label="Zoom in" disabled={zoom>=2.5} onClick={()=>setZoom(z=>Math.min(2.5,z+.25))}><ZoomIn size={15}/></button></div></div>
  <div className="pdf-scroll" ref={container}>
   {!url?<div className="source-empty"><FileSearch size={34}/><h3>Bring the evidence into view</h3><p>Attach the original PDF to inspect the source location for this value.</p><button className="button secondary" onClick={onAttach}>Attach source PDF</button></div>:error?<div className="source-empty error"><FileSearch size={30}/><p>{error}</p><button className="button secondary" onClick={onAttach}>Choose another PDF</button></div>:<>
    {loading&&<div className="source-empty"><LoaderCircle className="spin"/>Opening source…</div>}
    <div className="pdf-paper" style={{width:size.width*scale,height:size.height*scale,visibility:doc?'visible':'hidden'}}><canvas ref={canvas}/>{box&&current===page&&!rendering&&<div className="source-highlight" title={`${precision==='field'?'Field':'Row'}-level source region`} style={{left:box[0]*scale,top:box[1]*scale,width:(box[2]-box[0])*scale,height:Math.max(8,(box[3]-box[1])*scale)}}/>}</div>
   </>}
  </div>
  <div className="pdf-footer"><span><i className="highlight-key"/>{box?`${precision==='field'?'Field':'Row'}-level highlight`:'No source region supplied'}</span><div className="pdf-tools"><button className="icon-button" aria-label="Previous PDF page" disabled={!doc||current<=1} onClick={()=>setCurrent(p=>p-1)}><ChevronLeft size={15}/></button><span>{doc?`${current} / ${doc.numPages}`:'—'}</span><button className="icon-button" aria-label="Next PDF page" disabled={!doc||current>=doc.numPages} onClick={()=>setCurrent(p=>p+1)}><ChevronRight size={15}/></button></div></div>
 </div>;
}
