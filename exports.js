/* Exportación local: series preparadas por Python, PDF vectorial y Excel OOXML. */
(() => {
  'use strict';
  const PILLARS=['Partner','Cliente','Negocio'];
  const valid=v=>typeof v==='number'&&Number.isFinite(v);
  const average=values=>{const clean=values.filter(valid);return clean.length?clean.reduce((a,b)=>a+b,0)/clean.length:null;};
  const total=values=>{const clean=values.filter(valid);return clean.length?clean.reduce((a,b)=>a+b,0):null;};
  const xml=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&apos;'}[c])).replace(/[\u0000-\u0008\u000b\u000c\u000e-\u001f]/g,'');
  const date=s=>new Intl.DateTimeFormat('es-MX',{day:'2-digit',month:'short',year:'numeric',timeZone:'UTC'}).format(new Date(s));
  const periodLabel=(data,period)=>period==='YTD'?'Acumulado disponible':data.months.find(m=>String(m.id)===String(period))?.label;
  const scopeLabel=scope=>({store:'Tienda',dm:'DM',region:'Región'})[scope];
  function fmt(v,type,delta=false){
    if(!valid(v))return 'Sin dato';
    const sign=delta&&v>0?'+':'';
    if(type==='percent')return `${sign}${(v*100).toFixed(1)}${delta?' pp':'%'}`;
    if(type==='millions')return `${sign}$${(v/1e6).toFixed(2)} M`;
    if(type==='duration'){const s=Math.abs(Math.round(v));return `${v<0?'-':sign}${Math.floor(s/60)}:${String(s%60).padStart(2,'0')}`;}
    if(type==='currency'||type==='currency1')return sign+new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN',maximumFractionDigits:type==='currency'?0:1}).format(v);
    return sign+new Intl.NumberFormat('es-MX',{maximumFractionDigits:1}).format(v);
  }
  function select(series,key,g,period,months){
    if(period!=='YTD')return series[months.findIndex(m=>String(m.id)===String(period))]?.[key]??null;
    const values=series.map(p=>p[key]);
    if(g.ytd==='latest')return [...values].reverse().find(valid)??null;
    return g.ytd==='sum'?total(values):average(values);
  }
  function validate(data,current){
    if(data?.schemaVersion!==1||data.generatedAt!==current.data.generatedAt||data.directoryPolicy!=='open-only-v1'
      ||current.audit.issueCount!==0||current.audit.generatedAt!==data.generatedAt||!Array.isArray(data.metrics)
      ||!Array.isArray(data.months)||JSON.stringify(data.months)!==JSON.stringify(current.data.months)
      ||!data.reports?.[current.scope]?.[current.selection])throw new Error('La exportación no corresponde a los datos visibles. Actualiza la página después de reconstruir los reportes.');
    return data;
  }
  function report(data,current,pillars,period='YTD'){
    validate(data,current);
    if(period!=='YTD'&&!data.months.some(m=>String(m.id)===String(period)))throw new Error('Selecciona un periodo disponible.');
    if(!pillars.length||pillars.some(p=>!PILLARS.includes(p)))throw new Error('Selecciona un pilar válido.');
    const source=data.reports[current.scope][current.selection];
    const groups=pillars.map(pillar=>({pillar,metrics:data.metrics.filter(g=>g.pillar===pillar&&(g.id!=='tplh'||current.productivity==='TPLH')&&(g.id!=='productividad'||current.productivity!=='TPLH')).map(g=>{
      const series=source.series[g.id];
      if(!Array.isArray(series)||series.length!==data.months.length||series.some(p=>!Array.isArray(p)||p.length!==6||p.slice(0,3).some(v=>v!==null&&!valid(v))||p.slice(3).some(v=>!Number.isInteger(v)||v<0||v>source.storeCount)))throw new Error('Serie de exportación incompleta o inválida.');
      const actual=select(series,0,g,period,data.months),reference=select(series,1,g,period,data.months),budget=select(series,2,g,period,data.months);
      const delta=valid(actual)&&valid(reference)?actual-reference:g.isDiffOnly?actual:null;
      const status=!valid(actual)?'Sin dato':!valid(delta)?'Sin comparación':(g.direction==='lower'?delta<=0:delta>=0)?'Favorable':'Atención';
      const selected=period==='YTD'?series:series.filter((_,i)=>String(data.months[i].id)===String(period));
      const coverage=`Real ${selected.filter(p=>valid(p[0])).length}/${selected.length} meses${g.reference?` · ${g.referenceKind==='ppto'?'PPTO':'AA'} ${selected.filter(p=>valid(p[1])).length}/${selected.length}`:''}`;
      return {...g,hasReference:Boolean(g.reference),series,actual,reference,budget,delta,status,coverage};
    })}));
    return {label:source.label,scope:current.scope,storeCount:source.storeCount,team:source.team,generatedAt:data.generatedAt,engineInfo:data.engineInfo,warningCount:data.warningCount,offline:Boolean(current.offline),period,periodLabel:periodLabel(data,period),months:data.months,groups};
  }
  function sourceNote(r){
    const labels=key=>(r.engineInfo[key]?.months||[]).map(id=>r.months.find(m=>m.id===id)?.short).filter(Boolean).join(', ');
    return `Perfil: ${labels('profile')} | Negocio: ${labels('business')} | Equipo: ${r.engineInfo.partners?.asOf||'sin fecha'}`;
  }
  function method(g){return g.ytd==='latest'?'Último valor disponible':g.ytd==='sum'?'Suma de meses disponibles':'Promedio de meses disponibles';}
  async function pdf(r,lib=globalThis.PDFLib){
    const {PDFDocument,StandardFonts,rgb}=lib;
    const doc=await PDFDocument.create();doc.setTitle(`Perfil ${r.label}`);doc.setLanguage('es-MX');doc.setSubject('Indicadores auditados por pilar');doc.setCreator('Perfil de Tienda');
    const regular=await doc.embedFont(StandardFonts.Helvetica),bold=await doc.embedFont(StandardFonts.HelveticaBold);
    const colors={green:rgb(0,.384,.255),ink:rgb(.07,.22,.17),muted:rgb(.34,.44,.4),paper:rgb(.95,.97,.955),line:rgb(.82,.88,.84),bad:rgb(.68,.23,.16),neutral:rgb(.43,.48,.46),white:rgb(1,1,1),gold:rgb(.68,.49,.2)};
    const safe=s=>String(s??'').replace(/[\u2010-\u2015]/g,'-').replace(/[^\u0020-\u00ff]/g,' ');
    for(const [pageIndex,group] of r.groups.entries()){
      const page=doc.addPage([960,680]);
      const box=(x,y,w,h,color)=>page.drawRectangle({x,y,width:w,height:h,color});
      function text(s,x,y,size=11,color=colors.ink,font=regular,max=900){s=safe(s);while(font.widthOfTextAtSize(s,size)>max&&size>7)size-=.4;if(font.widthOfTextAtSize(s,size)>max){while(s.length&&font.widthOfTextAtSize(s+'...',size)>max)s=s.slice(0,-1);s+='...';}page.drawText(s,{x,y,size,font,color});}
      box(0,0,960,680,colors.paper);box(0,580,960,100,colors.green);
      text('STARBUCKS MÉXICO / PERFIL DE TIENDA',30,655,10,colors.white,bold);
      text(group.pillar,30,613,33,colors.white,bold,360);
      text(`${r.periodLabel} · ${r.months[0].period.slice(0,4)}`,600,631,15,colors.white,bold,330);
      text(`${r.storeCount} tienda${r.storeCount===1?'':'s'} Abierta${r.storeCount===1?'':'s'} · ${date(r.generatedAt)}`,600,610,10,colors.white,regular,330);
      text(`${scopeLabel(r.scope)} · ${r.label}`,30,557,17,colors.ink,bold,900);
      const scored=group.metrics.filter(m=>['Favorable','Atención'].includes(m.status)),good=scored.filter(m=>m.status==='Favorable').length;
      text(`${good} de ${scored.length} comparables favorables  |  ${group.metrics.filter(m=>m.status==='Sin dato').length} sin dato  |  Real = verde, referencia = gris, PPTO adicional = oro`,30,535,10,colors.muted,regular);
      const cols=group.metrics.length>8?4:group.metrics.length>4?3:2,rows=Math.ceil(group.metrics.length/cols),gap=12,w=(900-gap*(cols-1))/cols,h=(442-gap*(rows-1))/rows;
      group.metrics.forEach((g,i)=>{
        const x=30+(i%cols)*(w+gap),y=78+(rows-1-Math.floor(i/cols))*(h+gap),tone=g.status==='Favorable'?colors.green:g.status==='Atención'?colors.bad:colors.neutral;
        box(x,y,w,h,colors.white);box(x,y+h-3,w,3,tone);
        text(g.title,x+12,y+h-20,11,colors.ink,bold,w-24);
        text(fmt(g.actual,g.format),x+12,y+h-46,cols===4?21:27,colors.ink,bold,w-24);
        const ref=g.hasReference?`${g.referenceKind==='ppto'?'PPTO':'AA'} ${fmt(g.reference,g.format)}`:'Sin referencia';
        text(`${ref}${g.secondaryReference?` | PPTO ${fmt(g.budget,g.format)}`:''}`,x+12,y+h-61,9,colors.muted,regular,w-24);
        // La serie conserva los huecos: nunca conecta meses faltantes.
        const chartBottom=y+34,chartHeight=Math.max(7,h-118),chartLeft=x+12,chartWidth=w-24;
        const values=g.series.flatMap(p=>p.slice(0,3)).filter(valid);
        if(values.length){let lo=Math.min(...values),hi=Math.max(...values);if(hi===lo){lo-=Math.max(1,Math.abs(lo)*.1);hi+=Math.max(1,Math.abs(hi)*.1);}const X=j=>chartLeft+(g.series.length===1?.5:j/(g.series.length-1))*chartWidth,Y=v=>chartBottom+(v-lo)/(hi-lo)*chartHeight;
          [0,1,2].forEach((k)=>{g.series.forEach((p,j)=>{if(!valid(p[k]))return;const color=[colors.green,colors.neutral,colors.gold][k];if(j&&valid(g.series[j-1][k]))page.drawLine({start:{x:X(j-1),y:Y(g.series[j-1][k])},end:{x:X(j),y:Y(p[k])},thickness:k===0?1.8:1,color});page.drawCircle({x:X(j),y:Y(p[k]),size:k===0?2:1.3,color});});});
          text(r.months[0].short,chartLeft,chartBottom-10,7,colors.muted);text(r.months.at(-1).short,chartLeft+chartWidth-16,chartBottom-10,7,colors.muted);
        }
        text(`${g.status}${valid(g.delta)?` · ${fmt(g.delta,g.format,true)}`:''}`,x+12,y+12,9,tone,bold,w-24);
        text(g.coverage,x+12,y+h-74,7,colors.muted,regular,w-24);
      });
      text(sourceNote(r),30,55,8,colors.muted,regular,900);
      let foot='Acumulado: venta = suma; rotación = último valor; otros = promedio. Sin dato no equivale a cero. pp = puntos porcentuales.';
      if(group.pillar==='Partner')foot+=` Equipo: ${fmt(r.team.headcount)} partners · ${r.team.coveredStores}/${r.storeCount} tiendas con Query.`;
      text(foot,30,39,8,colors.muted,regular,900);
      text(`${r.offline?'Respaldo verificado':'Datos verificados'} · ${r.warningCount} avisos de origen · Construcción ${r.generatedAt}`,30,22,7,colors.muted,regular,850);
      text(`${pageIndex+1}/${r.groups.length}`,905,22,9,colors.muted,bold,30);
    }
    return doc.save();
  }

  // OOXML explícito: textos como inlineStr (no fórmulas), números nativos y gráficas enlazadas.
  const NS='http://schemas.openxmlformats.org/spreadsheetml/2006/main';
  const REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships';
  const PKG='http://schemas.openxmlformats.org/package/2006/relationships';
  const col=n=>{let s='';while(n){n--;s=String.fromCharCode(65+n%26)+s;n=Math.floor(n/26);}return s;};
  const cell=(ref,value,style=0,formula=null)=>{
    if(formula)return `<c r="${ref}" s="${style}"${valid(value)?'':' t="str"'}><f>${xml(formula)}</f><v>${valid(value)?value:xml(value??'')}</v></c>`;
    if(valid(value))return `<c r="${ref}" s="${style}"><v>${value}</v></c>`;
    return `<c r="${ref}" s="${style}" t="inlineStr"><is><t xml:space="preserve">${xml(value??'')}</t></is></c>`;
  };
  const styleFor=g=>g.format==='percent'?6:g.format==='currency'||g.format==='currency1'||g.format==='millions'?7:g.format==='duration'?8:5;
  const styles=`<?xml version="1.0" encoding="UTF-8"?><styleSheet xmlns="${NS}"><numFmts count="5"><numFmt numFmtId="164" formatCode="#,##0.0;(#,##0.0);0.0"/><numFmt numFmtId="165" formatCode="0.0%"/><numFmt numFmtId="166" formatCode="&quot;$&quot;#,##0.00;(&quot;$&quot;#,##0.00);&quot;$&quot;0.00"/><numFmt numFmtId="167" formatCode="0 &quot;s&quot;"/><numFmt numFmtId="168" formatCode="+0.0 &quot;pp&quot;;-0.0 &quot;pp&quot;;0.0 &quot;pp&quot;"/></numFmts><fonts count="5"><font><sz val="11"/><color rgb="FF173F31"/><name val="Calibri"/></font><font><b/><sz val="24"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFFFFFFF"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FF006241"/><name val="Calibri"/></font><font><b/><sz val="11"/><color rgb="FFAA3B29"/><name val="Calibri"/></font></fonts><fills count="4"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FF006241"/><bgColor indexed="64"/></patternFill></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF0F6F2"/><bgColor indexed="64"/></patternFill></fill></fills><borders count="2"><border/><border><bottom style="hair"><color rgb="FFC9DCD0"/></bottom></border></borders><cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs><cellXfs count="12">${[
    [0,0,0,0,'left'],[0,1,2,0,'left'],[0,2,2,0,'left'],[0,3,3,1,'left'],[0,0,3,1,'left'],[164,0,3,1,'right'],[165,0,3,1,'right'],[166,0,3,1,'right'],[167,0,3,1,'right'],[168,0,3,1,'right'],[0,3,3,1,'left'],[0,4,3,1,'left']
  ].map(([num,font,fill,border,align])=>`<xf numFmtId="${num}" fontId="${font}" fillId="${fill}" borderId="${border}" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="${align}" vertical="center" wrapText="1"/></xf>`).join('')}</cellXfs><cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles><dxfs count="3"><dxf><font><b/><color rgb="FF006241"/></font></dxf><dxf><font><b/><color rgb="FFAA3B29"/></font></dxf><dxf><font><color rgb="FF64736B"/></font></dxf></dxfs></styleSheet>`;
  function chartXML(name,g,rows,months){
    const strCache=months.map((m,i)=>`<c:pt idx="${i}"><c:v>${xml(m.short)}</c:v></c:pt>`).join('');
    const series=[['E',0,'Real','006241'],...(g.hasReference?[['F',1,g.referenceKind==='ppto'?'PPTO':'AA','89968E']]:[]),...(g.secondaryReference?[['G',2,'PPTO','B58632']]:[])];
    const parts=series.map(([column,key,label,color],i)=>`<c:ser><c:idx val="${i}"/><c:order val="${i}"/><c:tx><c:v>${label}</c:v></c:tx><c:spPr><a:ln w="25400"><a:solidFill><a:srgbClr val="${color}"/></a:solidFill></a:ln></c:spPr><c:marker><c:symbol val="circle"/><c:size val="4"/></c:marker><c:cat><c:strRef><c:f>'${name}'!$D$${rows.start}:$D$${rows.end}</c:f><c:strCache><c:ptCount val="${months.length}"/>${strCache}</c:strCache></c:strRef></c:cat><c:val><c:numRef><c:f>'${name}'!$${column}$${rows.start}:$${column}$${rows.end}</c:f><c:numCache><c:formatCode>${g.format==='percent'?'0.0%':'#,##0.0'}</c:formatCode><c:ptCount val="${months.length}"/>${g.series.map((p,j)=>valid(p[key])?`<c:pt idx="${j}"><c:v>${p[key]}</c:v></c:pt>`:'').join('')}</c:numCache></c:numRef></c:val><c:smooth val="0"/></c:ser>`).join('');
    return `<?xml version="1.0" encoding="UTF-8"?><c:chartSpace xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><c:lang val="es-MX"/><c:chart><c:title><c:tx><c:rich><a:bodyPr/><a:lstStyle/><a:p><a:r><a:rPr lang="es-MX" sz="1200"/><a:t>${xml(g.title)} · tendencia mensual</a:t></a:r></a:p></c:rich></c:tx></c:title><c:autoTitleDeleted val="0"/><c:plotArea><c:layout/><c:lineChart><c:grouping val="standard"/>${parts}<c:axId val="100"/><c:axId val="200"/></c:lineChart><c:catAx><c:axId val="100"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="b"/><c:tickLblPos val="nextTo"/><c:crossAx val="200"/><c:crosses val="autoZero"/></c:catAx><c:valAx><c:axId val="200"/><c:scaling><c:orientation val="minMax"/></c:scaling><c:axPos val="l"/><c:majorGridlines/><c:numFmt formatCode="${g.format==='percent'?'0.0%':'#,##0.0'}" sourceLinked="0"/><c:tickLblPos val="nextTo"/><c:crossAx val="100"/><c:crosses val="autoZero"/><c:crossBetween val="between"/></c:valAx></c:plotArea><c:legend><c:legendPos val="b"/></c:legend><c:plotVisOnly val="1"/><c:dispBlanksAs val="gap"/></c:chart></c:chartSpace>`;
  }
  async function excel(r,Zip=globalThis.JSZip){
    const zip=new Zip(),types=[],sheets=[],relations=[],defined=[],drawings=[];
    zip.file('_rels/.rels',`<Relationships xmlns="${PKG}"><Relationship Id="rId1" Type="${REL}/officeDocument" Target="xl/workbook.xml"/></Relationships>`);
    zip.file('xl/styles.xml',styles);
    let chartId=0;
    r.groups.forEach((group,index)=>{
      const id=index+1,name=group.pillar,rows=new Map(),merges=[];
      const put=(row,column,value,style=0,formula=null)=>{if(!rows.has(row))rows.set(row,[]);rows.get(row).push(cell(`${col(column)}${row}`,value,style,formula));};
      const merge=(row,start,end,value,style=0,formula=null)=>{for(let c=start;c<=end;c++)put(row,c,c===start?value:'',style,c===start?formula:null);merges.push(`${col(start)}${row}:${col(end)}${row}`);};
      merge(1,1,12,`${name} | PERFIL DE TIENDA`,1);
      merge(2,1,12,`${scopeLabel(r.scope)} · ${r.label} | ${r.storeCount} tiendas Abierta | ${r.periodLabel}`,3);
      merge(3,1,12,sourceNote(r),0);
      merge(4,1,12,`Datos ${r.offline?'de respaldo verificado':'verificados'} · ${date(r.generatedAt)} · ${r.warningCount} avisos de origen. MXN; porcentajes: fracción; brecha: pp; tiempos: segundos.`,0);
      merge(5,1,12,`Acumulado: venta = suma; rotación = último valor; otros = promedio. DM/Región: promedio simple de tiendas con dato, excepto venta (suma).`,0);
      if(name==='Partner')merge(6,1,12,`Equipo al ${r.engineInfo.partners?.asOf||'sin fecha'}: ${fmt(r.team.headcount)} partners | Query: ${r.team.coveredStores}/${r.storeCount} tiendas.`,3);
      else merge(6,1,12,'Favorable respeta la dirección del indicador. Sin comparación y Sin dato no se califican como favorables.',3);
      [[1,3,'Indicador'],[4,5,'Real'],[6,7,'Referencia'],[8,9,'Brecha'],[10,12,'Lectura / cobertura de origen']].forEach(([a,b,t])=>merge(8,a,b,t,2));
      const chartRow=10+group.metrics.length,detailHeader=chartRow+19,detailRanges={};
      ['Indicador','','','Mes','Real','Referencia','PPTO adicional','Brecha','Tiendas Real','Tiendas Ref.','Tiendas PPTO','Lectura'].forEach((t,i)=>put(detailHeader,i+1,t,2));merges.push(`A${detailHeader}:C${detailHeader}`);
      let detail=detailHeader+1;
      group.metrics.forEach((g,i)=>{
        const start=detail,end=start+r.months.length-1;detailRanges[g.id]={start,end};
        g.series.forEach((p,j)=>{
          const delta=valid(p[0])&&valid(p[1])?p[0]-p[1]:g.isDiffOnly?p[0]:null;
          const status=!valid(p[0])?'Sin dato':!valid(delta)?'Sin comparación':(g.direction==='lower'?delta<=0:delta>=0)?'Favorable':'Atención';
          merge(detail,1,3,g.title,4);put(detail,4,r.months[j].short,4);
          put(detail,5,p[0],styleFor(g));put(detail,6,p[1],styleFor(g));put(detail,7,p[2],styleFor(g));
          const expression=g.isDiffOnly?`IF(ISNUMBER(E${detail}),E${detail},"")`:`IF(AND(ISNUMBER(E${detail}),ISNUMBER(F${detail})),E${detail}-F${detail},"")`;
          put(detail,8,valid(delta)?delta*(g.format==='percent'?100:1):null,g.format==='percent'?9:styleFor(g),g.format==='percent'?`IF(AND(ISNUMBER(E${detail}),ISNUMBER(F${detail})),(E${detail}-F${detail})*100,"")`:expression);
          [9,10,11].forEach((c,k)=>put(detail,c,p[k+3],5));put(detail,12,status,4,`IF(NOT(ISNUMBER(E${detail})),"Sin dato",IF(NOT(ISNUMBER(H${detail})),"Sin comparación",IF(H${detail}${g.direction==='lower'?'<=':'>='}0,"Favorable","Atención")))`);detail++;
        });
        const summary=9+i;
        const formula=column=>{const range=`${column}${start}:${column}${end}`;if(r.period!=='YTD'){const row=start+r.months.findIndex(m=>String(m.id)===String(r.period));return `IF(ISNUMBER(${column}${row}),${column}${row},"")`;}
          if(g.ytd==='latest'){let latest='""';for(let row=start;row<=end;row++)latest=`IF(ISNUMBER(${column}${row}),${column}${row},${latest})`;return latest;}
          return `IF(COUNT(${range})=0,"",${g.ytd==='sum'?'SUM':'AVERAGE'}(${range}))`;};
        merge(summary,1,3,g.title,3);
        // Las fórmulas viven en la esquina superior izquierda de cada bloque combinado.
        for(const [c,value,column] of [[4,g.actual,'E'],[6,g.reference,'F']]){put(summary,c,value,styleFor(g),formula(column));put(summary,c+1,'',styleFor(g));merges.push(`${col(c)}${summary}:${col(c+1)}${summary}`);}
        const factor=g.format==='percent'?100:1;
        put(summary,8,valid(g.delta)?g.delta*factor:null,g.format==='percent'?9:styleFor(g),g.isDiffOnly?`IF(ISNUMBER(D${summary}),D${summary},"")`:`IF(AND(ISNUMBER(D${summary}),ISNUMBER(F${summary})),(D${summary}-F${summary})*${factor},"")`);
        put(summary,9,'',4);merges.push(`H${summary}:I${summary}`);merge(summary,10,12,`${g.status} · ${g.coverage}`,4,`IF(NOT(ISNUMBER(D${summary})),"Sin dato",IF(NOT(ISNUMBER(H${summary})),"Sin comparación",IF(H${summary}${g.direction==='lower'?'<=':'>='}0,"Favorable","Atención")))&" · ${g.coverage}"`);
      });
      merge(chartRow,1,12,'TENDENCIAS | Gráficas nativas de Excel, vinculadas al detalle mensual',3);
      const chosen=name==='Negocio'?['sales','adt'].map(key=>group.metrics.find(g=>g.id===key)).filter(Boolean):group.metrics.slice(0,2);
      const anchors=[],drawingRels=[];
      chosen.forEach((g,j)=>{
        const cid=++chartId;types.push(`<Override PartName="/xl/charts/chart${cid}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawingml.chart+xml"/>`);
        zip.file(`xl/charts/chart${cid}.xml`,chartXML(name,g,detailRanges[g.id],r.months));
        drawingRels.push(`<Relationship Id="rId${j+1}" Type="${REL}/chart" Target="../charts/chart${cid}.xml"/>`);
        anchors.push(`<xdr:twoCellAnchor><xdr:from><xdr:col>${j*6}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>${chartRow}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:from><xdr:to><xdr:col>${j*6+6}</xdr:col><xdr:colOff>0</xdr:colOff><xdr:row>${chartRow+17}</xdr:row><xdr:rowOff>0</xdr:rowOff></xdr:to><xdr:graphicFrame macro=""><xdr:nvGraphicFramePr><xdr:cNvPr id="${j+1}" name="Tendencia ${xml(g.title)}"/><xdr:cNvGraphicFramePr/></xdr:nvGraphicFramePr><xdr:xfrm><a:off x="0" y="0"/><a:ext cx="0" cy="0"/></xdr:xfrm><a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/chart"><c:chart xmlns:c="http://schemas.openxmlformats.org/drawingml/2006/chart" xmlns:r="${REL}" r:id="rId${j+1}"/></a:graphicData></a:graphic></xdr:graphicFrame><xdr:clientData/></xdr:twoCellAnchor>`);
      });
      zip.file(`xl/drawings/drawing${id}.xml`,`<xdr:wsDr xmlns:xdr="http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing" xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">${anchors.join('')}</xdr:wsDr>`);
      zip.file(`xl/drawings/_rels/drawing${id}.xml.rels`,`<Relationships xmlns="${PKG}">${drawingRels.join('')}</Relationships>`);
      zip.file(`xl/worksheets/_rels/sheet${id}.xml.rels`,`<Relationships xmlns="${PKG}"><Relationship Id="rId1" Type="${REL}/drawing" Target="../drawings/drawing${id}.xml"/></Relationships>`);
      const rowXML=[...rows].sort((a,b)=>a[0]-b[0]).map(([n,cells])=>`<row r="${n}" ht="${n===1?40:n<=6?30:n<chartRow?34:26}" customHeight="1">${cells.join('')}</row>`).join('');
      zip.file(`xl/worksheets/sheet${id}.xml`,`<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="${NS}" xmlns:r="${REL}"><sheetPr><pageSetUpPr fitToPage="1"/></sheetPr><dimension ref="A1:L${detail-1}"/><sheetViews><sheetView showGridLines="0" workbookViewId="0"><pane ySplit="8" topLeftCell="A9" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews><sheetFormatPr defaultRowHeight="18"/><cols><col min="1" max="12" width="12" customWidth="1"/></cols><sheetData>${rowXML}</sheetData><autoFilter ref="A${detailHeader}:L${detail-1}"/><mergeCells count="${merges.length}">${merges.map(m=>`<mergeCell ref="${m}"/>`).join('')}</mergeCells><conditionalFormatting sqref="H9:L${8+group.metrics.length}"><cfRule type="expression" dxfId="0" priority="1"><formula>LEFT($J9,9)="Favorable"</formula></cfRule><cfRule type="expression" dxfId="1" priority="2"><formula>LEFT($J9,8)="Atención"</formula></cfRule><cfRule type="expression" dxfId="2" priority="3"><formula>LEFT($J9,3)="Sin"</formula></cfRule></conditionalFormatting><conditionalFormatting sqref="L${detailHeader+1}:L${detail-1}"><cfRule type="expression" dxfId="0" priority="4"><formula>L${detailHeader+1}="Favorable"</formula></cfRule><cfRule type="expression" dxfId="1" priority="5"><formula>L${detailHeader+1}="Atención"</formula></cfRule></conditionalFormatting><pageMargins left="0.25" right="0.25" top="0.3" bottom="0.3" header="0.15" footer="0.15"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="1"/><drawing r:id="rId1"/></worksheet>`);
      types.push(`<Override PartName="/xl/worksheets/sheet${id}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>`,`<Override PartName="/xl/drawings/drawing${id}.xml" ContentType="application/vnd.openxmlformats-officedocument.drawing+xml"/>`);
      sheets.push(`<sheet name="${name}" sheetId="${id}" r:id="rId${id}"/>`);relations.push(`<Relationship Id="rId${id}" Type="${REL}/worksheet" Target="worksheets/sheet${id}.xml"/>`);
      defined.push(`<definedName name="_xlnm.Print_Area" localSheetId="${index}">'${name}'!$A$1:$L$${chartRow+17}</definedName>`);
    });
    zip.file('xl/workbook.xml',`<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="${NS}" xmlns:r="${REL}"><bookViews><workbookView/></bookViews><sheets>${sheets.join('')}</sheets><definedNames>${defined.join('')}</definedNames><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>`);
    zip.file('xl/_rels/workbook.xml.rels',`<Relationships xmlns="${PKG}">${relations.join('')}<Relationship Id="rIdStyles" Type="${REL}/styles" Target="styles.xml"/></Relationships>`);
    zip.file('[Content_Types].xml',`<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>${types.join('')}</Types>`);
    return zip.generateAsync({type:'uint8array',compression:'DEFLATE'});
  }
  let getter,connected=false,snapshot,compiled,busy=false;
  const $=id=>document.getElementById(id),loading=new Map();
  function script(path,globalName){if(globalThis[globalName])return Promise.resolve();if(loading.has(path))return loading.get(path);const promise=new Promise((resolve,reject)=>{const element=document.createElement('script');let timer=setTimeout(()=>{element.remove();reject(new Error('La librería de exportación tardó demasiado. Reintenta.'));},15000);element.src=path;element.onload=()=>{clearTimeout(timer);globalThis[globalName]?resolve():reject(new Error('No se pudo iniciar la exportación.'));};element.onerror=()=>{clearTimeout(timer);element.remove();reject(new Error('No se pudo cargar la librería de exportación. Reintenta con conexión.'));};document.head.append(element);}).catch(error=>{loading.delete(path);throw error;});loading.set(path,promise);return promise;}
  async function load(current){if(compiled?.generatedAt===current.data.generatedAt)return validate(compiled,current);const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);try{const response=await fetch('data/exports.json',{cache:'no-store',signal:controller.signal});if(!response.ok)throw new Error('Reportes no disponibles. Reconstruye los datos con Python o reintenta con conexión.');compiled=validate(await response.json(),current);return compiled;}catch(e){if(e.name==='AbortError')throw new Error('La preparación tardó demasiado. Reintenta con conexión.');throw e;}finally{clearTimeout(timer);}}
  function message(text,error=false){$('exportMessage').textContent=text;$('exportMessage').dataset.error=String(error);}
  async function download(format){if(busy)return;busy=true;['downloadPdf','downloadExcel','exportPillar','exportPeriod'].forEach(id=>$(id).disabled=true);message('Preparando datos verificados…');try{
    const current=snapshot,pillars=$('exportPillar').value==='all'?PILLARS:[$('exportPillar').value],period=$('exportPeriod').value;
    const [data]=await Promise.all([load(current),script(format==='pdf'?'assets/vendor/pdf-lib-1.17.1.min.js':'assets/vendor/jszip-3.10.1.min.js',format==='pdf'?'PDFLib':'JSZip')]);
    const r=report(data,current,pillars,period);message(`Diseñando ${pillars.length} pilar${pillars.length===1?'':'es'}…`);
    const bytes=await(format==='pdf'?pdf(r):excel(r)),mime=format==='pdf'?'application/pdf':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
    const url=URL.createObjectURL(new Blob([bytes],{type:mime})),a=document.createElement('a');
    const slug=s=>String(s).normalize('NFD').replace(/[\u0300-\u036f]/g,'').replace(/[^a-zA-Z0-9_-]+/g,'_').slice(0,90);
    a.href=url;a.download=`Perfil_${slug(r.label)}_${pillars.length===3?'3_pilares':pillars[0]}_${period}_${r.generatedAt.slice(0,10)}.${format==='pdf'?'pdf':'xlsx'}`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);message(`Descarga lista: ${format==='pdf'?'PDF con una lámina por pilar':'Excel con gráficas y detalle mensual'}.`);
  }catch(error){console.error(error);message(error.message||'No fue posible exportar. Reintenta.',true);}finally{busy=false;['downloadPdf','downloadExcel','exportPillar','exportPeriod'].forEach(id=>$(id).disabled=false);}}
  function connect(read){getter=read;const button=$('openExport');if(!button)return;button.disabled=false;if(connected)return;connected=true;
    button.addEventListener('click',()=>{snapshot={...getter()};$('exportPillar').value=snapshot.pillar;$('exportPeriod').replaceChildren();for(const item of [{id:'YTD',label:'Acumulado disponible'},...snapshot.data.months]){const option=document.createElement('option');option.value=item.id;option.textContent=item.label;$('exportPeriod').append(option);}const stores=snapshot.data.directory.filter(s=>snapshot.scope==='store'?s.cc===snapshot.selection:s[snapshot.scope]===snapshot.selection);$('exportContext').textContent=`${scopeLabel(snapshot.scope)} · ${snapshot.scope==='store'?`${snapshot.selection} · ${stores[0]?.store||''}`:snapshot.selection} · ${stores.length} tiendas Abierta`;message('Elige el pilar y el formato.');$('exportDialog').showModal();});
    $('closeExport').addEventListener('click',()=>{if(!busy)$('exportDialog').close();});$('exportDialog').addEventListener('cancel',event=>{if(busy)event.preventDefault();});$('downloadPdf').addEventListener('click',()=>download('pdf'));$('downloadExcel').addEventListener('click',()=>download('excel'));
  }
  globalThis.PerfilExports=Object.freeze({connect,report,pdf,excel,validate});
})();
