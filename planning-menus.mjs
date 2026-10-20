import {moneyControl,dateControl,readMoneyInput} from './form-inputs.mjs?v=543d9938d200573c';

const loanNames={mortgage:'주택담보대출',credit:'신용대출',sub:'청약담보대출'};
export const leaveGroups=[
  ['출산과 출산휴가',[
    ['birth_date','출산 예정일','date'],['birth_one_off','출산 일회성 비용'],
    ['maternity_start','아내 출산휴가 시작일','date'],['maternity_months','출산휴가 개월','int'],
    ['maternity_pay_m12','출산휴가 첫 두 달 · 월 수령액'],['maternity_pay_m3','출산휴가 세 번째 달 수령액'],
  ]],
  ['아내 육아휴직과 복직',[
    ['wife_leave_start','육아휴직 시작일','date'],['wife_leave_months','쉬는 개월','int'],
    ['return_delay_months','복직 추가 지연 개월','int'],['wife_gov_benefit_months','정부 급여 지급 개월','int'],
    ['wife_ordinary_wage','월 통상임금'],['wife_company_topup','회사 월 보전액'],
    ['wife_company_topup_months','회사 보전 개월','int'],
  ]],
  ['남편 육아휴직',[
    ['husband_leave_use','남편 육아휴직 사용','bool'],['husband_leave_start','육아휴직 시작일','date'],
    ['husband_leave_months','쉬는 개월','int'],['husband_gov_benefit_months','정부 급여 지급 개월','int'],
    ['husband_ordinary_wage','월 통상임금'],['husband_company_topup','회사 월 보전액'],
    ['husband_company_topup_months','회사 보전 개월','int'],
  ]],
  ['급여 지급 기준',[
    ['parents_6p6','부모 함께 육아휴직 6+6 적용','bool'],['benefit_pay_delay_months','휴직급여 입금 지연 개월','int'],
  ]],
];

export function repaymentCsv(rows){
  return '\ufeff'+[['날짜','구분','상환 원금','이자','수수료','납부 합계','남은 원금'],...rows.map(r=>[r.date,r.kind,r.principal,r.interest,r.fee,r.total,r.balance])].map(r=>r.join(',')).join('\r\n');
}

export function createPlanningMenus(ctx){
  const {state,$,$$,esc,won,shortMoney,clone,api,post,toast,field,checkField,openModal,closeModal,confirmation,render,calculate,validInputs}=ctx;
  let loan='mortgage',year='all',importPreview=null,importSnapshot=null,importWorkspace=null,importMode='new',importGeneration=0;
  const tools=()=>ctx.upgrades();
  const staleNotice=()=>state.calculatedSnapshot!==JSON.stringify(state.draft)?'<p class="recalculate-note">입력이 바뀌었습니다. 다시 계산하면 새 조건의 결과를 보여드려요.</p>':'';
  const buttons=()=>'<div class="bottom-actions"><button class="button" data-menu="calculate">다시 계산</button><button class="button primary" data-action="save">변경사항 저장</button></div>';
  const formField=(id,label,value='',kind='text')=>`<div class="field"><label for="${id}">${esc(label)}</label>${kind==='money'?moneyControl(id,label,value):kind==='date'?dateControl(id,label,value):`<input id="${id}" autocomplete="off" type="text" value="${esc(value)}">`}</div>`;
  const select=(id,label,options,value)=>`<div class="field"><label for="${id}">${esc(label)}</label><select id="${id}">${[...new Set([...options,value].filter(Boolean))].map(o=>`<option ${o===value?'selected':''}>${esc(o)}</option>`).join('')}</select></div>`;
  const number=id=>{const raw=$('#'+id).value.trim(),n=Number(raw);if(!raw||!Number.isFinite(n)||n<0||n>100)throw new Error('금리를 0~100%로 입력하세요.');return n/100;};
  const money=id=>{const n=readMoneyInput($('#'+id));if(n==null)throw new Error('금액을 입력하세요.');return n;};
  const uuid=prefix=>`${prefix}-${crypto.randomUUID()}`;
  function renderLeave(){
    const incomes={};
    for(const row of state.result?.ledger||[]){if(row.category==='income'){const month=row.date.slice(0,7);incomes[month]=(incomes[month]||0)+row.amount;}}
    return staleNotice()+leaveGroups.map(([title,fields])=>`<section class="card form-section"><h2>${title}</h2><div class="fields">${fields.map(([key,label,kind])=>kind==='bool'?checkField(key,label):field(key,label,kind||'money')).join('')}</div></section>`).join('')+`<section class="card"><h2>휴직 계획을 현금흐름에 반영하기</h2><p class="hint">평소 급여는 대출·가계에서, 출산 후 생활비·양육비는 기간별 지출에서 정하세요. 위 설정은 출산휴가·휴직 중 급여와 정부급여 입금 시점에 반영합니다. 시작일이 비어 있으면 해당 휴직 일정은 적용되지 않습니다.</p><a class="button small" href="#settings">생활비·양육비 설정 →</a><details><summary>계산된 월별 급여·휴직 수령액 보기</summary><p class="hint">현재 계산 기간의 두 사람 합계이며, 일회성 자금·부모님 지원은 제외합니다.</p><div class="table-wrap menu-scroll"><table><thead><tr><th>월</th><th>급여·휴직 수령액</th></tr></thead><tbody>${Object.entries(incomes).map(([month,amount])=>`<tr><td>${month}</td><td class="amount">${won(amount)}원</td></tr>`).join('')}</tbody></table></div></details></section>`+buttons();
  }
  const schedule=()=>state.result?.loans?.repayment_details?.[loan]||[];
  function renderRepayment(){
    const rows=schedule(),years=[...new Set(rows.map(r=>r.date.slice(0,4)))];
    if(!years.includes(year))year='all';
    const shown=rows.filter(r=>year==='all'||r.date.startsWith(year));
    const sum=key=>shown.reduce((n,r)=>n+Number(r[key]||0),0);
    return staleNotice()+`<section class="card"><div class="section-bar"><div><h2>대출별 상환 일정</h2><p>정기 납부와 추가 상환을 함께 확인하세요.</p></div><a class="button small" href="#settings">추가 상환 설정 →</a></div><div class="fields">${select('repayment-loan','확인할 대출',Object.values(loanNames),loanNames[loan])}<div class="field"><label for="repayment-year">조회 연도</label><select id="repayment-year"><option value="all">전체 기간</option>${years.map(y=>`<option ${year===y?'selected':''}>${y}</option>`).join('')}</select></div></div><div class="cost-stats"><div class="stat-card"><span>조회 기간 상환 원금</span><strong>${shortMoney(sum('principal'))}</strong></div><div class="stat-card"><span>조회 기간 이자·수수료</span><strong>${shortMoney(sum('interest')+sum('fee'))}</strong></div><div class="stat-card"><span>조회 마지막 납부 후 원금</span><strong>${shortMoney(shown.at(-1)?.balance??0)}</strong></div></div><p class="hint">주담대는 상환 종료까지, 신용·청약담보는 엔진이 계산한 일정까지 표시합니다. 만기일시 대출의 마지막 잔액이 남아 있으면 이후 원금 상환도 필요합니다. 추가 상환 수수료는 원금과 구분합니다.</p><button class="button small" id="repayment-download" ${shown.length?'':'disabled'}>조회 상환표 CSV 내려받기</button><div class="table-wrap menu-scroll"><table id="repayment-table"><thead><tr>${['날짜','구분','원금','이자','수수료','납부 합계','남은 원금'].map(x=>`<th>${x}</th>`).join('')}</tr></thead><tbody>${shown.map(r=>`<tr><td>${esc(r.date)}</td><td>${esc(r.kind)}</td>${['principal','interest','fee','total','balance'].map(key=>`<td class="amount">${won(r[key])}원</td>`).join('')}</tr>`).join('')||'<tr><td colspan="7">계산에 포함된 상환 일정이 없습니다. 대출 사용 여부와 확정 자금 필터를 확인하세요.</td></tr>'}</tbody></table></div></section>`;
  }
  function renderBanks(){
    const selected=state.draft.settings.mortgage_quote_option||{};
    return staleNotice()+`<section class="card"><div class="section-bar"><div><h2>은행 상담 기록</h2><p>은행과 상담일별로 조건을 보관하고, 계산할 조건을 선택하세요.</p></div><button class="button primary" data-menu="bank-add">+ 상담 추가</button></div>${state.draft.bank_quotes.map((q,i)=>`<section class="bank-record"><div class="section-bar"><div><h3>${esc(q.bank)} · ${esc(q.date)}</h3><p>${esc(q.basis)}</p></div><div><button class="button small" data-menu="bank-edit" data-index="${i}">수정</button> <button class="button small danger" data-menu="bank-delete" data-index="${i}">삭제</button></div></div><div class="table-wrap"><table><thead><tr><th>상환 방식</th><th>금리 유형</th><th>연 금리</th><th>상담 한도</th><th>계산에 적용</th></tr></thead><tbody>${q.options.map((o,j)=>`<tr><td>${esc(o.method)}</td><td>${esc(o.rate_type)}</td><td>${(Number(o.rate)*100).toFixed(3).replace(/0+$/,'').replace(/\.$/,'')}%</td><td>${won(o.limit)}원</td><td><button class="button small ${selected[o.method]===o.id&&state.draft.settings.mortgage_method===o.method?'soft':''}" data-menu="bank-select" data-index="${i}" data-option="${j}">${selected[o.method]===o.id&&state.draft.settings.mortgage_method===o.method?'적용 중':'이 조건 적용'}</button></td></tr>`).join('')}</tbody></table></div></section>`).join('')||'<p class="hint">아직 상담 기록이 없습니다. 상담받은 금리와 한도를 등록하거나 대출·가계에서 직접 입력하세요.</p>'}<p class="hint">상담 조건 적용은 금리·상환 방식·은행 확인 한도에 반영합니다. 실제 승인 상태와 희망 대출금은 대출·가계에서 따로 확인하세요.</p><a href="#settings" class="button small">대출·가계 →</a></section>`+buttons();
  }
  function bankDialog(index=null){
    const original=index===null?null:state.draft.bank_quotes[index];
    const q=clone(original||{id:uuid('BANK'),date:new Date().toLocaleDateString('sv-SE'),bank:'',basis:'',options:[]});
    q.id ||=uuid('BANK');
    const optionFields=o=>`<div class="bank-option-fields" data-option-id="${esc(o.id||uuid('OPT'))}"><div class="fields">${select(`bank-method-${uuid('f')}`,'상환 방식',['원리금균등','원금균등'],o.method)}${select(`bank-type-${uuid('f')}`,'금리 유형',['고정금리','변동금리','혼합금리','확인 필요'],o.rate_type)}${formField(uuid('bank-rate'),'연 금리 · %',Number(o.rate||0)*100)}${formField(uuid('bank-limit'),'상담 한도',o.limit||0,'money')}</div><button class="button small danger" type="button" data-bank-remove>이 조건 삭제</button></div>`;
    openModal(original?'은행 상담 수정':'은행 상담 추가',`<form id="bank-form">${formField('bank-name','은행 이름',q.bank)}${formField('bank-date','상담일',q.date,'date')}${formField('bank-basis','상담 기준·메모',q.basis)}<div id="bank-options">${(q.options.length?q.options:[{method:'원리금균등',rate_type:'확인 필요',rate:0,limit:0}]).map(optionFields).join('')}</div><button class="button small" type="button" id="bank-add-option">+ 다른 상환 조건 추가</button><p id="bank-error" class="modal-error" role="alert"></p><div class="modal-actions"><button type="button" class="button" id="bank-cancel">취소</button><button class="button primary" type="submit">반영하고 계산</button></div></form>`);
    $('#bank-cancel').onclick=closeModal;
    $('#bank-add-option').onclick=()=>$('#bank-options').insertAdjacentHTML('beforeend',optionFields({method:'원금균등',rate_type:'확인 필요'}));
    $('#bank-options').onclick=e=>{if(e.target.closest('[data-bank-remove]'))e.target.closest('.bank-option-fields').remove();};
    $('#bank-form').onsubmit=async e=>{e.preventDefault();const submit=e.submitter;submit.disabled=true;try{
      const updated={...q,bank:$('#bank-name').value.trim(),date:$('#bank-date').value,basis:$('#bank-basis').value.trim(),options:$$('.bank-option-fields').map(el=>{const selects=$$('select',el),inputs=$$('input',el).filter(i=>!i.type||i.type!=='hidden');return {id:el.dataset.optionId,method:selects[0].value,rate_type:selects[1].value,rate:number(inputs[0].id),limit:money(inputs[1].id)};})};
      if(!updated.bank||!updated.date||!updated.options.length)throw new Error('은행·상담일·상환 조건을 입력하세요.');
      const h=clone(state.draft);if(index===null)h.bank_quotes.push(updated);else h.bank_quotes[index]=updated;
      for(const [method,id] of Object.entries(h.settings.mortgage_quote_option||{})){const option=updated.options.find(o=>o.id===id);if(original?.options.some(o=>o.id===id)&&(!option||option.method!==method)){const previous=original.options.find(o=>o.id===id);if(method===h.settings.mortgage_method)Object.assign(h.settings,{mortgage_rate:previous.rate,bank_confirmed_limit:previous.limit,mortgage_rate_type:previous.rate_type});delete h.settings.mortgage_quote_option[method];}if(option&&method===h.settings.mortgage_method){h.settings.mortgage_rate=option.rate;h.settings.bank_confirmed_limit=option.limit;h.settings.mortgage_rate_type=option.rate_type;}}
      await tools().applyCandidate(h);closeModal();toast('상담 기록을 반영했습니다. 변경사항을 저장해 주세요.');
    }catch(error){$('#bank-error').textContent=error.message;}finally{if(submit.isConnected)submit.disabled=false;}};
  }
  function renderImport(){
    importGeneration++;
    // A preview is tied to the exact workspace and draft from which it was made.
    if(importWorkspace!==state.workspace||importSnapshot!==JSON.stringify(state.draft))importPreview=null;
    return `<section class="card form-section"><h2>엑셀에서 계획 가져오기</h2><p class="hint">매수계획 v18 형식의 .xlsx 파일을 지원합니다. 임의 양식은 지원하지 않습니다. 엑셀에서 수식을 다시 계산하고 저장한 파일을 선택하세요. 가져온 뒤에는 앱의 저장 데이터를 사용합니다.</p><form id="excel-form"><div class="fields"><div class="field wide"><label for="excel-file">엑셀 파일 · 최대 10MB</label><input id="excel-file" type="file" accept=".xlsx" required></div><div class="field"><label for="excel-mode">가져오는 방식</label><select id="excel-mode"><option value="new">별도 새 계획으로 만들기</option><option value="merge">현재 계획에 추가 · 기존 입력 우선</option></select></div>${formField('excel-label','새 계획 이름','엑셀에서 가져온 계획')}</div><label class="checkbox-line"><input id="excel-refresh" type="checkbox" disabled>현재 계획의 엑셀 출처 항목도 갱신 · 앱에서 수정한 값은 유지</label><button class="button primary" type="submit">가져올 내용 미리보기</button><p id="excel-error" class="modal-error" role="alert"></p></form></section><div id="excel-preview"></div>`;
  }
  function invalidateImport(){importGeneration++;importPreview=null;$('#excel-preview').innerHTML='';}
  async function previewImport(e){
    e.preventDefault();const button=e.submitter;button.disabled=true;invalidateImport();
    try{
      if(!validInputs())return;
      const file=$('#excel-file').files[0];if(!file||file.size>10*1024*1024)throw new Error('10MB 이하 .xlsx 파일을 선택하세요.');
      const snapshot=JSON.stringify(state.draft),workspace=state.workspace,mode=$('#excel-mode').value,generation=importGeneration;
      const content=await new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(String(r.result).split(',')[1]);r.onerror=()=>reject(new Error('파일을 읽지 못했습니다.'));r.readAsDataURL(file);});
      const preview=await post('/api/import-excel/preview',{filename:file.name,content,household:mode==='merge'?clone(state.draft):null,refresh_imported:mode==='merge'&&$('#excel-refresh').checked});
      const result=await post('/api/evaluate',{household:preview.household});
      if(generation!==importGeneration||workspace!==state.workspace||snapshot!==JSON.stringify(state.draft)||!$('#excel-preview'))throw new Error('입력이 바뀌었습니다. 다시 미리보기 하세요.');
      importPreview=preview;importSnapshot=snapshot;importWorkspace=workspace;importMode=mode;
      $('#excel-preview').innerHTML=`<section class="card"><h2>가져오기 미리보기 · ${esc(preview.filename)}</h2><p>자금 ${preview.counts.fund_events}개 · 부모님 지원 ${preview.counts.parent_support}개 · 매물 ${preview.counts.listings}개</p><p>판정 ${esc(result.status)} · 최저 현금 ${shortMoney(result.kpis.min_balance_overall)}</p><ul>${preview.warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul><p class="hint">${mode==='new'?'확인하면 별도 계획을 만들어 저장합니다. 기존 계획은 보존됩니다.':'현재 초안에만 반영합니다. 계산 결과를 확인하고 변경사항을 저장하세요.'}</p><button class="button primary" id="excel-apply">${mode==='new'?'이 내용으로 새 계획 저장':'현재 초안에 반영'}</button></section>`;
      $('#excel-apply').onclick=applyImport;
    }catch(error){if($('#excel-error'))$('#excel-error').textContent=error.message;else toast(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
  }
  async function applyImport(e){
    const button=e.currentTarget;button.disabled=true;
    try{
      if(!importPreview||importWorkspace!==state.workspace||importSnapshot!==JSON.stringify(state.draft))throw new Error('입력이 바뀌었습니다. 다시 미리보기 하세요.');
      const candidate=clone(importPreview.household);
      if(importMode==='merge'){await tools().applyCandidate(candidate);toast('엑셀 내용을 초안에 반영했습니다. 확인 후 저장하세요.');}
      else{
        const label=$('#excel-label').value.trim();if(!label)throw new Error('새 계획 이름을 입력하세요.');
        if(!await confirmation('엑셀 내용으로 새 계획을 저장할까요?','<p>현재 계획은 유지됩니다. 저장하지 않은 현재 초안도 이 브라우저에 임시 보관합니다.</p>','새 계획 저장'))return;
        tools().flushDraft();
        const saved=await post('/api/workspaces',{label,household:candidate});
        state.workspaces=await api('/api/workspaces');state.workspace=saved.id;state.cashDate=null;state.confirmed=false;state.max=null;state.sequence++;
        try{localStorage.setItem(`homeplan-last-workspace:${location.origin}`,saved.id);}catch{}
        await tools().applySaved(saved);toast('별도 계획으로 저장했습니다.');
      }
      importPreview=null;state.route='plan';location.hash='plan';render();
    }catch(error){if($('#excel-error'))$('#excel-error').textContent=error.message;else toast(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
  }
  async function bankAction(button){
    const action=button.dataset.menu,index=Number(button.dataset.index),q=state.draft.bank_quotes[index];
    if(action==='bank-add'){bankDialog();return;}
    if(action==='bank-edit'){bankDialog(index);return;}
    const h=clone(state.draft);
    if(action==='bank-delete'){
      if(!await confirmation('은행 상담 기록을 삭제할까요?',`<p>${esc(q.bank)} · ${esc(q.date)} 상담을 삭제합니다. 적용 중인 조건이면 선택 연결을 해제하고 현재 금리·한도를 직접 입력값으로 유지합니다.</p>`,'삭제',{focusConfirm:true}))return;
      h.bank_quotes.splice(index,1);for(const [method,id] of Object.entries(h.settings.mortgage_quote_option||{}))if(q.options.some(o=>o.id===id)){const previous=q.options.find(o=>o.id===id);if(method===h.settings.mortgage_method)Object.assign(h.settings,{mortgage_rate:previous.rate,bank_confirmed_limit:previous.limit,mortgage_rate_type:previous.rate_type});delete h.settings.mortgage_quote_option[method];}
    }else{
      const option=q.options[Number(button.dataset.option)];if(!option.id)throw new Error('상담 기록을 수정해 저장한 뒤 적용하세요.');
      Object.assign(h.settings,{mortgage_method:option.method,mortgage_rate:option.rate,mortgage_rate_type:option.rate_type,bank_confirmed_limit:option.limit,mortgage_quote_option:{...h.settings.mortgage_quote_option,[option.method]:option.id}});
    }
    await tools().applyCandidate(h);toast('상담 조건을 반영했습니다. 변경사항을 저장해 주세요.');
  }
  function bind(){
    if(state.route==='repayment'){
      $('#repayment-loan').onchange=e=>{loan=Object.keys(loanNames).find(k=>loanNames[k]===e.target.value);year='all';render();};
      $('#repayment-year').onchange=e=>{year=e.target.value;render();};
      $('#repayment-download').onclick=()=>{const url=URL.createObjectURL(new Blob([repaymentCsv(schedule().filter(r=>year==='all'||r.date.startsWith(year)))],{type:'text/csv;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download=`homeplan-${loan}-${year}.csv`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);};
    }
    if(state.route==='import'){
      $('#excel-form').onsubmit=previewImport;
      $('#excel-mode').onchange=()=>{$('#excel-refresh').disabled=$('#excel-mode').value!=='merge';$('#excel-label').disabled=$('#excel-mode').value==='merge';invalidateImport();};
      $('#excel-file').onchange=invalidateImport;$('#excel-refresh').onchange=invalidateImport;
    }
  }
  document.addEventListener('click',async e=>{const button=e.target.closest('[data-menu]');if(!button)return;if(state.saving){toast('저장이 끝난 뒤 다시 시도해 주세요.');return;}try{if(button.dataset.menu==='calculate')await calculate();else await bankAction(button);}catch(error){toast(error.message,true);}});
  return {renderLeave,renderRepayment,renderBanks,renderImport,bind};
}
