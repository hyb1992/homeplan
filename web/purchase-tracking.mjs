import {moneyControl,dateControl,readMoneyInput} from './form-inputs.mjs';

const categories=['계약금','중도금','잔금','취득세','중개보수','법무·등기','수리','이사','기타'];
const statuses=['예정','진행 중','완료','해당 없음'];
const today=()=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Seoul'}).format(new Date());
const uuid=prefix=>prefix+'-'+crypto.randomUUID();

export function createPurchaseTracking(ctx){
  const {state,$,$$,esc,won,shortMoney,clone,openModal,closeModal,confirmation,toast}=ctx;
  let filter='전체';
  const tracking=()=>state.draft.purchase_tracking;
  const controls=(submit='기록 반영')=>`<p id="tracking-error" class="modal-error" role="alert"></p><div class="modal-actions"><button type="button" class="button" id="tracking-cancel">취소</button><button type="submit" class="button primary">${submit}</button></div>`;
  const field=(id,label,value='',kind='text')=>`<div class="field"><label for="${id}">${esc(label)}</label>${kind==='money'?moneyControl(id,label,value):kind==='date'?dateControl(id,label,value):`<input id="${id}" autocomplete="off" maxlength="120" value="${esc(value)}">`}</div>`;
  const select=(id,label,values,value)=>`<div class="field"><label for="${id}">${esc(label)}</label><select id="${id}">${values.map(v=>`<option ${v===value?'selected':''}>${esc(v)}</option>`).join('')}</select></div>`;
  const memo=value=>`<div class="field wide"><label for="tracking-memo">메모</label><textarea id="tracking-memo" maxlength="1000" rows="3">${esc(value||'')}</textarea></div>`;
  function dateValue(id,required=false,actual=false){
    const value=$('#'+id).value.trim();
    if(!value&&!required)return null;
    if(!/^\d{4}-\d{2}-\d{2}$/.test(value)||Number.isNaN(Date.parse(value))||new Date(value).toISOString().slice(0,10)!==value)throw new Error('날짜를 YYYY-MM-DD로 입력하거나 달력에서 선택하세요.');
    if(actual&&value>today())throw new Error('실제 지급일과 완료일은 오늘 이후로 기록할 수 없습니다. 예정일은 단계 일정에 입력하세요.');
    return value;
  }
  const amount=id=>{const value=readMoneyInput($('#'+id));if(value==null)throw new Error('금액을 입력하세요.');return value;};
  async function apply(candidate){await ctx.upgrades().applyCandidate(candidate);closeModal();toast('기록을 반영했습니다. 변경사항 저장을 눌러 보관하세요.');}
  function submit(handler){
    $('#tracking-cancel').onclick=closeModal;
    $('#tracking-form').onsubmit=async e=>{
      e.preventDefault();const button=e.submitter;button.disabled=true;
      try{await handler();}catch(error){if($('#tracking-error'))$('#tracking-error').textContent=error.message;else toast(error.message,true);}finally{if(button.isConnected)button.disabled=false;}
    };
  }
  async function agreementDialog(){
    const workspace=state.workspace;
    if(!state.result||state.calculatedSnapshot!==JSON.stringify(state.draft))await ctx.calculate();
    if(workspace!==state.workspace)throw new Error('계획이 바뀌었습니다. 계약 기록을 다시 열어 주세요.');
    if(!state.result||state.calculatedSnapshot!==JSON.stringify(state.draft))throw new Error('매수계획의 입력을 확인하고 다시 계산한 뒤 기록을 시작하세요.');
    if($('#modal').open)return;
    const previous=tracking(),listing=state.draft.listings.find(row=>row.id===state.draft.selected_listing)||state.draft.listings[0];
    const calculated=state.calculatedSnapshot===JSON.stringify(state.draft),payment=label=>calculated?Math.abs(state.result?.ledger.find(row=>row.source==='purchase'&&row.label===label)?.amount||0):0;
    const values=previous||{listing_id:listing.id,property_name:listing.name,price:listing.price,deposit_amount:payment('계약금'),interim_amount:state.draft.settings.interim_amount||0,contract_date:today(),milestones:[],payments:[]};
    openModal(previous?'계약 정보 수정':'계약 기록 시작',`<form id="tracking-form"><p class="hint">계약서에 적힌 실제 금액과 날짜를 확인하세요. 이 정보는 현재 매수계획과 별도로 보관합니다.</p><div class="fields">${field('tracking-property','계약한 집',values.property_name)}${field('tracking-contract-date','실제 계약일',values.contract_date,'date')}${field('tracking-price','계약 매매가',values.price,'money')}${field('tracking-deposit','약정 계약금',values.deposit_amount,'money')}${field('tracking-interim','약정 중도금 합계',values.interim_amount,'money')}</div><p class="hint">실제로 이체한 금액은 계약 정보를 반영한 뒤 지급 기록에 따로 추가하세요.</p>${controls(previous?'수정 반영':'계약 기록 시작')}</form>`);
    submit(async()=>{
      const contractDate=dateValue('tracking-contract-date',true,true),price=amount('tracking-price'),deposit=amount('tracking-deposit'),interim=amount('tracking-interim');
      if(!$('#tracking-property').value.trim()||price<=0)throw new Error('계약한 집의 이름과 0원보다 큰 매매가를 입력하세요.');
      if(deposit+interim>price)throw new Error('계약금과 중도금 합계가 매매가보다 큽니다.');
      const candidate=clone(state.draft),updated={...clone(values),property_name:$('#tracking-property').value.trim(),contract_date:contractDate,price,deposit_amount:deposit,interim_amount:interim};
      if(!previous){
        const schedule=state.result?.schedule||{},planned=key=>/^\d{4}-\d{2}-\d{2}$/.test(schedule[key]||'')?schedule[key]:null;
        updated.milestones=[{id:uuid('STEP'),name:'매매 계약',status:'완료',planned_date:contractDate,completed_date:contractDate,memo:''},...(interim?[{id:uuid('STEP'),name:'중도금 지급',status:'예정',planned_date:planned('interim_date'),completed_date:null,memo:''}]:[]),...['잔금 지급','소유권 이전·등기','입주'].map((name,index)=>({id:uuid('STEP'),name,status:'예정',planned_date:planned(index===2?'move_in_date':'closing_date'),completed_date:null,memo:''}))];
      }
      candidate.purchase_tracking=updated;await apply(candidate);
    });
  }
  function milestoneDialog(id=null){
    const row=tracking().milestones.find(item=>item.id===id)||{id:uuid('STEP'),name:'',status:'예정',planned_date:null,completed_date:null,memo:''};
    openModal(id?'진행 단계 수정':'진행 단계 추가',`<form id="tracking-form"><div class="fields">${field('tracking-step-name','단계 이름',row.name)}${select('tracking-status','진행 상태',statuses,row.status)}${field('tracking-planned','예정일 · 선택',row.planned_date||'','date')}${field('tracking-completed','실제 완료일',row.completed_date||'','date')}${memo(row.memo)}</div><p class="hint">단계를 완료해도 지급 기록은 자동으로 만들어지지 않습니다. 실제 이체 내역을 별도로 기록하세요.</p>${controls()}</form>`);
    const sync=()=>{const done=$('#tracking-status').value==='완료';$('#tracking-completed').closest('.field').hidden=!done;if(done&&!$('#tracking-completed').value)$('#tracking-completed').value=today();};
    $('#tracking-status').onchange=sync;sync();
    submit(async()=>{const candidate=clone(state.draft),updated={...row,name:$('#tracking-step-name').value.trim(),status:$('#tracking-status').value,planned_date:dateValue('tracking-planned'),completed_date:$('#tracking-status').value==='완료'?dateValue('tracking-completed',true,true):null,memo:$('#tracking-memo').value.trim()};if(!updated.name)throw new Error('단계 이름을 입력하세요.');const index=candidate.purchase_tracking.milestones.findIndex(item=>item.id===id);if(index<0)candidate.purchase_tracking.milestones.push(updated);else candidate.purchase_tracking.milestones[index]=updated;await apply(candidate);});
  }
  function paymentDialog(id=null,category='계약금'){
    const row=tracking().payments.find(item=>item.id===id)||{id:uuid('PAY'),category,amount:'',paid_date:today(),payer:'공동',recipient:'',memo:''};
    openModal(id?'지급 기록 수정':'실제 지급 기록',`<form id="tracking-form"><div class="fields">${select('tracking-category','지급 항목',categories,row.category)}${field('tracking-paid-date','실제 지급일',row.paid_date,'date')}${field('tracking-amount','실제로 지불한 금액',row.amount,'money')}${select('tracking-payer','지불한 사람',['공동','남편','아내'],row.payer)}${field('tracking-recipient','받는 곳 · 선택',row.recipient)}${memo(row.memo)}</div><p class="hint">이체한 건별로 기록하세요. 나눠 낸 계약금은 여러 번 추가할 수 있습니다. 기존 예상 현금 원장에서는 다시 차감하지 않습니다.</p>${controls()}</form>`);
    submit(async()=>{const candidate=clone(state.draft),updated={...row,category:$('#tracking-category').value,paid_date:dateValue('tracking-paid-date',true,true),amount:amount('tracking-amount'),payer:$('#tracking-payer').value,recipient:$('#tracking-recipient').value.trim(),memo:$('#tracking-memo').value.trim()};if(updated.amount<=0)throw new Error('실제 지급액은 0원보다 커야 합니다.');const index=candidate.purchase_tracking.payments.findIndex(item=>item.id===id);if(index<0)candidate.purchase_tracking.payments.push(updated);else candidate.purchase_tracking.payments[index]=updated;await apply(candidate);});
  }
  async function remove(kind,id){
    const rows=tracking()[kind],row=rows.find(item=>item.id===id);if(!row)return;
    const title=kind==='payments'?`${row.category} ${won(row.amount)}원`:row.name;
    if(!await confirmation('이 기록을 삭제할까요?',`<p>${esc(title)}</p><p>변경사항을 저장해야 삭제가 보관됩니다. 이전 저장본은 저장 기록에서 복원할 수 있습니다.</p>`,'삭제',{focusConfirm:true}))return;
    const candidate=clone(state.draft);candidate.purchase_tracking[kind]=candidate.purchase_tracking[kind].filter(item=>item.id!==id);await apply(candidate);
  }
  function render(){
    const record=tracking();
    if(!record)return `<section class="card purchase-empty"><p class="eyebrow">CONTRACT & PAYMENTS</p><h2>계약한 집의 진행 상황을 기록하세요</h2><p>계약부터 잔금·등기·입주까지, 진행 단계와 실제로 지불한 돈을 한곳에 보관합니다.</p><button class="button primary" data-purchase="agreement">계약 기록 시작</button><p class="hint">예상 계획이나 기존 자금을 바꾸지 않고 기록을 시작할 수 있어요.</p></section>`;
    const s=state.result?.purchase_progress;if(!s)return '<section class="card">계약 기록을 계산하고 있습니다. 상단에서 다시 계산해 주세요.</section>';
    const stat=(label,value,hint)=>`<section class="card"><p class="stat-label">${label}</p><strong class="purchase-stat">${value}</strong><p class="hint">${hint}</p></section>`;
    const matched=state.draft.listings.find(row=>row.id===record.listing_id),different=!matched||matched.price!==record.price||state.draft.selected_listing!==record.listing_id||state.result?.schedule?.contract_date!==record.contract_date||Number(state.draft.settings.interim_amount||0)!==record.interim_amount||Math.abs(state.result?.ledger.find(row=>row.source==='purchase'&&row.label==='계약금')?.amount||0)!==record.deposit_amount;
    const rows=[...record.payments].filter(row=>filter==='전체'||row.category===filter).sort((a,b)=>b.paid_date.localeCompare(a.paid_date));
    return `<section class="card purchase-agreement"><div class="section-bar"><div><p class="eyebrow">계약한 집</p><h2>${esc(record.property_name)}</h2><p>${esc(record.contract_date)} 계약 · 매매가 ${shortMoney(record.price)}</p></div><button class="button small" data-purchase="agreement">계약 정보 수정</button></div><p class="hint">계약 기록은 이 집에 고정됩니다. 매수계획에서 다른 매물을 골라도 기록은 유지됩니다.</p>${different?'<p class="recalculate-note">현재 매수계획의 매물·금액·계약일 중 계약 기록과 다른 조건이 있습니다. 실제 계약 조건을 예상 현금에도 반영하려면 <a href="#plan">매수계획</a>을 따로 수정하세요.</p>':''}</section><div class="purchase-stats">${stat('진행 단계',`${s.completed_steps} / ${s.total_steps}`,s.current_steps.length?`진행 중 · ${s.current_steps.map(esc).join(', ')}`:s.next_step?`다음 단계 · ${esc(s.next_step.name)}`:'모든 단계를 완료했어요')}${stat('실제 지불 합계',shortMoney(s.total_paid),`집값 ${shortMoney(s.price_paid)} + 부대비용 ${shortMoney(s.expenses_paid)}`)}${stat('남은 매매대금',shortMoney(s.remaining_price),'계약 매매가 − 집값 지급액 · 부대비용 별도')}</div><section class="card"><div class="section-bar"><div><h2>계약 이후 진행도</h2><p>예정일과 실제 완료일을 구분해 기록하세요.</p></div><button class="button small" data-purchase="step-add">+ 단계 추가</button></div><progress class="purchase-progress" max="100" value="${s.progress_percent}" aria-label="계약 진행도">${s.progress_percent}%</progress><ol class="purchase-milestones">${record.milestones.map(row=>`<li class="purchase-milestone ${row.status==='완료'?'done':''} ${row.status==='해당 없음'?'skipped':''}"><div><span class="status-pill">${esc(row.status)}</span><h3>${esc(row.name)}</h3><p>예정 ${esc(row.planned_date||'미정')} · 완료 ${esc(row.completed_date||'—')}${row.planned_date&&row.planned_date<s.as_of&&['예정','진행 중'].includes(row.status)?' <span class="negative-text">일정 확인 필요</span>':''}</p>${row.memo?`<p class="purchase-memo">${esc(row.memo)}</p>`:''}</div><div class="purchase-row-actions"><button class="row-action" data-purchase="step-edit" data-id="${esc(row.id)}">수정</button><button class="row-action danger" data-purchase="step-delete" data-id="${esc(row.id)}">삭제</button></div></li>`).join('')}</ol></section><section class="card"><h2>매매대금 지급 현황</h2><p class="hint">단계 완료 여부와 실제 지급 금액은 각각 기록합니다. ${s.paid_percent}% 지급</p><progress class="purchase-progress" max="100" value="${s.paid_percent}" aria-label="매매대금 지급률">${s.paid_percent}%</progress><div class="table-wrap"><table><thead><tr><th>항목</th><th>약정액</th><th>실제 지급</th><th>남은 금액</th><th></th></tr></thead><tbody>${['계약금','중도금','잔금'].map(category=>`<tr><td>${category}</td><td>${won(s.expected[category])}원</td><td>${won(s.categories[category])}원</td><td>${s.categories[category]>s.expected[category]?`<span class="negative-text">${won(s.categories[category]-s.expected[category])}원 초과</span>`:`${won(s.expected[category]-s.categories[category])}원`}</td><td><button class="row-action" data-purchase="payment-add" data-category="${category}">지급 기록</button></td></tr>`).join('')}</tbody></table></div>${s.overpaid_price?`<p class="negative-text">매매대금보다 ${shortMoney(s.overpaid_price)} 더 기록되어 있습니다. 지급 항목과 중복 기록을 확인하세요.</p>`:''}${s.future_payments?'<p class="negative-text">미래 날짜의 지급 기록은 오늘의 지급 합계에서 제외합니다.</p>':''}</section><section class="card"><div class="section-bar"><div><h2>실제로 지불한 돈</h2><p>분할 지급도 건별로 기록할 수 있습니다.</p></div><button class="button primary" data-purchase="payment-add">+ 지급 기록</button></div><label for="purchase-filter" class="sr-only">지급 항목 필터</label><select id="purchase-filter">${['전체',...categories].map(category=>`<option ${filter===category?'selected':''}>${category}</option>`).join('')}</select><div class="table-wrap"><table id="purchase-payments"><thead><tr><th>지급일</th><th>항목</th><th>금액</th><th>지불한 사람</th><th>받는 곳·메모</th><th></th></tr></thead><tbody>${rows.map(row=>`<tr><td>${esc(row.paid_date)}</td><td>${esc(row.category)}</td><td>${won(row.amount)}원</td><td>${esc(row.payer)}</td><td>${esc(row.recipient)}${row.memo?`<small class="purchase-memo">${esc(row.memo)}</small>`:''}</td><td class="purchase-row-actions"><button class="row-action" data-purchase="payment-edit" data-id="${esc(row.id)}">수정</button><button class="row-action danger" data-purchase="payment-delete" data-id="${esc(row.id)}">삭제</button></td></tr>`).join('')||'<tr><td colspan="6">기록된 지급 내역이 없습니다.</td></tr>'}</tbody></table></div></section><section class="card purchase-record-note"><strong>실제 지급 내역을 보관하는 화면입니다.</strong><p>기록은 기존 예상 현금 원장이나 대출 잔액에 추가로 차감하지 않습니다. 계약금·중도금·잔금의 계산 조건을 바꾸려면 <a href="#plan">매수계획</a>에서 조정하세요. 여기에 보이는 남은 매매대금은 대출을 포함한 실제 보유 현금과 다릅니다.</p><button class="button primary" data-action="save">변경사항 저장</button></section>`;
  }
  document.addEventListener('click',async event=>{
    const button=event.target.closest('[data-purchase]');if(!button)return;if(state.saving){toast('저장이 끝난 뒤 다시 시도해 주세요.');return;}
    try{const action=button.dataset.purchase;if(action==='agreement')await agreementDialog();else if(action==='step-add'||action==='step-edit')milestoneDialog(button.dataset.id);else if(action==='payment-add'||action==='payment-edit')paymentDialog(button.dataset.id,button.dataset.category);else await remove(action==='step-delete'?'milestones':'payments',button.dataset.id);}catch(error){toast(error.message,true);}
  });
  function bind(){if(state.route==='purchase')$('#purchase-filter')?.addEventListener('change',event=>{filter=event.target.value;ctx.render();});}
  return {render,bind};
}
