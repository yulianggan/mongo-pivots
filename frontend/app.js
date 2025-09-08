(function(){
const $=(s)=>document.querySelector(s);
const apiBaseEl=$("#apiBase"),healthEl=$("#health"),collEl=$("#collection"),limitEl=$("#limit"),skipEl=$("#skip"),filtersEl=$("#filters");
const btnLoad=$("#btnLoad"),btnPeek=$("#btnPeek"),btnExport=$("#btnExportCsv"),rowsBadge=$("#rowsBadge"),logEl=$("#log");
const availableFieldsEl=$("#availableFields"),fieldSearchEl=$("#fieldSearch");
const rowsZone=$("#rowsZone"),colsZone=$("#colsZone"),valsZone=$("#valsZone");
const calcNameEl=$("#calcName"),calcExprEl=$("#calcExpr"),btnAddCalc=$("#btnAddCalc"),computedListEl=$("#computedList");
const pivotContainer=$("#pivotContainer"),formatPanelEl=$("#formatPanel");
const viewModeEl=$("#viewMode"),subtotalToggleEl=$("#subtotalToggle");
const profileNameEl=$("#profileName"),btnSaveCloud=$("#btnSaveCloud"),btnLoadCloud=$("#btnLoadCloud"),btnListCloud=$("#btnListCloud");
const btnUseConfig=$("#btnUseConfig");
const iferrAllToggle=$("#iferrAllToggle"), iferrFallbackEl=$("#iferrFallback");
const fileInput=$("#fileInput"),sheetInput=$("#sheetInput"),startRowInput=$("#startRow"),btnUpload=$("#btnUpload");
const rowFieldFiltersEl=$("#rowFieldFilters"), metricFieldFiltersEl=$("#metricFieldFilters");
const btnClearFilters=$("#btnClearFilters"), btnApplyFilters=$("#btnApplyFilters");
const toggleFilterEl=$("#toggleFilter"), toggleConfigEl=$("#toggleConfig");
const filterPanelEl=$("#filterPanel"), configPanelEl=$("#configPanel");
const filterResizeEl=$("#filterResize"), configResizeEl=$("#configResize");
const freezeRowsEl=$("#freezeRows"), freezeColsEl=$("#freezeCols");
const btnApplyFreeze=$("#btnApplyFreeze"), btnClearFreeze=$("#btnClearFreeze");

collEl.addEventListener('change', async ()=>{
  if(collEl.value && !isUploadedMode){
    currentCollection = collEl.value;
    loadState();
  }
});

let currentCollection="", rawBaseRows=[], currentRows=[], rawUploadRows=[];
let hiddenFields=new Set(), computedDefs=[], layout={rows:[],cols:[],vals:[]}, formats={};
let subtotalEnabled=false, viewMode='pivot';
let iferrDefaultEnabled=false, iferrDefaultFallback=0;
let isUploadedMode=false;
let rowFieldFilters={}, metricFieldFilters={}, filteredRows=[];

function log(s){const t=new Date().toISOString().substr(11,8); logEl.textContent+=`[${t}] ${s}
`; logEl.scrollTop=logEl.scrollHeight;}

function setApiBaseFromConfig(){ if(window.__APP_CONFIG__?.API_BASE) apiBaseEl.value=window.__APP_CONFIG__.API_BASE; }
function guessApiBases(){ const list=[]; if(window.__APP_CONFIG__?.API_BASE) list.push(window.__APP_CONFIG__.API_BASE); if(apiBaseEl?.value) list.push(apiBaseEl.value); const host=location.hostname||'localhost'; list.push(`http://${host}:7002`,`http://${host}:8000`); return [...new Set(list)]; }
async function smartPingAndInit(){ for(const b of guessApiBases()){ try{ const r=await fetch(`${b}/api/health`); const j=await r.json(); if(j?.status==='ok'){ apiBaseEl.value=b; healthEl.textContent='OK'; healthEl.style.color='#4ade80'; await loadCollections(); if(collEl.options.length){ currentCollection=collEl.value; await doPeek(); } return; } }catch(e){ log('健康检查失败：'+b); } } healthEl.textContent='连接失败'; healthEl.style.color='#f87171';}

async function loadCollections(){ try{ const r=await fetch(`${apiBaseEl.value}/api/collections`); const j=await r.json(); collEl.innerHTML=''; const collections = j && j.collections && Array.isArray(j.collections) ? j.collections : []; collections.forEach(c=>{ const o=document.createElement('option'); o.value=c; o.textContent=c; collEl.appendChild(o); }); }catch(e){ log('加载集合列表失败: '+e.message); collEl.innerHTML=''; } }

btnUseConfig && (btnUseConfig.onclick=()=>{ if(window.__APP_CONFIG__?.API_BASE){ apiBaseEl.value=window.__APP_CONFIG__.API_BASE; smartPingAndInit(); }});

function num(x){ if(x===null||x===undefined||x==='') return 0; if(typeof x==='number'&&isFinite(x)) return x;
  if(typeof x==='string'){ let s=x.replace(/\u00A0/g,' ').trim().replace(/\s+/g,''); if(s.includes(',')&&s.includes('.')){ if(s.lastIndexOf(',')>s.lastIndexOf('.')){ s=s.replace(/\./g,'').replace(',', '.'); } else { s=s.replace(/,/g,''); } } else if(s.includes(',')){ s=s.replace(/\./g,''); s=s.replace(/,/g,'.'); } const v=parseFloat(s); return isNaN(v)?0:v; }
  const v=Number(x); return isNaN(v)?0:v; }

function compileExpr(expr){
  return function(r){
    try{
      // Include computed fields that were already calculated
      const allKeys = [...Object.keys(r), ...computedDefs.map(d => d.name)];
      const keys = [...new Set(allKeys)].sort((a,b)=>b.length-a.length);
      let code=expr;
      keys.forEach(k=>{ 
        // 使用带边界检查的字符串替换，支持特殊字符字段名
        const parts = code.split(k);
        if(parts.length > 1) {
          let result = parts[0];
          for(let i = 1; i < parts.length; i++) {
            const prevChar = result.slice(-1);
            const nextChar = parts[i].slice(0, 1);
            
            // 检查是否是完整的字段名（前后不是字母数字或中文字符）
            const isValidBoundary = (
              (prevChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(prevChar)) &&
              (nextChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(nextChar))
            );
            
            if(isValidBoundary) {
              result += `num(r["${k}"])` + parts[i];
            } else {
              result += k + parts[i];
            }
          }
          code = result;
        }
      });
      const FN=new Function('r','num','__enabled','__fb',`
        const IFERROR=(v,fb=0)=>{ const n=Number(v); return (Number.isFinite(n)&&!Number.isNaN(n))?v:fb; };
        const DIV=(a,b,fb=0)=>{ const na=num(a); const nb=num(b); if(nb===0) return fb; const q=na/nb; return (Number.isFinite(q)&&!Number.isNaN(q))?q:fb; };
        const _res = (${code});
        return __enabled ? IFERROR(_res, __fb) : _res;
      `);
      const fb = Number(iferrFallbackEl?.value ?? iferrDefaultFallback) || 0;
      return FN(r,num, !!iferrDefaultEnabled, fb);
    }catch(e){ return null; }
  };
}
function extractVars(expr, knownFields = []){ 
  const set=new Set(); 
  
  // 尝试从全局数据获取已知字段
  if(knownFields.length === 0 && typeof rawBaseRows !== 'undefined' && Array.isArray(rawBaseRows) && rawBaseRows.length > 0) {
    knownFields = Object.keys(rawBaseRows[0]);
  }
  
  // 使用已知字段列表进行精确匹配
  if(knownFields.length > 0) {
    const allFields = [...knownFields, ...computedDefs.map(d => d.name)];
    allFields.sort((a,b) => b.length - a.length); // 按长度排序，优先匹配长字段名
    
    for(const field of allFields) {
      // 使用简单的字符串包含检查，然后验证边界
      if(expr.includes(field)) {
        // 验证是否是完整的字段名匹配
        const parts = expr.split(field);
        for(let i = 0; i < parts.length - 1; i++) {
          const prevChar = parts[i].slice(-1);
          const nextChar = parts[i + 1].slice(0, 1);
          const isValidBoundary = (
            (prevChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(prevChar)) &&
            (nextChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(nextChar))
          );
          if(isValidBoundary) {
            set.add(field);
            break;
          }
        }
      }
    }
  } else {
    // 回退到改进的正则表达式方法
    const rx=/[A-Za-z_\u4e00-\u9fff][A-Za-z0-9_\u4e00-\u9fff\|\/%\s\-\(\)\[\]\{\}]*[A-Za-z0-9_\u4e00-\u9fff\|\/%\-\(\)\[\]\{\}]|[A-Za-z_\u4e00-\u9fff]/g; 
    let m; 
    while((m=rx.exec(expr))){ 
      const variable = m[0].trim(); 
      if(variable && variable.length > 0) set.add(variable); 
    }
  }
  
  ['num','Math','Infinity','NaN','undefined','true','false','IFERROR','DIV'].forEach(k=>set.delete(k)); 
  return [...set]; 
}
function compileAggExpr(expr){
  const vars=extractVars(expr); let code=expr;
  // Include computed field names in the variables list
  const allVars = [...vars, ...computedDefs.map(d => d.name)];
  const uniqueVars = [...new Set(allVars)].sort((a,b)=>b.length-a.length);
  uniqueVars.forEach(v=>{ 
    // 使用带边界检查的字符串替换，支持特殊字符字段名
    const parts = code.split(v);
    if(parts.length > 1) {
      let result = parts[0];
      for(let i = 1; i < parts.length; i++) {
        const prevChar = result.slice(-1);
        const nextChar = parts[i].slice(0, 1);
        
        // 检查是否是完整的字段名（前后不是字母数字或中文字符）
        const isValidBoundary = (
          (prevChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(prevChar)) &&
          (nextChar === '' || !/[A-Za-z0-9_\u4e00-\u9fff]/.test(nextChar))
        );
        
        if(isValidBoundary) {
          result += `get("${v}")` + parts[i];
        } else {
          result += v + parts[i];
        }
      }
      code = result;
    }
  });
  return function(get){
    try{
      const FN=new Function('get','num','__enabled','__fb',`
        const IFERROR=(v,fb=0)=>{ const n=Number(v); return (Number.isFinite(n)&&!Number.isNaN(n))?v:fb; };
        const DIV=(a,b,fb=0)=>{ const na=num(a); const nb=num(b); if(nb===0) return fb; const q=na/nb; return (Number.isFinite(q)&&!Number.isNaN(q))?q:fb; };
        const _res = (${code});
        return __enabled ? IFERROR(_res, __fb) : _res;
      `);
      const fb = Number(iferrFallbackEl?.value ?? iferrDefaultFallback) || 0;
      return FN(get,num, !!iferrDefaultEnabled, fb);
    }catch(e){ return null; }
  };
}

function applyComputed(rows){ 
  if(!computedDefs.length || !Array.isArray(rows)) return rows || []; 
  return rows.map(r=>{ 
    const out={...r}; 
    
    // Apply computed fields in dependency order
    const processedFields = new Set();
    const remainingDefs = [...computedDefs];
    
    // Multi-pass processing to handle dependencies
    while (remainingDefs.length > 0 && processedFields.size < computedDefs.length) {
      const currentRoundProcessed = [];
      
      for (let i = remainingDefs.length - 1; i >= 0; i--) {
        const def = remainingDefs[i];
        const dependencies = extractVars(def.expr);
        const computedNames = new Set(computedDefs.map(d => d.name));
        const unprocessedDeps = dependencies.filter(dep => 
          computedNames.has(dep) && !processedFields.has(dep)
        );
        
        if (unprocessedDeps.length === 0) {
          // No unprocessed dependencies, can compute this field
          try {
            out[def.name] = def.fn(out);
            processedFields.add(def.name);
            currentRoundProcessed.push(i);
          } catch(e) {
            console.error('计算字段错误:', def.name, e);
            out[def.name] = 0;
            processedFields.add(def.name);
            currentRoundProcessed.push(i);
          }
        }
      }
      
      // Remove processed fields from remaining list（indices already in reverse order from backward iteration）
      currentRoundProcessed.forEach(index => {
        remainingDefs.splice(index, 1);
      });
      
      // If no fields were processed in this round, there are circular dependencies
      if (currentRoundProcessed.length === 0) {
        remainingDefs.forEach(def => {
          out[def.name] = 0;
        });
        break;
      }
    }
    
    return out; 
  }); 
}

function buildFilterUI(){
  rowFieldFiltersEl.innerHTML=''; metricFieldFiltersEl.innerHTML='';
  if(!currentRows || !currentRows.length) return;
  
  const fields = Object.keys(currentRows[0] || {});
  const rowFields = layout.rows || [];
  const valFields = (layout.vals || []).map(v => v.field);
  
  // 为行字段生成字符串筛选器
  rowFields.forEach(field => {
    if(!fields.includes(field)) return;
    const filterDiv = document.createElement('div');
    filterDiv.className = 'filter-item';
    filterDiv.innerHTML = `
      <label>${field}</label>
      <input type="text" data-field="${field}" data-type="row" 
             placeholder="输入包含的字符串..." style="width:100%;" />
    `;
    rowFieldFiltersEl.appendChild(filterDiv);
  });
  
  // 为指标字段生成数字筛选器
  valFields.forEach(field => {
    if(!fields.includes(field)) return;
    const nums = currentRows.map(r => num(r[field])).filter(n => Number.isFinite(n));
    if(!nums.length) return;
    const min = Math.min(...nums);
    const max = Math.max(...nums);
    const filterDiv = document.createElement('div');
    filterDiv.className = 'filter-item';
    filterDiv.innerHTML = `
      <label>${field}</label>
      <div style="display:flex;gap:4px;align-items:center;">
        <input type="number" data-field="${field}" data-type="metric" data-operator="min" 
               placeholder="最小值" step="0.01" style="width:50%;" />
        <span style="color:#7f8ca3;">-</span>
        <input type="number" data-field="${field}" data-type="metric" data-operator="max" 
               placeholder="最大值" step="0.01" style="width:50%;" />
      </div>
    `;
    metricFieldFiltersEl.appendChild(filterDiv);
  });
}

function applyFilters(){
  if(!rawBaseRows || !rawBaseRows.length) return;
  let filtered = [...rawBaseRows];
  
  // 应用计算字段
  filtered = applyComputed(filtered);
  
  // 应用行字段筛选 (字符串包含筛选)
  Object.keys(rowFieldFilters).forEach(field => {
    const value = rowFieldFilters[field];
    if(value && value !== '') {
      filtered = filtered.filter(r => String(r[field] || '').toLowerCase().includes(value.toLowerCase()));
    }
  });
  
  // 应用指标字段筛选 (数字筛选)
  Object.keys(metricFieldFilters).forEach(field => {
    const filter = metricFieldFilters[field];
    if(filter) {
      filtered = filtered.filter(r => {
        const val = num(r[field]);
        if(filter.min !== undefined && val < filter.min) return false;
        if(filter.max !== undefined && val > filter.max) return false;
        return true;
      });
    }
  });
  
  filteredRows = filtered;
  return filtered;
}

function updateFilters(){
  rowFieldFilters = {};
  metricFieldFilters = {};
  
  // 收集行字段筛选
  rowFieldFiltersEl.querySelectorAll('input[data-type="row"]').forEach(input => {
    const field = input.dataset.field;
    if(input.value && input.value.trim() !== '') {
      rowFieldFilters[field] = input.value.trim();
    }
  });
  
  // 收集指标字段筛选
  const metricInputs = metricFieldFiltersEl.querySelectorAll('input[data-type="metric"]');
  metricInputs.forEach(input => {
    const field = input.dataset.field;
    const operator = input.dataset.operator;
    const value = input.value;
    
    if(value && value !== '') {
      if(!metricFieldFilters[field]) metricFieldFilters[field] = {};
      metricFieldFilters[field][operator] = parseFloat(value);
    }
  });
  
  log('筛选条件已更新');
}

function matchesFilter(doc, filt){
  if(!filt || !Object.keys(filt).length) return true;
  const ops=Object.keys(filt);
  if("$and" in filt){ return (filt.$and||[]).every(f=>matchesFilter(doc,f)); }
  if("$or" in filt){ return (filt.$or||[]).some(f=>matchesFilter(doc,f)); }
  for(const k of ops){
    if(k==="$and"||k==="$or") continue;
    const cond=filt[k];
    const val=doc[k];
    if(cond && typeof cond==="object" && !Array.isArray(cond)){
      for(const op in cond){
        const target=cond[op];
        if(op==="$eq"){ if(!(val===target)) return false; }
        else if(op==="$gt"){ if(!(num(val)>num(target))) return false; }
        else if(op==="$gte"){ if(!(num(val)>=num(target))) return false; }
        else if(op==="$lt"){ if(!(num(val)<num(target))) return false; }
        else if(op==="$lte"){ if(!(num(val)<=num(target))) return false; }
        else if(op==="$in"){ if(!Array.isArray(target) || !target.includes(val)) return false; }
        else if(op==="$regex"){
          const pattern = String(target);
          const flags = (cond.$options||"");
          try{
            const re=new RegExp(pattern, flags);
            if(!re.test(String(val??""))) return false;
          }catch{ return false; }
        } else {
          return false;
        }
      }
    } else {
      if(!(val===cond)) return false;
    }
  }
  return true;
}

function rebuildAvailableFields(){ availableFieldsEl.innerHTML=''; const sample=Array.isArray(currentRows) && currentRows.length > 0 ? currentRows[0] : {}; let fields=Object.keys(sample).filter(k=>!hiddenFields.has(k)); const kw=(fieldSearchEl?.value||'').trim().toLowerCase(); if(kw) fields=fields.filter(x=>x.toLowerCase().includes(kw)); fields.sort(); fields.forEach(f=>{ const chip=document.createElement('div'); chip.className='field'; chip.draggable=true; chip.dataset.field=f; chip.innerHTML=`<span>${f}</span>`; chip.addEventListener('dragstart',onDragStart); availableFieldsEl.appendChild(chip); }); }

function renderZone(zoneEl, arr, showAgg){ zoneEl.innerHTML=''; arr.forEach((item,idx)=>{ const f=typeof item==='string'?item:item.field; const chip=document.createElement('div'); chip.className='field'; chip.draggable=true; chip.dataset.field=f; chip.dataset.zone=zoneEl.id; chip.dataset.index=idx; let inner=`<span>${f}</span>`; if(showAgg){ const agg=item.agg||'sum'; inner+=` <select class='agg'><option value='sum'${agg==='sum'?' selected':''}>sum</option><option value='avg'${agg==='avg'?' selected':''}>avg</option><option value='count'${agg==='count'?' selected':''}>count</option><option value='min'${agg==='min'?' selected':''}>min</option><option value='max'${agg==='max'?' selected':''}>max</option></select>`;} inner+=` <span class='remove'>✕</span>`; chip.innerHTML=inner; chip.addEventListener('dragstart',onDragStart); chip.querySelector('.remove').onclick=()=>{ arr.splice(idx,1); saveState(); renderZones(); renderPivot(); }; if(showAgg){ chip.querySelector('.agg').onchange=e=>{ arr[idx].agg=e.target.value; saveState(); renderPivot(); renderFormatPanel(); }; } zoneEl.appendChild(chip); }); }
function renderZones(){ renderZone(rowsZone,layout.rows,false); renderZone(colsZone,layout.cols,false); renderZone(valsZone,layout.vals,true); renderFormatPanel(); }
function onDragStart(e){ const field=e.currentTarget.dataset.field; const zone=e.currentTarget.dataset.zone||'available'; const index=e.currentTarget.dataset.index; e.dataTransfer.setData('text/plain', JSON.stringify({field,from:zone,index:index?Number(index):null})); }
[rowsZone,colsZone,valsZone,availableFieldsEl,computedListEl].forEach(el=>{ 
  el.addEventListener('dragover',e=>e.preventDefault()); 
  
  el.addEventListener('drop', e=>{ 
    e.preventDefault(); 
    const data=JSON.parse(e.dataTransfer.getData('text/plain')); 
    const to=el.id;
    
    // 计算插入位置（用于同区域内排序）
    let insertIndex = -1;
    if (to === 'valsZone') {
      const rect = el.getBoundingClientRect();
      const mouseY = e.clientY - rect.top;
      const children = Array.from(el.children);
      
      for (let i = 0; i < children.length; i++) {
        const childRect = children[i].getBoundingClientRect();
        const childTop = childRect.top - rect.top;
        const childBottom = childTop + childRect.height;
        
        if (mouseY < childTop + childRect.height / 2) {
          insertIndex = i;
          break;
        }
      }
      
      if (insertIndex === -1) {
        insertIndex = children.length;
      }
    }
    
    // 处理同区域内的排序
    if (data.from === to && to === 'valsZone') {
      // 同区域内排序
      const item = layout.vals[data.index];
      layout.vals.splice(data.index, 1);
      
      // 调整插入位置（如果原位置在插入位置之前）
      if (data.index < insertIndex) {
        insertIndex--;
      }
      
      layout.vals.splice(insertIndex, 0, item);
    } else {
      // 跨区域移动（原有逻辑）
      if(data.from==='rowsZone') layout.rows.splice(data.index,1); 
      if(data.from==='colsZone') layout.cols.splice(data.index,1); 
      if(data.from==='valsZone') layout.vals.splice(data.index,1); 
      
      if(to==='rowsZone') layout.rows.push(data.field); 
      else if(to==='colsZone') layout.cols.push(data.field); 
      else if(to==='valsZone') {
        const newItem = {field:data.field,agg:'sum'};
        if (insertIndex >= 0 && insertIndex < layout.vals.length) {
          layout.vals.splice(insertIndex, 0, newItem);
        } else {
          layout.vals.push(newItem);
        }
      }
    }
    
    saveState(); 
    renderZones(); 
    renderPivot(); 
  }); 
});

function metricKey(vd){ return `${vd.field}|${vd.agg||'sum'}`; }
function renderFormatPanel(){ formatPanelEl.innerHTML=''; const list=layout.vals.length?layout.vals:[]; list.forEach(vd=>{ const key=metricKey(vd); const cfgRaw=formats[key]||{}; const cfg={decimals:Number.isFinite(cfgRaw.decimals)?cfgRaw.decimals:2, thousand:cfgRaw.thousand!==undefined?!!cfgRaw.thousand:true, currency:cfgRaw.currency||'', currencyPos:cfgRaw.currencyPos||'prefix', tenThousand:cfgRaw.tenThousand!==undefined?!!cfgRaw.tenThousand:false}; const card=document.createElement('div'); card.className='metric-card'; card.innerHTML=`<div class='metric-title'>${vd.field} ${vd.agg||'sum'}</div><div class='metric-grid'><label>小数位<input type='number' class='fmt-dec' min='0' max='8' step='1' value='${cfg.decimals}'/></label><label>千分位<input type='checkbox' class='fmt-th' ${cfg.thousand?'checked':''}/></label><label>万<input type='checkbox' class='fmt-wan' ${cfg.tenThousand?'checked':''}/></label><label>货币符号<input type='text' class='fmt-cur' value='${cfg.currency.replace(/"/g,'&quot;')}'/></label><label>位置<select class='fmt-pos'><option value='prefix'${cfg.currencyPos==='prefix'?' selected':''}>前</option><option value='suffix'${cfg.currencyPos==='suffix'?' selected':''}>后</option></select></label></div>`; const dec=card.querySelector('.fmt-dec'),th=card.querySelector('.fmt-th'),wan=card.querySelector('.fmt-wan'),cur=card.querySelector('.fmt-cur'),pos=card.querySelector('.fmt-pos'); dec.oninput=e=>{ const v=Number(e.target.value); cfg.decimals=Number.isFinite(v)?Math.max(0,Math.min(8,v)):0; formats[key]=cfg; saveState(); renderPivot(); }; th.onchange=e=>{ cfg.thousand=!!e.target.checked; formats[key]=cfg; saveState(); renderPivot(); }; wan.onchange=e=>{ cfg.tenThousand=!!e.target.checked; formats[key]=cfg; saveState(); renderPivot(); }; cur.oninput=e=>{ cfg.currency=e.target.value; formats[key]=cfg; saveState(); renderPivot(); }; pos.onchange=e=>{ cfg.currencyPos=e.target.value; formats[key]=cfg; saveState(); renderPivot(); }; formatPanelEl.appendChild(card); }); if(!list.length){ const p=document.createElement('div'); p.className='small'; p.textContent='将指标拖入"指标（聚合）"后，在此配置格式。'; formatPanelEl.appendChild(p); } }
function formatNumber(n,opt){ const decimals=Number(opt?.decimals??2); const thousand=!!opt?.thousand; const currency=opt?.currency||''; const pos=opt?.currencyPos||'prefix'; const tenThousand=!!opt?.tenThousand; let value = tenThousand ? n / 10000 : n; const fixed=(Math.round(value*(10**decimals))/(10**decimals)).toFixed(decimals); let x=fixed; if(thousand){ const [i,d]=fixed.split('.'); const sep=i.replace(/\B(?=(\d{3})+(?!\d))/g,','); x=d!==undefined?`${sep}.${d}`:sep; } return currency? (pos==='suffix'?`${x}${currency}`:`${currency}${x}`):x; }
function formatAgg(value,agg,fmt){ const n=(typeof value==='number')?value:num(value); if(!isFinite(n)) return ''; if(agg==='count') return String(Math.round(n)); return formatNumber(n,fmt); }

function saveState(){ localStorage.setItem(`pivot_hidden_${currentCollection}`, JSON.stringify([...hiddenFields])); localStorage.setItem(`pivot_layout_${currentCollection}`, JSON.stringify(layout)); localStorage.setItem(`pivot_formulas_${currentCollection}`, JSON.stringify(computedDefs.map(({name,expr})=>({name,expr})))); localStorage.setItem(`pivot_formats_${currentCollection}`, JSON.stringify(formats)); localStorage.setItem(`pivot_subtotal_${currentCollection}`, JSON.stringify(subtotalEnabled)); localStorage.setItem(`pivot_view_${currentCollection}`, viewMode); localStorage.setItem(`pivot_iferr_enabled_${currentCollection}`, JSON.stringify(iferrDefaultEnabled)); localStorage.setItem(`pivot_iferr_fb_${currentCollection}`, JSON.stringify(Number(iferrFallbackEl?.value ?? iferrDefaultFallback)||0)); }
function loadState(){ 
  hiddenFields=new Set(JSON.parse(localStorage.getItem(`pivot_hidden_${currentCollection}`)||'[]')); 
  layout=JSON.parse(localStorage.getItem(`pivot_layout_${currentCollection}`)||'{"rows":[],"cols":[],"vals":[]}')||{rows:[],cols:[],vals:[]}; 
  const f=JSON.parse(localStorage.getItem(`pivot_formulas_${currentCollection}`)||'[]'); 
  
  // Load computed fields first without functions
  computedDefs = f.map(x => ({...x, fn: null, fnAgg: null}));
  
  // Then compile all expressions to ensure proper field references
  computedDefs = computedDefs.map(def => ({
    ...def,
    fn: compileExpr(def.expr),
    fnAgg: compileAggExpr(def.expr)
  }));
  
  formats=JSON.parse(localStorage.getItem(`pivot_formats_${currentCollection}`)||'{}'); 
  subtotalEnabled=JSON.parse(localStorage.getItem(`pivot_subtotal_${currentCollection}`)||'false'); 
  viewMode=localStorage.getItem(`pivot_view_${currentCollection}`)||'pivot'; 
  iferrDefaultEnabled=JSON.parse(localStorage.getItem(`pivot_iferr_enabled_${currentCollection}`)||'false'); 
  iferrDefaultFallback=JSON.parse(localStorage.getItem(`pivot_iferr_fb_${currentCollection}`)||'0'); 
  if(iferrAllToggle){ iferrAllToggle.checked=!!iferrDefaultEnabled; } 
  if(iferrFallbackEl){ iferrFallbackEl.value=String(iferrDefaultFallback); } 
}

function getColumns(){ return Array.isArray(rawBaseRows) && rawBaseRows.length > 0 ? Object.keys(rawBaseRows[0]) : []; }

function pivotData(baseRows){
  if(!Array.isArray(baseRows) || baseRows.length === 0) {
    return {headerRows: [], dataRows: [], summaryRow: [], allRowData: [], rowFields: [], colFields: [], valDefs: [], colAggTypes: [], colKeys: [], rows: []};
  }
  const rowFields=layout.rows, colFields=layout.cols, valDefs=layout.vals.length?layout.vals:[{field:getColumns()[0]||'',agg:'count'}];
  const sep='\u0001';
  const computedNames=new Set(computedDefs.map(d=>d.name));
  const computedMap=Object.fromEntries(computedDefs.map(d=>[d.name,d]));

  const colKey=r=>colFields.map(f=>String(r[f]??'')).join(sep);
  const colKeys=[], colSet=new Set();
  baseRows.forEach(r=>{ const ck=colKey(r); if(!colSet.has(ck)){colSet.add(ck);colKeys.push(ck);} });

  function initAgg(){return {sum:0,count:0,min:Infinity,max:-Infinity}}
  function updateAgg(a,v){const n=num(v); a.sum+=n; a.count++; if(n<a.min)a.min=n; if(n>a.max)a.max=n;}
  function valueAgg(a,t){ if(t==='sum')return a.sum; if(t==='count')return a.count; if(t==='min')return a.min===Infinity?0:a.min; if(t==='max')return a.max===-Infinity?0:a.max; if(t==='avg')return a.count?a.sum/a.count:0; return 0; }

  // 构建层级树结构
  function buildHierarchy() {
    const root = { children: new Map(), data: new Map(), isSubtotal: false };
    
    baseRows.forEach(r0 => {
      const r = {...r0};
      computedDefs.forEach(def=>{ r[def.name] = def.fn(r); });
      
      let currentNode = root;
      const ck = colKey(r);
      
      // 构建行层级路径
      for (let level = 0; level < rowFields.length; level++) {
        const fieldValue = String(r[rowFields[level]] ?? '');
        if (!currentNode.children.has(fieldValue)) {
          currentNode.children.set(fieldValue, { 
            children: new Map(), 
            data: new Map(), 
            isSubtotal: false,
            level: level,
            fieldName: rowFields[level],
            value: fieldValue
          });
        }
        currentNode = currentNode.children.get(fieldValue);
      }
      
      // 在叶子节点存储数据
      const dataKey = ck;
      if (!currentNode.data.has(dataKey)) currentNode.data.set(dataKey, {});
      const bucket = currentNode.data.get(dataKey);
      Object.keys(r).forEach(k=>{ if(!bucket[k]) bucket[k]=initAgg(); });
      Object.keys(r).forEach(k=> updateAgg(bucket[k], r[k]));
    });
    
    return root;
  }
  
  // 递归生成所有行（包括小计行）
  function generateRows(node, currentPath = [], allRows = []) {
    if (node.children.size === 0) {
      // 叶子节点：添加数据行
      const row = [...currentPath];
      // 填充剩余列为空
      while (row.length < rowFields.length) row.push('');
      
      colKeys.forEach(ck => {
        const bucket = node.data.get(ck) || {};
        
        // 先计算所有自定义字段的值
        const computedValues = new Map();
        const processedComputedFields = new Set();
        const remainingComputedDefs = [...computedDefs];
        
        // 多轮处理自定义字段的依赖关系
        while (remainingComputedDefs.length > 0 && processedComputedFields.size < computedDefs.length) {
          const currentRoundProcessed = [];
          
          for (let i = remainingComputedDefs.length - 1; i >= 0; i--) {
            const def = remainingComputedDefs[i];
            const dependencies = extractVars(def.expr);
            const unprocessedDeps = dependencies.filter(dep => 
              computedNames.has(dep) && !processedComputedFields.has(dep)
            );
            
            if (unprocessedDeps.length === 0) {
              // 创建数据对象，包含原始字段和已计算的自定义字段
              const leafRowData = {};
              // 添加原始字段
              Object.keys(bucket).forEach(fieldName => {
                const agg = bucket[fieldName] || initAgg();
                leafRowData[fieldName] = valueAgg(agg, 'sum');
              });
              // 添加已计算的自定义字段
              for (const [fieldName, fieldValue] of computedValues) {
                leafRowData[fieldName] = fieldValue;
              }
              
              try {
                // Use aggregation function with get accessor for pivot context
                const get = (fieldName) => {
                  if (computedValues.has(fieldName)) {
                    return computedValues.get(fieldName);
                  }
                  const agg = bucket[fieldName] || initAgg();
                  return valueAgg(agg, 'sum');
                };
                const val = def.fnAgg ? def.fnAgg(get) : 0;
                computedValues.set(def.name, val);
                processedComputedFields.add(def.name);
                currentRoundProcessed.push(i);
              } catch(e) {
                console.error('叶子节点计算字段错误:', def.name, e);
                computedValues.set(def.name, 0);
                processedComputedFields.add(def.name);
                currentRoundProcessed.push(i);
              }
            }
          }
          
          // 移除已处理的字段（indices already in reverse order from backward iteration）
          currentRoundProcessed.forEach(index => {
            remainingComputedDefs.splice(index, 1);
          });
          
          // 如果一轮下来没有处理任何字段，说明存在循环依赖，退出循环
          if (currentRoundProcessed.length === 0) {
            remainingComputedDefs.forEach(def => {
              computedValues.set(def.name, 0);
            });
            break;
          }
        }
        
        valDefs.forEach(vd => {
          let val = 0;
          if (computedNames.has(vd.field)) {
            val = computedValues.get(vd.field) || 0;
          } else {
            const a = bucket[vd.field] || initAgg();
            val = valueAgg(a, vd.agg);
          }
          row.push(val);
        });
      });
      allRows.push({ row, level: currentPath.length, isSubtotal: false, path: [...currentPath] });
      return;
    }
    
    // 中间节点：递归处理子节点
    const children = Array.from(node.children.entries()).sort((a, b) => String(a[0]).localeCompare(String(b[0])));
    
    for (const [value, childNode] of children) {
      const newPath = [...currentPath, value];
      generateRows(childNode, newPath, allRows);
    }
    
    // 在处理完所有子项后，为每个有子项的分组添加小计行
    for (const [value, childNode] of children) {
      if (subtotalEnabled && childNode.children.size > 0 && rowFields.length > 1) {
        const newPath = [...currentPath, value];
        const subtotalRow = [...newPath];
        // 填充剩余列
        while (subtotalRow.length < rowFields.length) subtotalRow.push('');
        
        // 计算这个分组的小计
        const subtotalData = new Map();
        function collectSubtotalData(n) {
          if (n.children.size === 0) {
            // 叶子节点，收集数据
            for (const [ck, bucket] of n.data) {
              if (!subtotalData.has(ck)) subtotalData.set(ck, {});
              const subtotalBucket = subtotalData.get(ck);
              Object.keys(bucket).forEach(k => {
                if (!subtotalBucket[k]) subtotalBucket[k] = initAgg();
                const agg = bucket[k];
                subtotalBucket[k].sum += agg.sum;
                subtotalBucket[k].count += agg.count;
                if (agg.min < subtotalBucket[k].min) subtotalBucket[k].min = agg.min;
                if (agg.max > subtotalBucket[k].max) subtotalBucket[k].max = agg.max;
              });
            }
          } else {
            // 递归收集子节点数据
            for (const child of n.children.values()) {
              collectSubtotalData(child);
            }
          }
        }
        collectSubtotalData(childNode);
        
        colKeys.forEach(ck => {
          const bucket = subtotalData.get(ck) || {};
          
          // 先计算所有自定义字段的值
          const computedValues = new Map();
          const processedComputedFields = new Set();
          const remainingComputedDefs = [...computedDefs];
          
          // 多轮处理自定义字段的依赖关系
          while (remainingComputedDefs.length > 0 && processedComputedFields.size < computedDefs.length) {
            const currentRoundProcessed = [];
            
            for (let i = remainingComputedDefs.length - 1; i >= 0; i--) {
              const def = remainingComputedDefs[i];
              const dependencies = extractVars(def.expr);
              const unprocessedDeps = dependencies.filter(dep => 
                computedNames.has(dep) && !processedComputedFields.has(dep)
              );
              
              if (unprocessedDeps.length === 0) {
                // 创建数据对象，包含原始字段和已计算的自定义字段
                const subtotalRowData = {};
                // 添加原始字段
                Object.keys(bucket).forEach(fieldName => {
                  const agg = bucket[fieldName] || initAgg();
                  subtotalRowData[fieldName] = valueAgg(agg, 'sum');
                });
                // 添加已计算的自定义字段
                for (const [fieldName, fieldValue] of computedValues) {
                  subtotalRowData[fieldName] = fieldValue;
                }
                
                try {
                  // Use aggregation function with get accessor for subtotal context
                  const get = (fieldName) => {
                    if (computedValues.has(fieldName)) {
                      return computedValues.get(fieldName);
                    }
                    const agg = bucket[fieldName] || initAgg();
                    return valueAgg(agg, 'sum');
                  };
                  const val = def.fnAgg ? def.fnAgg(get) : 0;
                  computedValues.set(def.name, val);
                  processedComputedFields.add(def.name);
                  currentRoundProcessed.push(i);
                } catch(e) {
                  console.error('小计行计算字段错误:', def.name, e);
                  computedValues.set(def.name, 0);
                  processedComputedFields.add(def.name);
                  currentRoundProcessed.push(i);
                }
              }
            }
            
            // 移除已处理的字段（indices already in reverse order from backward iteration）
            currentRoundProcessed.forEach(index => {
              remainingComputedDefs.splice(index, 1);
            });
            
            // 如果一轮下来没有处理任何字段，说明存在循环依赖，退出循环
            if (currentRoundProcessed.length === 0) {
              remainingComputedDefs.forEach(def => {
                computedValues.set(def.name, 0);
              });
              break;
            }
          }
          
          valDefs.forEach(vd => {
            let val = 0;
            if (computedNames.has(vd.field)) {
              val = computedValues.get(vd.field) || 0;
            } else {
              const a = bucket[vd.field] || initAgg();
              val = valueAgg(a, vd.agg);
            }
            subtotalRow.push(val);
          });
        });
        
        allRows.push({ row: subtotalRow, level: newPath.length, isSubtotal: true, path: [...newPath] });
      }
    }
    
    return allRows;
  }

  const hierarchy = buildHierarchy();
  const allRowData = generateRows(hierarchy);
  
  // 提取数据行
  const dataRows = allRowData.map(item => item.row);

  const colLabels=colKeys.map(ck=> ck?ck.split(sep):Array(colFields.length).fill(''));
  const headerRows=[];
  for(let level=0; level<colFields.length; level++){ const row=Array(rowFields.length).fill(''); colLabels.forEach(labels=> row.push(labels[level]||'')); headerRows.push(row); }
  const valHeader=Array(rowFields.length).fill(''); colKeys.forEach(_=>{ valDefs.forEach(vd=> { const key=`${vd.field}|${vd.agg||'sum'}`; const fmt=formats[key]||{}; const wanSuffix=fmt.tenThousand?'万':''; valHeader.push(`${vd.field} ${vd.agg}${wanSuffix}`); }); }); headerRows.push(valHeader);
  const colAggTypes=[]; colKeys.forEach(_=>{ valDefs.forEach(vd=> colAggTypes.push(vd.agg)); });

  // 计算汇总行
  const summaryRow = [];
  for(let i = 0; i < rowFields.length; i++) {
    summaryRow.push(i === 0 ? '汇总' : '');
  }
  
  // 从层级结构计算汇总值
  const totalData = new Map();
  function collectTotalData(node) {
    if (node.children.size === 0) {
      // 叶子节点，收集数据
      for (const [ck, bucket] of node.data) {
        if (!totalData.has(ck)) totalData.set(ck, {});
        const totalBucket = totalData.get(ck);
        Object.keys(bucket).forEach(k => {
          if (!totalBucket[k]) totalBucket[k] = initAgg();
          const agg = bucket[k];
          totalBucket[k].sum += agg.sum;
          totalBucket[k].count += agg.count;
          if (agg.min < totalBucket[k].min) totalBucket[k].min = agg.min;
          if (agg.max > totalBucket[k].max) totalBucket[k].max = agg.max;
        });
      }
    } else {
      // 递归收集子节点数据
      for (const child of node.children.values()) {
        collectTotalData(child);
      }
    }
  }
  collectTotalData(hierarchy);
  
  // 为汇总行计算创建全局访问器
  const globalTotalData = new Map();
  for (const [ck, bucket] of totalData) {
    for (const [fieldName, agg] of Object.entries(bucket)) {
      if (!globalTotalData.has(fieldName)) {
        globalTotalData.set(fieldName, initAgg());
      }
      const globalAgg = globalTotalData.get(fieldName);
      globalAgg.sum += agg.sum;
      globalAgg.count += agg.count;
      globalAgg.min = Math.min(globalAgg.min, agg.min);
      globalAgg.max = Math.max(globalAgg.max, agg.max);
    }
  }
  
  // 预先计算所有自定义字段的汇总值（只计算一次）
  const computedSummaryValues = new Map();
  if (computedNames.size > 0) {
    // 创建汇总行数据对象，使用与非自定义字段相同的汇总逻辑
    const summaryRowData = {};
    
    // 对每个字段，取第一列的汇总值作为该字段的总汇总值
    // 因为在pivot结构中，每个字段的总汇总应该是相同的，不管在哪一列
    if (colKeys.length > 0) {
      const firstColKey = colKeys[0];
      const firstBucket = totalData.get(firstColKey) || {};
      Object.keys(firstBucket).forEach(fieldName => {
        const agg = firstBucket[fieldName] || initAgg();
        summaryRowData[fieldName] = valueAgg(agg, 'sum');
        
        // 处理字段名称的变体，确保公式能找到正确的字段
        if (fieldName === '总模版花费') {
          summaryRowData['总模板花费'] = valueAgg(agg, 'sum');
        }
        if (fieldName === '总模板花费') {
          summaryRowData['总模版花费'] = valueAgg(agg, 'sum');
        }
      });
    }
    
    // 为每个自定义字段计算汇总值，需要考虑字段间的依赖关系
    // 先计算所有非依赖其他自定义字段的字段，然后再计算依赖字段
    const processedFields = new Set();
    const remainingDefs = [...computedDefs];
    
    // 多轮处理，直到所有字段都被处理
    while (remainingDefs.length > 0 && processedFields.size < computedDefs.length) {
      const currentRoundProcessed = [];
      
      for (let i = remainingDefs.length - 1; i >= 0; i--) {
        const def = remainingDefs[i];
        
        // 检查当前字段是否依赖其他尚未处理的自定义字段
        const dependencies = extractVars(def.expr);
        const unprocessedDeps = dependencies.filter(dep => 
          computedNames.has(dep) && !processedFields.has(dep)
        );
        
        if (unprocessedDeps.length === 0) {
          // 没有未处理的依赖，可以计算此字段
          try {
            // Use aggregation function with get accessor for summary context
            const get = (fieldName) => {
              if (computedSummaryValues.has(fieldName)) {
                return computedSummaryValues.get(fieldName);
              }
              return summaryRowData[fieldName] || 0;
            };
            
            const val = def.fnAgg ? def.fnAgg(get) : 0;
            computedSummaryValues.set(def.name, val);
            processedFields.add(def.name);
            currentRoundProcessed.push(i);
          } catch(e) {
            console.error('汇总行计算字段错误:', def.name, e);
            computedSummaryValues.set(def.name, 0);
            processedFields.add(def.name);
            currentRoundProcessed.push(i);
          }
        }
      }
      
      // 移除已处理的字段（indices already in reverse order from backward iteration）
      currentRoundProcessed.forEach(index => {
        remainingDefs.splice(index, 1);
      });
      
      // 如果一轮下来没有处理任何字段，说明存在循环依赖，退出循环
      if (currentRoundProcessed.length === 0) {
        console.warn('检测到自定义字段循环依赖，剩余字段:', remainingDefs.map(d => d.name));
        remainingDefs.forEach(def => {
          computedSummaryValues.set(def.name, 0);
        });
        break;
      }
    }
  }

  // 为每个列计算汇总值
  colKeys.forEach(ck => {
    const bucket = totalData.get(ck) || {};
    valDefs.forEach(vd => {
      let totalVal = 0;
      if (computedNames.has(vd.field)) {
        // 使用预先计算好的自定义字段汇总值
        totalVal = computedSummaryValues.get(vd.field) || 0;
      } else {
        const a = bucket[vd.field] || initAgg();
        totalVal = valueAgg(a, vd.agg);
      }
      summaryRow.push(totalVal);
    });
  });

  return {headerRows, dataRows, summaryRow, allRowData, rowFields, colFields, valDefs, colAggTypes, colKeys, rows: baseRows};
}

function renderRawTable(rows){
  if(!Array.isArray(rows) || rows.length === 0) {
    pivotContainer.innerHTML='<div class="small">没有数据</div>';
    btnExport.disabled=true;
    return;
  }
  const headers=Object.keys(rows[0]||{});
  const table=document.createElement('table');
  const thead=document.createElement('thead');
  const trh=document.createElement('tr');
  headers.forEach(h=>{ const th=document.createElement('th'); th.textContent=h; trh.appendChild(th); });
  thead.appendChild(trh); table.appendChild(thead);
  const tbody=document.createElement('tbody');
  rows.forEach(r=>{ const tr=document.createElement('tr'); headers.forEach((h,ci)=>{ const td=document.createElement('td'); td.textContent=String(r[h]??''); td.dataset.col=ci; tr.appendChild(td); }); tbody.appendChild(tr); });
  table.appendChild(tbody);
  pivotContainer.innerHTML=''; pivotContainer.appendChild(table); btnExport.disabled=false;
  enableCrosshair(table);
}

function renderPivot(){
  const base=Array.isArray(rawBaseRows) ? rawBaseRows : [];
  if(!base.length){ pivotContainer.innerHTML='<div class="small">没有数据</div>'; rowsBadge.textContent='Rows: 0'; btnExport.disabled=true; return; }
  
  // 使用筛选后的数据或原始数据
  const filteredBase = filteredRows.length > 0 ? filteredRows : applyFilters();
  currentRows = filteredBase.length > 0 ? filteredBase : applyComputed(base);
  
  rebuildAvailableFields(); renderZones(); buildFilterUI(); 
  rowsBadge.textContent=`Rows: ${Array.isArray(currentRows) ? currentRows.length : 0}`;
  if(viewMode==='raw') return renderRawTable(currentRows);

  // 使用筛选后的数据进行透视计算
  const pivotBase = filteredBase.length > 0 ? filteredBase : base;
  const {headerRows, dataRows, summaryRow, allRowData, rowFields, colFields, valDefs, colAggTypes, colKeys, rows} = pivotData(pivotBase);

  const thead=document.createElement('thead');
  headerRows.forEach((hr, ridx)=>{ const tr=document.createElement('tr'); hr.forEach((cell, ci)=>{ const th=document.createElement('th'); th.textContent = ridx<headerRows.length-1 ? (ci<rowFields.length ? (rowFields[ci]||'') : String(cell)) : String(cell); tr.appendChild(th); }); thead.appendChild(tr); });
  const tbody=document.createElement('tbody');

  allRowData.forEach((rowInfo, index) => {
    const r = rowInfo.row;
    const tr = document.createElement('tr');
    
    // 根据是否为小计行设置样式
    if (rowInfo.isSubtotal) {
      tr.className = 'subtotal-row';
      tr.style.cssText = 'background-color: #162032; font-weight: bold; border-top: 1px solid #334155;';
    }
    
    r.forEach((cell, ci) => {
      const td = document.createElement('td');
      
      // 小计行样式
      if (rowInfo.isSubtotal) {
        td.style.cssText = 'background-color: #162032; font-weight: bold;';
      }
      
      if (ci < rowFields.length) {
        // 行标签列 - 添加层级缩进
        const indent = Math.max(0, rowInfo.level - 1) * 20;
        if (indent > 0) {
          td.style.paddingLeft = `${6 + indent}px`;
        }
        
        // 小计行添加前缀
        if (rowInfo.isSubtotal && cell && ci === rowInfo.level - 1) {
          td.textContent = `${cell} 小计`;
        } else {
          td.textContent = String(cell);
        }
      } else {
        // 数值列
        const idx = ci - rowFields.length;
        const aggType = colAggTypes ? colAggTypes[idx % colAggTypes.length] : 'sum';
        const vd = valDefs[idx % valDefs.length];
        const key = `${vd.field}|${vd.agg||'sum'}`;
        const fmt = formats[key] || {decimals:2, thousand:true, currency:'', currencyPos:'prefix'};
        td.textContent = formatAgg(cell, aggType, fmt);
      }
      
      td.dataset.col = ci;
      tr.appendChild(td);
    });
    
    tbody.appendChild(tr);
  });

  const table=document.createElement('table'); table.appendChild(thead); table.appendChild(tbody);
  
  // 创建容器结构
  pivotContainer.innerHTML='';
  const mainContent = document.createElement('div');
  mainContent.className = 'pivot-main-content';
  mainContent.appendChild(table);
  pivotContainer.appendChild(mainContent);
  
  // 创建独立的汇总行容器
  if(summaryRow && summaryRow.length > 0) {
    const summaryContainer = document.createElement('div');
    summaryContainer.className = 'pivot-summary-container';
    
    const summaryTable = document.createElement('table');
    summaryTable.className = 'pivot-summary-table';
    
    // 创建汇总行表头（复制主表表头结构）
    const summaryThead = document.createElement('thead');
    summaryThead.style.display = 'none'; // 隐藏汇总表的表头
    summaryTable.appendChild(summaryThead);
    
    const summaryTbody = document.createElement('tbody');
    const summaryTr = document.createElement('tr');
    summaryTr.className = 'summary-row';
    
    summaryRow.forEach((cell, ci) => {
      const td = document.createElement('td');
      
      if(ci < rowFields.length) {
        td.textContent = String(cell);
      } else {
        const idx = ci - rowFields.length;
        const aggType = colAggTypes ? colAggTypes[idx % colAggTypes.length] : 'sum';
        const vd = valDefs[idx % valDefs.length];
        const key = `${vd.field}|${vd.agg||'sum'}`;
        const fmt = formats[key] || {decimals:2, thousand:true, currency:'', currencyPos:'prefix'};
        td.textContent = formatAgg(cell, aggType, fmt);
      }
      
      td.dataset.col = ci;
      summaryTr.appendChild(td);
    });
    
    summaryTbody.appendChild(summaryTr);
    summaryTable.appendChild(summaryTbody);
    summaryContainer.appendChild(summaryTable);
    pivotContainer.appendChild(summaryContainer);
  }
  
  btnExport.disabled=false;
  enableCrosshair(table);
  enableColumnResize(table);
  enableColumnSort(table, allRowData, rowFields, colFields, valDefs, colAggTypes, formats);
  
  // 同步汇总表格的列宽
  setTimeout(() => {
    syncSummaryTableColumns();
  }, 0);
}

// 同步汇总表格列宽与主表格
function syncSummaryTableColumns() {
  try {
    const mainTable = pivotContainer?.querySelector('.pivot-main-content table');
    const summaryTable = pivotContainer?.querySelector('.pivot-summary-table');
    
    if (!mainTable || !summaryTable) return;
    
    // 获取主表格的表头单元格
    const mainHeaders = mainTable.querySelectorAll('thead tr:last-child th');
    const summaryRows = summaryTable.querySelectorAll('tr');
    
    if (!mainHeaders.length || !summaryRows.length) return;
    
    // 清除之前的固定宽度设置，让表格自然重新布局
    mainTable.style.tableLayout = '';
    summaryTable.style.tableLayout = '';
    
    // 获取精确的列宽并同步
    requestAnimationFrame(() => {
      try {
        // 再次强制固定布局模式
        mainTable.style.tableLayout = 'fixed';
        summaryTable.style.tableLayout = 'fixed';
        
        requestAnimationFrame(() => {
          try {
            mainHeaders.forEach((th, index) => {
              // 使用 getBoundingClientRect 获取更精确的宽度
              const rect = th.getBoundingClientRect();
              const width = rect.width;
              
              if (width > 0) { // 确保宽度有效
                // 应用到汇总表格的对应列
                summaryRows.forEach(row => {
                  const cell = row.children[index];
                  if (cell) {
                    cell.style.width = width + 'px';
                    cell.style.minWidth = width + 'px';
                    cell.style.maxWidth = width + 'px';
                    cell.style.boxSizing = 'border-box';
                  }
                });
              }
            });
            
            // 确保汇总表格总宽度与主表格一致
            const mainTableRect = mainTable.getBoundingClientRect();
            if (mainTableRect.width > 0) {
              summaryTable.style.width = mainTableRect.width + 'px';
              summaryTable.style.minWidth = mainTableRect.width + 'px';
              summaryTable.style.maxWidth = mainTableRect.width + 'px';
            }
          } catch (e) {
            console.warn('同步汇总表格列宽时发生错误（内层）:', e);
          }
        });
      } catch (e) {
        console.warn('同步汇总表格列宽时发生错误（外层）:', e);
      }
    });
  } catch (e) {
    console.warn('同步汇总表格列宽时发生错误:', e);
  }
}

function enableCrosshair(table){
  let lastRow=null, lastColIndex=null;
  const clear=()=>{
    if(lastRow){ lastRow.classList.remove('hl-row'); lastRow=null; }
    if(lastColIndex!==null){
      // 清除主表格和汇总表格的高亮
      pivotContainer.querySelectorAll(`td[data-col="${lastColIndex}"]`).forEach(td=>td.classList.remove('hl-col','hl-hit'));
      lastColIndex=null;
    }
  };
  
  // 为主表和汇总表都添加事件监听
  const allTables = pivotContainer.querySelectorAll('table');
  allTables.forEach(tbl => {
    tbl.addEventListener('mouseleave', clear);
    tbl.addEventListener('mousemove', (e)=>{
      const td=e.target.closest('td'); if(!td) return;
      const tr=td.parentElement; const col=td.dataset.col;
      if(tr!==lastRow){ if(lastRow) lastRow.classList.remove('hl-row'); tr.classList.add('hl-row'); lastRow=tr; }
      if(col!==String(lastColIndex)){ 
        if(lastColIndex!==null){ 
          pivotContainer.querySelectorAll(`td[data-col="${lastColIndex}"]`).forEach(n=>n.classList.remove('hl-col','hl-hit')); 
        } 
        pivotContainer.querySelectorAll(`td[data-col="${col}"]`).forEach(n=>n.classList.add('hl-col')); 
        lastColIndex=Number(col); 
      }
      pivotContainer.querySelectorAll('td.hl-hit').forEach(n=>n.classList.remove('hl-hit')); 
      td.classList.add('hl-hit');
    });
  });
}

// 列宽调整功能
function enableColumnResize(table) {
  const headers = table.querySelectorAll('thead th');
  headers.forEach((th, index) => {
    // 添加调整手柄
    const resizer = document.createElement('div');
    resizer.className = 'column-resizer';
    resizer.style.cssText = 'position: absolute; top: 0; right: 0; width: 4px; height: 100%; cursor: col-resize; background: transparent;';
    
    th.style.position = 'relative';
    th.style.minWidth = '60px';
    th.appendChild(resizer);
    
    let startX = 0;
    let startWidth = 0;
    let isResizing = false;
    
    const onMouseDown = (e) => {
      isResizing = true;
      startX = e.clientX;
      startWidth = th.offsetWidth;
      document.addEventListener('mousemove', onMouseMove);
      document.addEventListener('mouseup', onMouseUp);
      e.preventDefault();
    };
    
    const onMouseMove = (e) => {
      if (!isResizing) return;
      const newWidth = Math.max(60, startWidth + (e.clientX - startX));
      th.style.width = newWidth + 'px';
      th.style.minWidth = newWidth + 'px';
      th.style.maxWidth = newWidth + 'px';
      
      // 同步主表格中所有相同列的单元格宽度
      const mainTable = pivotContainer.querySelector('.pivot-main-content table');
      if (mainTable) {
        const mainColCells = mainTable.querySelectorAll(`td:nth-child(${index + 1}), th:nth-child(${index + 1})`);
        mainColCells.forEach(cell => {
          cell.style.width = newWidth + 'px';
          cell.style.minWidth = newWidth + 'px';
          cell.style.maxWidth = newWidth + 'px';
          cell.style.boxSizing = 'border-box';
        });
      }
      
      // 实时同步汇总表格的对应列宽
      const summaryTable = pivotContainer.querySelector('.pivot-summary-table');
      if (summaryTable) {
        const summaryColCells = summaryTable.querySelectorAll(`td:nth-child(${index + 1}), th:nth-child(${index + 1})`);
        summaryColCells.forEach(cell => {
          cell.style.width = newWidth + 'px';
          cell.style.minWidth = newWidth + 'px';
          cell.style.maxWidth = newWidth + 'px';
          cell.style.boxSizing = 'border-box';
        });
      }
    };
    
    const onMouseUp = () => {
      isResizing = false;
      document.removeEventListener('mousemove', onMouseMove);
      document.removeEventListener('mouseup', onMouseUp);
      
      // 列宽调整完成后，触发完整的汇总表格同步
      setTimeout(() => {
        syncSummaryTableColumns();
      }, 10);
    };
    
    resizer.addEventListener('mousedown', onMouseDown);
  });
}

// 排序功能
function enableColumnSort(table, allRowData, rowFields, colFields, valDefs, colAggTypes, formats) {
  const headers = table.querySelectorAll('thead tr:last-child th');
  
  headers.forEach((th, colIndex) => {
    // 只对聚合列添加排序功能
    if (colIndex >= rowFields.length) {
      th.style.cursor = 'pointer';
      th.style.userSelect = 'none';
      th.setAttribute('data-sortable', 'true');
      
      // 添加排序指示器
      const sortIndicator = document.createElement('span');
      sortIndicator.className = 'sort-indicator';
      sortIndicator.style.cssText = 'margin-left: 5px; opacity: 0.5; font-size: 10px;';
      sortIndicator.textContent = '⇅';
      th.appendChild(sortIndicator);
      
      let currentSort = null; // null, 'asc', 'desc'
      
      th.addEventListener('click', (e) => {
        e.preventDefault();
        
        // 清除其他列的排序状态
        headers.forEach((otherTh, otherIndex) => {
          if (otherIndex !== colIndex) {
            const otherIndicator = otherTh.querySelector('.sort-indicator');
            if (otherIndicator) {
              otherIndicator.textContent = '⇅';
              otherIndicator.style.opacity = '0.5';
            }
          }
        });
        
        // 切换当前列的排序状态
        if (currentSort === null || currentSort === 'desc') {
          currentSort = 'asc';
          sortIndicator.textContent = '↑';
          sortIndicator.style.opacity = '1';
        } else {
          currentSort = 'desc';
          sortIndicator.textContent = '↓';
          sortIndicator.style.opacity = '1';
        }
        
        // 执行排序
        sortTableByColumn(table, allRowData, colIndex, currentSort, rowFields, colFields, valDefs, colAggTypes, formats);
      });
    }
  });
}

// 按指定列对表格进行排序
function sortTableByColumn(table, allRowData, colIndex, direction, rowFields, colFields, valDefs, colAggTypes, formats) {
  const tbody = table.querySelector('tbody');
  
  // 对层级数据进行智能排序 - 只对叶子节点（非小计行）进行排序
  const leafRows = allRowData.filter(rowInfo => !rowInfo.isSubtotal);
  const subtotalRows = allRowData.filter(rowInfo => rowInfo.isSubtotal);
  
  // 对叶子节点排序
  leafRows.sort((a, b) => {
    const aVal = a.row[colIndex];
    const bVal = b.row[colIndex];
    const aNum = num(aVal);
    const bNum = num(bVal);
    
    const result = aNum - bNum;
    return direction === 'asc' ? result : -result;
  });
  
  // 构建排序后的完整行数据结构
  const sortedAllRows = [];
  
  // 如果没有层级结构，直接使用排序结果
  if (rowFields.length <= 1) {
    sortedAllRows.push(...leafRows, ...subtotalRows);
  } else {
    // 有层级结构时，需要重新组织数据以保持层级关系
    const groupMap = new Map();
    
    // 按第一级分组
    leafRows.forEach(rowInfo => {
      const groupKey = rowInfo.path[0] || '';
      if (!groupMap.has(groupKey)) {
        groupMap.set(groupKey, []);
      }
      groupMap.get(groupKey).push(rowInfo);
    });
    
    // 按每组的总和排序组别
    const sortedGroups = Array.from(groupMap.entries()).sort((a, b) => {
      const aSum = a[1].reduce((sum, row) => sum + num(row.row[colIndex]), 0);
      const bSum = b[1].reduce((sum, row) => sum + num(row.row[colIndex]), 0);
      return direction === 'asc' ? aSum - bSum : bSum - aSum;
    });
    
    // 重新构建排序后的行
    sortedGroups.forEach(([groupKey, groupRows]) => {
      sortedAllRows.push(...groupRows);
      
      // 添加对应的小计行
      const groupSubtotals = subtotalRows.filter(s => s.path[0] === groupKey);
      sortedAllRows.push(...groupSubtotals);
    });
  }
  
  // 重新渲染表格主体
  tbody.innerHTML = '';
  
  // 添加排序后的所有行
  sortedAllRows.forEach(rowInfo => {
    const tr = createRowElement(rowInfo, rowFields, colFields, valDefs, colAggTypes, formats);
    tbody.appendChild(tr);
  });
}

// 创建行元素的辅助函数
function createRowElement(rowInfo, rowFields, colFields, valDefs, colAggTypes, formats) {
  const r = rowInfo.row;
  const tr = document.createElement('tr');
  
  if (rowInfo.isSubtotal) {
    tr.className = 'subtotal-row';
    tr.style.cssText = 'background-color: #162032; font-weight: bold; border-top: 1px solid #334155;';
  }
  
  r.forEach((cell, ci) => {
    const td = document.createElement('td');
    
    if (rowInfo.isSubtotal) {
      td.style.cssText = 'background-color: #162032; font-weight: bold;';
    }
    
    if (ci < rowFields.length) {
      const indent = Math.max(0, rowInfo.level - 1) * 20;
      if (indent > 0) {
        td.style.paddingLeft = `${6 + indent}px`;
      }
      
      if (rowInfo.isSubtotal && cell && ci === rowInfo.level - 1) {
        td.textContent = `${cell} 小计`;
      } else {
        td.textContent = String(cell);
      }
    } else {
      const idx = ci - rowFields.length;
      const aggType = colAggTypes ? colAggTypes[idx % colAggTypes.length] : 'sum';
      const vd = valDefs[idx % valDefs.length];
      const key = `${vd.field}|${vd.agg||'sum'}`;
      const fmt = formats[key] || {decimals:2, thousand:true, currency:'', currencyPos:'prefix'};
      td.textContent = formatAgg(cell, aggType, fmt);
    }
    
    td.dataset.col = ci;
    tr.appendChild(td);
  });
  
  return tr;
}

btnExport.onclick=()=>{ 
  const allTables=pivotContainer.querySelectorAll('table'); 
  if(!allTables.length) return; 
  const rows=[]; 
  allTables.forEach(t=>{ 
    t.querySelectorAll('tr').forEach(tr=>{ 
      rows.push([...tr.children].map(td=>`"${String(td.textContent).replace(/"/g,'""')}"`).join(',')); 
    }); 
  }); 
  const csv=rows.join('\n'); 
  const blob=new Blob([csv],{type:'text/csv;charset=utf-8;'}); 
  const url=URL.createObjectURL(blob); 
  const a=document.createElement('a'); 
  a.href=url; 
  a.download=`pivot_${new Date().toISOString().replace(/[:.]/g,'-')}.csv`; 
  document.body.appendChild(a); 
  a.click(); 
  setTimeout(()=>{document.body.removeChild(a); URL.revokeObjectURL(url);},0); 
};

// 筛选按钮事件处理
btnApplyFilters.onclick=()=>{
  updateFilters();
  applyFilters();
  renderPivot();
  log(`应用筛选完成，剩余数据: ${filteredRows.length} 行`);
};

btnClearFilters.onclick=()=>{
  rowFieldFilters = {};
  metricFieldFilters = {};
  filteredRows = [];
  buildFilterUI();
  renderPivot();
  log('已清除所有筛选条件');
};

// 面板折叠/展开功能
toggleFilterEl.onclick=()=>{
  filterPanelEl.classList.toggle('collapsed');
  toggleFilterEl.textContent = filterPanelEl.classList.contains('collapsed') ? '▶' : '◀';
  // 折叠/展开后需要重新同步汇总表格列宽
  setTimeout(() => {
    syncSummaryTableColumns();
  }, 300); // 等待CSS动画完成
};

toggleConfigEl.onclick=()=>{
  configPanelEl.classList.toggle('collapsed');
  toggleConfigEl.textContent = configPanelEl.classList.contains('collapsed') ? '▶' : '◀';
  // 折叠/展开后需要重新同步汇总表格列宽
  setTimeout(() => {
    syncSummaryTableColumns();
  }, 300); // 等待CSS动画完成
};

// 面板拖拽调整宽度功能
function initResize(handle, panel) {
  let isResizing = false;
  let startX = 0;
  let startWidth = 0;

  handle.addEventListener('mousedown', (e) => {
    isResizing = true;
    startX = e.clientX;
    startWidth = parseInt(window.getComputedStyle(panel).width, 10);
    document.addEventListener('mousemove', onMouseMove);
    document.addEventListener('mouseup', onMouseUp);
    e.preventDefault();
  });

  function onMouseMove(e) {
    if (!isResizing) return;
    const width = startWidth + e.clientX - startX;
    const minWidth = panel === filterPanelEl ? 200 : 300;
    const maxWidth = panel === filterPanelEl ? 500 : 800;
    
    if (width >= minWidth && width <= maxWidth) {
      panel.style.width = width + 'px';
      if (panel === configPanelEl) {
        panel.style.minWidth = width + 'px';
      }
    }
  }

  function onMouseUp() {
    isResizing = false;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseup', onMouseUp);
    // 拖拽完成后重新同步汇总表格列宽
    setTimeout(() => {
      syncSummaryTableColumns();
    }, 50);
  }
}

// 初始化调整大小功能
if (filterResizeEl && filterPanelEl) initResize(filterResizeEl, filterPanelEl);
if (configResizeEl && configPanelEl) initResize(configResizeEl, configPanelEl);

// 表格冻结功能
function applyFreeze() {
  const mainContent = pivotContainer.querySelector('.pivot-main-content');
  const table = mainContent ? mainContent.querySelector('table') : null;
  if (!table) return;
  
  const freezeRows = parseInt(freezeRowsEl.value) || 0;
  const freezeCols = parseInt(freezeColsEl.value) || 0;
  
  // 清除之前的冻结状态
  clearFreeze();
  
  if (freezeRows === 0 && freezeCols === 0) return;
  
  pivotContainer.classList.add('frozen');
  
  // 冻结行
  if (freezeRows > 0) {
    const headerRows = table.querySelectorAll('thead tr');
    const bodyRows = table.querySelectorAll('tbody tr');
    
    // 冻结表头
    headerRows.forEach(row => {
      row.classList.add('frozen-row');
    });
    
    // 冻结指定数量的数据行
    for (let i = 0; i < Math.min(freezeRows - headerRows.length, bodyRows.length); i++) {
      if (bodyRows[i]) {
        bodyRows[i].classList.add('frozen-row');
        bodyRows[i].style.top = `${(headerRows.length + i) * 32}px`;
      }
    }
  }
  
  // 冻结列
  if (freezeCols > 0) {
    // 处理主表格和汇总表格
    const allTables = pivotContainer.querySelectorAll('table');
    let leftOffset = 0;
    
    for (let colIndex = 0; colIndex < freezeCols; colIndex++) {
      allTables.forEach(tbl => {
        const allRows = tbl.querySelectorAll('tr');
        allRows.forEach(row => {
          const cell = row.children[colIndex];
          if (cell) {
            cell.classList.add('frozen-col');
            cell.style.left = `${leftOffset}px`;
            
            // 角落单元格（既是冻结行又是冻结列）
            if ((row.closest('thead') || row.classList.contains('frozen-row')) && colIndex < freezeCols) {
              cell.classList.add('frozen-corner');
            }
          }
        });
      });
      
      // 计算下一列的偏移（基于主表格）
      const sampleCell = table.querySelector(`tr td:nth-child(${colIndex + 1}), tr th:nth-child(${colIndex + 1})`);
      if (sampleCell) {
        leftOffset += sampleCell.offsetWidth;
      }
    }
  }
  
  log(`已应用冻结: ${freezeRows}行 ${freezeCols}列`);
}

function clearFreeze() {
  const mainContent = pivotContainer.querySelector('.pivot-main-content');
  const table = mainContent ? mainContent.querySelector('table') : null;
  if (!table) return;
  
  pivotContainer.classList.remove('frozen');
  
  // 清除所有冻结相关的类和样式（包括汇总表格）
  pivotContainer.querySelectorAll('.frozen-row, .frozen-col, .frozen-corner').forEach(cell => {
    cell.classList.remove('frozen-row', 'frozen-col', 'frozen-corner');
    cell.style.removeProperty('top');
    cell.style.removeProperty('left');
  });
  
  log('已取消表格冻结');
}

// 冻结按钮事件
btnApplyFreeze.onclick = applyFreeze;
btnClearFreeze.onclick = clearFreeze;

function tryParseJSON(s){ if(!s) return {}; try{ return JSON.parse(s); }catch{ return {}; } }
function makeBody(){ return {collection: collEl.value, filters: tryParseJSON(filtersEl.value), limit: Number(limitEl.value||5000), skip: Number(skipEl.value||0), projection: {"_id":0}}; }
async function postQuery(body){ try{ const r=await fetch(`${apiBaseEl.value}/api/query`,{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}); const j=await r.json(); return Array.isArray(j.rows) ? j.rows : []; }catch(e){ log('查询失败: '+e.message); return []; } }

btnLoad.onclick=async ()=>{
  const filt=tryParseJSON(filtersEl.value);
  if(isUploadedMode){
    const uploadRows = Array.isArray(rawUploadRows) ? rawUploadRows : [];
    rawBaseRows = uploadRows.filter(r => matchesFilter(r, filt));
    log(`本地数据（上传）应用过滤后：${rawBaseRows.length} 行`);
    renderPivot(); return;
  }
  const body=makeBody(); currentCollection=body.collection; loadState(); rawBaseRows=await postQuery(body); renderPivot(); btnSaveCloud.disabled=false; btnLoadCloud.disabled=false; btnListCloud.disabled=false; await loadCloudList();
};
async function doPeek(){ try{ const url=`${apiBaseEl.value}/api/peek?collection=${encodeURIComponent(collEl.value)}`; isUploadedMode=false; currentCollection=collEl.value; loadState(); const r=await fetch(url); const j=await r.json(); rawBaseRows=Array.isArray(j.rows) ? j.rows : []; renderPivot(); btnSaveCloud.disabled=false; btnLoadCloud.disabled=false; btnListCloud.disabled=false; await loadCloudList(); }catch(e){ log('查看数据失败: '+e.message); rawBaseRows=[]; renderPivot(); } }
btnPeek.onclick=doPeek;

btnUpload.onclick=async ()=>{
  const f=fileInput.files && fileInput.files[0]; if(!f){ alert('请选择文件'); return; }
  
  // 显示上传进度
  btnUpload.disabled = true;
  btnUpload.textContent = '上传中...';
  
  try {
    const fd=new FormData();
    fd.append('file', f);
    if(sheetInput.value) fd.append('sheet', sheetInput.value);
    fd.append('start_row', String(Number(startRowInput.value||1)));
    
    const r=await fetch(`${apiBaseEl.value}/api/upload`,{method:'POST', body: fd});
    const j=await r.json();
    
    if(!r.ok) {
      throw new Error(j.detail || '上传失败');
    }
    
    if(j && Array.isArray(j.rows)){
      rawUploadRows=j.rows; rawBaseRows=rawUploadRows.slice(); isUploadedMode=true;
      const label=`__upload__::${j.filename||f.name}`;
      let found=false; [...collEl.options].forEach(o=>{ if(o.value===label) found=true; });
      if(!found){ const o=document.createElement('option'); o.value=label; o.textContent=label; collEl.appendChild(o); }
      collEl.value=label; currentCollection=label; loadState(); renderPivot();
      btnSaveCloud.disabled=false; btnLoadCloud.disabled=false; btnListCloud.disabled=false;
      log(`上传完成：${j.filename}，行数=${j.count}${j.message ? '，' + j.message : ''}`);
      await loadCloudList();
    }else{ 
      throw new Error('服务器返回数据格式错误或没有有效数据'); 
    }
  } catch(e) {
    log('上传失败：' + e.message);
    alert('上传失败：' + e.message);
  } finally {
    btnUpload.disabled = false;
    btnUpload.textContent = '读取并加载';
  }
};

btnAddCalc.onclick=()=>{ 
  const name=(calcNameEl.value||'').trim(); 
  const expr=(calcExprEl.value||'').trim(); 
  if(!name||!expr) return; 
  
  // Remove existing field with the same name
  computedDefs=computedDefs.filter(d=>d.name!==name); 
  
  // Add the new field first
  computedDefs.push({name,expr,fn:null,fnAgg:null}); 
  
  // Now recompile all computed fields to ensure proper field references
  computedDefs = computedDefs.map(def => ({
    ...def,
    fn: compileExpr(def.expr),
    fnAgg: compileAggExpr(def.expr)
  }));
  
  calcNameEl.value=''; 
  calcExprEl.value=''; 
  renderComputedList(); 
  renderPivot(); 
  saveState(); 
};
function renderComputedList(){ 
  computedListEl.innerHTML=''; 
  computedDefs.forEach((d,i)=>{ 
    const w=document.createElement('div'); 
    w.className='field'; 
    w.draggable=true; 
    w.dataset.field=d.name; 
    w.innerHTML=`<b>${d.name}</b> = <code>${d.expr}</code> <span class='remove'>✕</span>`; 
    w.addEventListener('dragstart',onDragStart); 
    w.querySelector('.remove').onclick=()=>{ 
      computedDefs.splice(i,1); 
      
      // Recompile remaining computed fields to update field references
      computedDefs = computedDefs.map(def => ({
        ...def,
        fn: compileExpr(def.expr),
        fnAgg: compileAggExpr(def.expr)
      }));
      
      renderComputedList(); 
      renderPivot(); 
      saveState(); 
    }; 
    computedListEl.appendChild(w); 
  }); 
}

btnSaveCloud.disabled=true; btnLoadCloud.disabled=true; btnListCloud.disabled=true;
viewModeEl.onchange=()=>{ viewMode=viewModeEl.value; saveState(); renderPivot(); };
subtotalToggleEl.onchange=()=>{ subtotalEnabled=!!subtotalToggleEl.checked; saveState(); renderPivot(); };

iferrAllToggle && (iferrAllToggle.onchange=()=>{ iferrDefaultEnabled=!!iferrAllToggle.checked; saveState(); renderPivot(); });
iferrFallbackEl && (iferrFallbackEl.oninput=()=>{ saveState(); renderPivot(); });

btnSaveCloud.onclick=async ()=>{ if(!currentCollection) return; const name=(profileNameEl.value||'').trim(); if(!name) return; const body={collection: currentCollection, name, layout, hiddenFields:[...hiddenFields], formulas: computedDefs.map(({name,expr})=>({name,expr})), formats, subtotalEnabled, viewMode, iferrorAllEnabled: !!iferrDefaultEnabled, iferrorFallback: Number(iferrFallbackEl?.value ?? 0) || 0 }; const r=await fetch(`${apiBaseEl.value}/api/prefs/save`,{method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body)}); const j=await r.json(); log('保存云端配置: '+JSON.stringify(j)); await loadCloudList(); };
async function loadCloudList(){ const url=`${apiBaseEl.value}/api/prefs/list`; try{ const r=await fetch(url); const j=await r.json(); const items=j.items||[]; const cloudListEl=$('#cloudList'); cloudListEl.innerHTML=''; if(items.length===0){ cloudListEl.innerHTML='<div class="small">暂无保存的配置</div>'; return; } items.forEach(item=>{ const div=document.createElement('div'); div.className='cloud-item'; div.style.cssText='margin:4px 0;padding:8px;background:#0f1627;border:1px solid #2a374d;border-radius:6px;cursor:pointer;display:flex;justify-content:space-between;align-items:center;'; div.innerHTML=`<span onclick="loadCloudConfig('${item.collection}','${item.name}')" style="flex:1;color:#e7ecf6;">[${item.collection}] ${item.name}</span><span class="small" style="color:#9fb0c7;margin-left:8px;">${item.updatedAt||''}</span><span onclick="deleteCloudConfig('${item.collection}','${item.name}')" style="margin-left:8px;color:#f87171;cursor:pointer;">✕</span>`; cloudListEl.appendChild(div); }); }catch(e){ log('加载配置列表失败: '+e.message); } } window.loadCloudConfig=async (collection, name)=>{ if(!collection || !name) return; profileNameEl.value=name; const url=`${apiBaseEl.value}/api/prefs/get?collection=${encodeURIComponent(collection)}&name=${encodeURIComponent(name)}`; try{ const r=await fetch(url); const j=await r.json(); if(j && j.doc){ const d=j.doc; layout=d.layout||{rows:[],cols:[],vals:[]}; hiddenFields=new Set(d.hiddenFields||[]); // Load computed fields first without functions
        computedDefs = (d.formulas||[]).map(x => ({...x, fn: null, fnAgg: null}));
        
        // Then compile all expressions to ensure proper field references
        computedDefs = computedDefs.map(def => ({
          ...def,
          fn: compileExpr(def.expr),
          fnAgg: compileAggExpr(def.expr)
        })); formats=d.formats||{}; subtotalEnabled=!!d.subtotalEnabled; viewMode=d.viewMode||'pivot'; iferrDefaultEnabled=!!d.iferrorAllEnabled; iferrDefaultFallback=Number(d.iferrorFallback||0); if(iferrAllToggle) iferrAllToggle.checked=!!iferrDefaultEnabled; if(iferrFallbackEl) iferrFallbackEl.value=String(iferrDefaultFallback); renderComputedList(); rebuildAvailableFields(); renderZones(); viewModeEl.value=viewMode; subtotalToggleEl.checked=subtotalEnabled; renderPivot(); saveState(); log(`加载配置: [${collection}] ${name}`); }else{ log('配置不存在: '+name); } }catch(e){ log('加载配置失败: '+e.message); } }; window.deleteCloudConfig=async (collection, name)=>{ if(!confirm(`确定删除配置 "[${collection}] ${name}" 吗？`)) return; const url=`${apiBaseEl.value}/api/prefs/delete?collection=${encodeURIComponent(collection)}&name=${encodeURIComponent(name)}`; try{ const r=await fetch(url,{method:'DELETE'}); const j=await r.json(); log(`删除配置: [${collection}] ${name}`); await loadCloudList(); }catch(e){ log('删除失败: '+e.message); } }; btnLoadCloud.onclick=async ()=>{ if(!currentCollection) return; const name=(profileNameEl.value||'').trim(); if(!name) return; await loadCloudConfig(currentCollection, name); }; btnListCloud.onclick=loadCloudList;

// 添加窗口大小改变监听器，重新同步列宽
window.addEventListener('resize', () => {
  clearTimeout(window.resizeTimeout);
  window.resizeTimeout = setTimeout(() => {
    syncSummaryTableColumns();
  }, 50);
});

// 监听浏览器缩放事件
let lastZoomLevel = window.devicePixelRatio;
function checkZoomChange() {
  const currentZoomLevel = window.devicePixelRatio;
  if (Math.abs(currentZoomLevel - lastZoomLevel) > 0.01) {
    lastZoomLevel = currentZoomLevel;
    syncSummaryTableColumns();
  }
}

// 定期检查缩放变化
setInterval(checkZoomChange, 200);

// 监听视觉视口变化（更精确的缩放检测）
if (window.visualViewport) {
  window.visualViewport.addEventListener('resize', () => {
    clearTimeout(window.zoomTimeout);
    window.zoomTimeout = setTimeout(() => {
      syncSummaryTableColumns();
    }, 50);
  });
}

(function(){ setApiBaseFromConfig(); smartPingAndInit().then(()=> { log('前端初始化完成（IFERROR 全局兜底 • 修复 DIV v3 + Upload + Crosshair • repack）'); loadCloudList(); }); })();
})();