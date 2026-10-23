import {createPurchaseTracking} from './purchase-tracking.mjs';
import {moneyControl, dateControl, readMoneyInput, normalizeMoneyInput, installInputControls, closeCalendar, refreshCalendar, formatMoney, moneyWords} from './form-inputs.mjs';
import {seedExpenseItems} from './expense-plan.mjs';
import {createUpgradeTools} from './workspace-tools.mjs';
import {installUpdateNotice} from './update-notice.mjs';
import {renderPurchaseCosts} from './purchase-costs.mjs';
import {createPlanningMenus} from './planning-menus.mjs';
import {installFundBuilder,renderFundComposition,fundComposition,fundTypes} from './fund-builder.mjs';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const clone = value => structuredClone(value);
const esc = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const won = value => Number(value ?? 0).toLocaleString('ko-KR');
const shortMoney = value => {
  if (value == null) return '—';
  const sign = Number(value) < 0 ? '−' : '';
  const absolute = Math.abs(Number(value));
  if (absolute < 10000) return `${sign}${won(absolute)}원`;
  const eok = Math.floor(absolute / 1e8), man = Math.floor(absolute % 1e8 / 1e4);
  return sign + (eok ? `${eok}억` : '') + (man ? `${eok ? ' ' : ''}${won(man)}만` : '');
};
const icons = {
  purchase:'M9 3h6v3H9zM6 5H4v16h16V5h-2M8 11l2 2 5-5M8 17h8',
  plan:'M3 10 12 3l9 7M5 9v12h14V9M9 21v-8h6v8',
  costs:'M4 3h16v18H4zM8 8h8M8 12h8M8 16h5',
  funds:'M3 7h18v14H3zM3 7l3-4h12l3 4M15 13h6v4h-6z',
  support:'M12 21s-9-5-9-12a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 7-9 12-9 12z',
  settings:'M4 20V10M12 20V4M20 20v-7M1 10h6M9 4h6M17 13h6',
  leave:'M12 21s-9-5-9-12a5 5 0 0 1 9-3 5 5 0 0 1 9 3c0 7-9 12-9 12z',
  repayment:'M4 3h16v18H4zM8 8h8M8 12h8M8 16h5',
  banks:'M3 9l9-6 9 6M3 21h18M6 10v8M12 10v8M18 10v8',
  ledger:'M4 3h16v18H4zM8 8h8M8 12h8M8 16h5'
};
const pages = {
  plan:['매수계획','매수 계획을 한눈에','매물과 일정을 바꾸며 우리 가족의 자금을 확인하세요.'],
  purchase:['계약·지급','계약부터 입주까지 기록하기','계약한 집의 진행 상황과 실제로 지불한 돈을 기록하세요.'],
  costs:['매수 비용','집값 외에 드는 돈을 먼저','취득세부터 법무사·수리·이사 비용까지, 항목별로 정하세요.'],
  funds:['우리 자금','우리의 자금을 모아보기','예금부터 앞으로 들어올 돈까지, 항목을 자유롭게 추가하세요.'],
  support:['부모님 지원','도움을 받는 일정도 함께','증여와 차입을 구분하고, 실제 입금일을 기준으로 계획하세요.'],
  settings:['대출·가계','매달의 여유까지 살펴보기','대출 조건과 소득·지출을 바꿔 우리 가족에게 맞는 기준을 정하세요.'],
  leave:['출산·휴직','출산과 휴직도 계획에 함께','출산휴가·육아휴직·복직에 따른 급여와 입금 시점을 정하세요.'],
  repayment:['대출 상환표','매달 갚는 원금과 이자를 확인해요','대출별 정기 납부·추가 상환과 남은 원금을 함께 살펴보세요.'],
  banks:['은행 상담','상담받은 조건을 모아 비교해요','은행별 금리와 한도를 보관하고 계산에 적용할 조건을 선택하세요.'],
  ledger:['날짜별 현금','그날, 우리에게 남는 돈','날짜를 고르면 대출금을 포함한 현금과 남은 빚을 함께 보여드려요.']
};
const settingLabels = {
  contract_date:'계약일',interim_date:'중도금일',closing_date:'잔금일',move_in_date:'입주일',lease_refund_date:'퇴거일 · 보증금 반환일',lease_loan_repay_date:'전세대출 상환일',
  interim_amount:'중도금',deposit_ratio:'계약금 비율',min_emergency_cash:'최소 비상금',target_cash_after_purchase:'매수 후 목표 현금',
  husband_net_pay:'남편 월 실수령',wife_net_pay:'아내 월 실수령',husband_gross:'남편 연 총급여',wife_gross:'아내 연 총급여',living_cost:'월 생활비',fixed_cost:'월 고정비',
  mortgage_desired:'희망 주담대',mortgage_rate:'주담대 금리',mortgage_method:'상환 방식',mortgage_years:'상환기간',bank_confirmed_limit:'은행 확인 한도',
  monthly_repay_limit:'월 상환 한도',monthly_spend_limit:'월 가계지출 한도',credit_use:'신용대출 반영',credit_amount:'신용대출 금액',credit_rate:'신용대출 금리',
  sub_loan_use:'청약담보 반영',family_loan_rate:'가족 차입 금리',family_loan_monthly_principal:'가족 차입 월 원금',bank_income:'은행 인정 연소득'
};
settingLabels.variable_asset_mode='변동자산 계산 기준';
Object.assign(settingLabels,{card_pay_tax:'취득세 카드 납부',card_repay_on_credit_draw:'신용대출 실행일 카드 완납',card_months:'카드 할부 개월',card_first_offset:'카드 첫 납부월',card_fee_rate:'카드 할부 수수료율',card_paid_installments:'카드 유이자 회차'});
Object.assign(settingLabels,{expense_day:'가계 납부일',management_start_date:'새집 관리비 시작일',management_end_date:'새집 관리비 종료일',birth_date:'출산 예정일',birth_one_off:'출산 일회성 비용',annual_cost:'연 비용',annual_cost_month:'연 비용 납부월',fixed_in_living:'연 비용 포함 여부',property_tax_annual:'연간 보유세',monthly_saving:'적금·투자 납입',saving_end_date:'납입 종료일',saving_in_spend_limit:'저축의 월 지출 한도 포함 여부',lease_loan_rate:'전세대출 이율'});
const variablePresets={
  refund:{name:'연말정산 환급',type:'성과급·환급금',match:row=>row.name.includes('연말정산')},
  bonus:{name:'성과급',type:'성과급·환급금',match:row=>row.name.includes('성과급')},
  stock:{name:'주식',type:'투자자산',match:row=>row.type==='투자자산'||row.name.includes('주식')}
};
const variableMode=()=>state.draft.settings.variable_asset_mode||'보수적';
const fundAmount=(row,mode=variableMode())=>Number(row.is_variable?(mode==='보수적'?row.conservative_amount:row.aggressive_amount):(row.cash_out_amount??row.value??0))-Number(row.cost||0);
function variableModeControl(){return `<div class="field variable-mode"><label for="variable-asset-mode">변동자산 계산 기준</label><select id="variable-asset-mode"><option ${variableMode()==='보수적'?'selected':''}>보수적</option><option ${variableMode()==='공격적'?'selected':''}>공격적</option></select></div>`;}
function variablePreset(key){
  const preset=variablePresets[key];
  const existing=state.draft.fund_events.find(row=>row.data_kind!=='예시'&&preset.match(row));
  editRecord('fund',existing?.id||null,preset);
}
function renderVariableAssets(){
  const rows=state.draft.fund_events.filter(row=>row.is_variable&&row.data_kind!=='예시'&&row.status!=='제외'&&row.use_for_purchase!==false);
  return `<section class="card variable-assets"><div class="section-bar"><div><h2>변동자산</h2><p>연말정산 환급·성과급·주식에 두 가지 예상 금액을 기록하세요.</p></div>${variableModeControl()}</div><div class="variable-totals">${['보수적','공격적'].map(mode=>`<div class="variable-total ${variableMode()===mode?'selected':''}"><span>${mode} 예상 금액</span><strong>${shortMoney(rows.reduce((total,row)=>total+fundAmount(row,mode),0))}</strong><small>${variableMode()===mode?'현재 계산에 적용':'비교용 예상 금액'}</small></div>`).join('')}</div><p class="cash-note">매수에 쓰는 변동자산 ${rows.length}개 · 등록 비용을 뺀 합계입니다. 입금·현금화 날짜에 맞춰 반영됩니다.</p><div class="variable-presets">${Object.entries(variablePresets).map(([key,preset])=>`<button class="button small soft" data-action="variable-preset" data-preset="${key}">${esc(preset.name)} 설정</button>`).join('')}</div><p class="cash-note">기존 항목은 ‘수정’에서 변동자산으로 바꿀 수 있습니다. 두 예상액은 직접 입력해 주세요.</p></section>`;
}
const state = {workspace:null,workspaces:[],base:null,draft:null,revision:0,result:null,route:'plan',confirmed:false,chartRange:'purchase',max:null,showAll:false,evaluating:false,saving:false,sequence:0,calculatedSnapshot:null,cashDate:null,expenseMonth:null};
const inputProblems=new Map();
let upgrades;
let menus;
let purchase;
let toastTimer;
function toast(message, error = false) {
  const element = $('#toast'); element.textContent = message; element.className = `visible${error ? ' error' : ''}`;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => element.className = '', 4200);
}
async function api(url, options = {}) {
  const response = await fetch(url,{...options,headers:{'Content-Type':'application/json',...options.headers}});
  if (!response.ok) {
    let detail = '연결을 확인한 뒤 다시 시도해 주세요.';
    try { const body = await response.json(); detail = typeof body.detail === 'string' ? body.detail : body.detail?.map(row => row.msg).join('\n') || detail; } catch {}
    throw new Error(detail);
  }
  return response.json();
}
const post = (url, payload, method = 'POST') => api(url,{method,body:JSON.stringify(payload)});
const dirty = () => JSON.stringify(state.base) !== JSON.stringify(state.draft)||inputProblems.size>0;
const selected = () => state.draft.listings.find(item => item.id === state.draft.selected_listing) || state.draft.listings[0];
function updateSavedState() {
  $('#save-button').disabled = !dirty() || state.saving;
  $('#save-button').textContent = state.saving ? '저장 중…' : '변경사항 저장';
  $('#save-state').textContent = dirty() ? '저장하지 않은 변경사항' : '저장된 계획';
  $('#save-state').classList.toggle('dirty',dirty());
}
function field(key,label,kind='money',scope='settings',wide=false,help='') {
  const source = scope === 'listing' ? selected() : state.draft.settings;
  let value = source[key] ?? '';
  if(key==='management_start_date'&&!value)value='입주일';
  if(scope==='listing'&&key==='mgmt_fee'&&source[key]==null)value=state.draft.settings.mgmt_fee_default??'';
  if(scope==='listing'&&key==='repair'&&source[key]==null)value=state.draft.settings.repair_default??0;
  if (kind === 'percent') value = value === '' ? '' : Number((Number(value)*100).toFixed(6));
  const attributes=`data-key="${key}" data-kind="${kind}" data-scope="${scope}"`,id=`field-${key}`;
  const date=kind==='date'||key.endsWith('_date');
  if(kind==='money')label=label.replace(' · 원','');
  const control=kind==='money'?moneyControl(id,label,value,attributes,{defaultUnit:['price','appraisal'].includes(key)?1e8:undefined}):date?dateControl(id,label,value,attributes):`<input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="${id}" ${attributes} type="text" value="${esc(value)}">`;
  return `<div class="field${wide?' wide':''}"><label for="${id}">${esc(label)}</label>${control}${help?`<small>${esc(help)}</small>`:''}</div>`;
}
function selectField(key,label,options,scope='settings',wide=false) {
  const value = scope === 'listing' ? selected()[key] : state.draft.settings[key];
  return `<div class="field${wide?' wide':''}"><label for="field-${key}">${esc(label)}</label><select id="field-${key}" data-key="${key}" data-kind="select" data-scope="${scope}">${options.map(option=>`<option value="${esc(option)}" ${String(value)===String(option)?'selected':''}>${esc(option)}</option>`).join('')}</select></div>`;
}
const checkField = (key,label) => `<label class="checkbox-line"><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" type="checkbox" data-key="${key}" data-kind="bool" data-scope="settings" ${state.draft.settings[key]?'checked':''}>${esc(label)}</label>`;
const refundLinked=()=>['중도금일','중도금지급일','interim_date'].includes(String(state.draft.settings.lease_refund_date||'').replace(/\s/g,'').replace(/^=/,''));
function refundLinkControl() {
  const linked=refundLinked();
  return `<div class="refund-link wide"><button type="button" id="refund-interim-link" class="button small ${linked?'selected':''}" aria-pressed="${linked}" aria-describedby="refund-link-help">퇴거일을 중도금일에 맞추기 <span>${linked?'켜짐':'꺼짐'}</span></button><small id="refund-link-help">${linked?'중도금일을 바꾸면 퇴거일·보증금 반환일도 함께 바뀝니다.':'켜두면 두 날짜가 계속 함께 바뀝니다.'}</small></div>`;
}
function syncRefundLink() {
  const input=$('#field-lease_refund_date');if(!input)return;
  const linked=refundLinked();input.readOnly=linked;input.setAttribute('aria-readonly',String(linked));
  const calendar=$('[data-calendar-for="field-lease_refund_date"]');if(calendar)calendar.disabled=linked;
  if(linked)input.value=state.calculatedSnapshot===JSON.stringify(state.draft)?state.result.schedule.lease_refund_date:String(state.draft.settings.interim_date||'');
}
async function toggleRefundLink() {
  if(state.saving){toast('저장이 끝난 뒤 다시 시도해 주세요.');return;}
  const linked=refundLinked(),candidate=clone(state.draft),snapshot=JSON.stringify(state.draft),workspace=state.workspace;
  if(!linked&&!String(candidate.settings.interim_date||'').trim()){toast('중도금일을 먼저 입력해 주세요.',true);return;}
  if(!linked)candidate.settings.lease_refund_date='중도금일';
  closeCalendar();const sequence=++state.sequence;state.evaluating=true;$('#refund-interim-link').disabled=true;
  try{
    const result=await post('/api/evaluate',{household:candidate,listing_id:selected().id,confirmed_only:state.confirmed});
    if(sequence!==state.sequence||workspace!==state.workspace)return;
    if(snapshot!==JSON.stringify(state.draft)){toast('입력이 바뀌었습니다. 옵션을 다시 선택해 주세요.');return;}
    if(linked)candidate.settings.lease_refund_date=result.schedule.lease_refund_date;
    state.draft=candidate;state.result=result;state.max=null;state.calculatedSnapshot=JSON.stringify(candidate);state.evaluating=false;render();
    toast(linked?'연결을 해제했습니다. 퇴거일을 따로 설정할 수 있어요.':'퇴거일을 중도금일에 연결했습니다. 변경사항을 저장해 주세요.');
  }catch(error){if(sequence===state.sequence)toast(error.message,true);}
  finally{if(sequence===state.sequence){state.evaluating=false;const button=$('#refund-interim-link');if(button)button.disabled=false;const calculateButton=$('#calculate-button');if(calculateButton){calculateButton.disabled=false;calculateButton.textContent='현재 조건으로 계산';}}}
}
function onFieldChange(event) {
  const element = event.target.closest('[data-key]'); if (!element) return;
  const {key,kind,scope} = element.dataset;
  const target = scope === 'listing' ? selected() : state.draft.settings;
  try {
    let value = element.value;
    if (kind === 'money') {value = readMoneyInput(element);if(value==null)throw new Error('금액을 입력해 주세요.');}
    if (kind === 'percent') { value = Number(value)/100; if (!Number.isFinite(value) || value<0 || value>1) throw new Error('비율을 0~100%로 입력해 주세요.'); }
    if (kind === 'int') { if(value.trim()==='')throw new Error('숫자를 입력해 주세요.');value = Number(value); if (!Number.isInteger(value) || value<0) throw new Error('0 이상의 정수로 입력해 주세요.'); const ranges={payday:[1,31],expense_day:[1,31],annual_cost_month:[0,12],mortgage_years:[1,50],card_months:[1,60]};if(ranges[key]&&(value<ranges[key][0]||value>ranges[key][1]))throw new Error(`${ranges[key][0]}~${ranges[key][1]} 범위로 입력해 주세요.`); }
    if (kind === 'optional-int') { value=value.trim()===''?null:Number(value);if(value!==null&&(!Number.isInteger(value)||value<1||value>31))throw new Error('납부일은 1~31일 또는 빈칸으로 입력해 주세요.'); }
    if (kind === 'bool') value = element.checked;
    if (kind === 'date' && !value) value = null;
    const oldIncomeSum=Number(state.draft.settings.husband_gross||0)+Number(state.draft.settings.wife_gross||0);
    const oldBankIncome=Number(state.draft.settings.bank_income||0);
    target[key] = value;
    inputProblems.delete(`${scope}:${scope==='listing'?selected().id+':':''}${key}`);
    if(['husband_gross','wife_gross'].includes(key)&&(!oldBankIncome||oldBankIncome===oldIncomeSum))state.draft.settings.bank_income=Number(state.draft.settings.husband_gross||0)+Number(state.draft.settings.wife_gross||0);
    element.classList.remove('invalid'); element.setCustomValidity('');
    if (kind === 'money') normalizeMoneyInput(element,value);
    if (scope === 'listing') target.origin = 'app';
    if (['mortgage_rate','bank_confirmed_limit'].includes(key)) {
      const mapping = state.draft.settings.mortgage_quote_option || {};
      delete mapping[state.draft.settings.mortgage_method]; state.draft.settings.mortgage_quote_option = mapping;
      const selector = $('#bank-option'); if (selector) selector.value = '';
    }
    state.max = null; updateSavedState(); const note=$('#calculation-state'); if(note)note.hidden=state.calculatedSnapshot===JSON.stringify(state.draft);
    upgrades?.scheduleDraft();
    if(key==='interim_date')syncRefundLink();
    if(['card_pay_tax','card_repay_on_credit_draw'].includes(key)&&$('#tax-card-plan'))$('#tax-card-plan').outerHTML=renderTaxCardPlan();
    if((key==='birth_date'&&state.route==='settings'&&state.draft.expense_items==null)||['credit_use','sub_loan_use'].includes(key))render();
  } catch(error) { inputProblems.set(`${scope}:${scope==='listing'?selected().id+':':''}${key}`,{key,scope,listingId:scope==='listing'?selected().id:null,raw:element.value,error:error.message,route:state.route});element.classList.add('invalid'); element.setCustomValidity(error.message); element.reportValidity();upgrades?.scheduleDraft(); }
}
function validInputs(){
  for(const input of $$('[data-key] input, input[data-key]')){if(input===document.activeElement)onFieldChange({target:input});}
  const invalid=$('#content :invalid');
  if(invalid){invalid.scrollIntoView({block:'center'});invalid.focus();invalid.reportValidity();toast('오류가 있는 입력을 먼저 수정해 주세요.',true);return false;}
  if(inputProblems.size){const problem=[...inputProblems.values()][0];if(problem.listingId)state.draft.selected_listing=problem.listingId;state.route=problem.route;location.hash=problem.route;render();toast(problem.error,true);return false;}
  const s=state.draft.settings;
  if(s.annual_cost>0&&!s.fixed_in_living&&!s.annual_cost_month){state.route='settings';location.hash='settings';render();$('#field-annual_cost_month')?.focus();toast('연 비용 납부월을 1~12월로 설정해 주세요.',true);return false;}
  return true;
}
function stat(label,value,foot='',className='') {
  const action=label==='일별 최저 잔고'?'inspect-minimum':label==='남은 빚 원금'?'inspect-debt':label==='보유 현금 · 대출금 포함'?'inspect-cash':'';
  return `<div class="stat-card ${className} ${action?'inspectable':''}" ${action?`role="button" tabindex="0" data-action="${action}"`:''}><div class="stat-label">${label}</div><div class="stat-value">${value}</div><div class="stat-foot">${esc(foot)}</div></div>`;
}
function stats() {
  const r=state.result, k=r?.kpis;
  if (!r) return `<div class="stats">${stat('매수 가능 여부','계산 중…','','highlight')}${stat('일별 최저 잔고','—')}${stat('주담대 월 납입','—')}${stat('잔금일 가용자금','—')}</div>`;
  return `<div class="stats">${stat('매수 가능 여부',esc(r.status),`${r.checks.filter(c=>!c.ok).length}개 조건을 살펴보세요`,'highlight')}${stat('일별 최저 잔고',esc(shortMoney(k.min_balance_overall)),`${k.min_balance_date} · 장중 최저 포함`,k.min_balance_overall<0?'negative':'')}${stat('주담대 첫 월 납입',`${esc(shortMoney(k.mortgage_first_payment))}<small>/ 월</small>`,`대출금 ${shortMoney(k.mortgage_amount)} · 월 한도 ${shortMoney(state.draft.settings.monthly_repay_limit)}`)}${stat('잔금일 가용자금',esc(shortMoney(k.closing_cash_available)),`${state.result.schedule.closing_date} 기준`)}</div>`;
}
function priceNotice() {
  const price=Number(selected().price);
  if(!(price>=0&&price<1000000))return '';
  const proposed=price*10000,canCorrect=proposed>=1e8&&proposed<=1e10;
  return `<div class="price-notice" role="status"><strong>매수가 단위를 확인해 주세요.</strong><p>현재 매수가는 ${esc(moneyWords(price))}(${won(price)}원)입니다. 주담대도 이 금액을 기준으로 계산됩니다.</p>${canCorrect?`<button type="button" class="button small" data-action="price-correct" data-price="${proposed}" data-listing="${esc(selected().id)}">${esc(formatMoney(proposed,1e8))}억원으로 수정</button>`:''}</div>`;
}
function listingActions() {
  const last=state.draft.listings.length<=1;
  return `<span class="listing-actions"><button class="row-action" data-action="listing-edit">매물 수정</button><button class="row-action danger" data-action="listing-delete" ${last?'disabled aria-describedby="listing-delete-note"':''}>매물 삭제</button></span>${last?'<small id="listing-delete-note" class="listing-delete-note">마지막 매물입니다. 새 매물을 추가한 뒤 삭제할 수 있어요.</small>':''}`;
}
function renderPlan() {
  const item=selected(), s=state.draft.settings;
  return `<div id="calculation-state" class="recalculate-note" ${state.calculatedSnapshot===JSON.stringify(state.draft)?'hidden':''}>입력이 바뀌었습니다. 다시 계산하면 새 조건의 결과를 보여드려요.</div>${stats()}<div class="plan-layout"><section class="card plan-editor"><div class="card-title"><h2>매물과 일정</h2><button class="text-action" data-action="listing-add">+ 매물 추가</button></div><div class="fields"><div class="field wide"><label for="listing-select">검토 중인 매물</label><select id="listing-select">${state.draft.listings.map(row=>`<option value="${esc(row.id)}" ${row.id===item.id?'selected':''}>${esc(row.name)} · ${Number(row.area_m2)}㎡</option>`).join('')}</select></div><div class="field wide"><div class="listing-detail">${esc(item.tenant)} · 전용 ${Number(item.area_m2)}㎡ ${listingActions()}</div></div><div class="price-field field wide">${field('price','검토 매수가 · 원','money','listing',true).replace('class="field wide"','class="field"')}</div>${priceNotice()}<div class="field-heading">매수 일정 <span class="field-help">날짜별로 자금을 확인해요</span></div>${field('contract_date','계약일','date')}${field('interim_date','중도금일','date')}${field('interim_amount','중도금 · 원','money','settings',true)}${field('closing_date','잔금일','date')}${field('move_in_date','입주일 · 수리 후','date','settings',false,'수리·이사 일정에 반영해요. 토허 잔금 일정은 잔금일로 점검합니다.')}${field('lease_refund_date','퇴거일 · 보증금 반환일','date','settings',true)}${refundLinkControl()}${field('min_emergency_cash','최소 비상금 · 원','money','settings',true)}</div>${variableModeControl()}<label class="checkbox-line"><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="confirmed-only" type="checkbox" ${state.confirmed?'checked':''}> 확정된 미래 자금만 계산</label><div class="form-bottom"><button class="button primary full" id="calculate-button">${state.evaluating?'<span class="spinner"></span> 계산 중…':'현재 조건으로 계산'}</button><p>입력 변경 후 계산 결과를 확인하고<br>상단의 저장 버튼으로 보관하세요.</p></div><button class="button soft full" id="maximum-button" style="margin-top:10px">이 조건의 최대 매수가 찾기</button><div id="maximum-result">${renderMaximum()}</div></section><div class="right-column"><section class="card chart-card"><div class="card-title"><div><h2>시간에 따른 우리집 현금</h2><p>매일의 최저 잔고와 비상금 기준</p></div><div class="chart-tools"><select id="chart-range" aria-label="그래프 기간"><option value="purchase" ${state.chartRange==='purchase'?'selected':''}>매수 전후 12개월</option><option value="all" ${state.chartRange==='all'?'selected':''}>전체 기간</option><option value="leave" ${state.chartRange==='leave'?'selected':''}>휴직 기간</option></select></div></div><div id="chart" class="chart-wrap"></div><div class="chart-legend"><span><i class="legend-line"></i>일별 최저 잔고</span><span><i class="legend-line dashed"></i>최소 비상금</span></div></section>${renderDateCash()}${renderChecks()}${renderDsr()}${renderAssumptions()}</div></div>`;
}
function renderMaximum() {
  const result=state.max; if (!result) return '';
  return `<div class="max-result"><span>입력 조건 기준 예상 최대가</span><strong class="large">${result.price==null?'일정·조건 확인 필요':esc(shortMoney(result.price))}</strong><span>제한 조건 · ${esc(result.binding_check)}</span>${result.gate_failures.length?`<p>일정 조건 제외 참고 한도<br><b>${esc(shortMoney(result.conditional_price))}</b></p>`:''}<p class="field-help">선택 매물의 수리비·관리비 기준입니다.<br>은행 한도와 예정 자금 확인이 필요합니다.</p></div>`;
}
function renderChecks() {
  if (!state.result) return '<section class="card loading-card">계산 후 조건별 결과를 보여드려요.</section>';
  const checks=[...state.result.checks].sort((a,b)=>Number(a.ok)-Number(b.ok));
  const shown=state.showAll?checks:checks.slice(0,7);
  return `<section class="card checks-card"><div class="card-title"><h2>매수 전 확인할 조건</h2><span class="check-count">${checks.filter(c=>c.ok).length} / ${checks.length} 충족</span></div><div class="table-wrap"><table class="checks-table"><thead><tr><th>확인 항목</th><th>결과</th><th>판정 근거</th></tr></thead><tbody>${shown.map(c=>`<tr><td>${esc(c.name)}</td><td><span class="status-pill ${c.ok?'':'bad'}">${c.ok?'충족':'확인 필요'}</span></td><td>${esc(c.reason)}${c.name==='월 가계지출 한도'?'<button class="row-action" data-action="inspect-spend">지출 내역 →</button>':''}</td></tr>`).join('')}</tbody></table></div><div class="check-foot"><span>금액과 실제 입금일을 함께 확인하세요.</span><button id="show-checks">${state.showAll?'주요 조건만 보기':'모든 조건 보기'} ${state.showAll?'−':'+'}</button></div></section>`;
}
function renderDsr() {
  if(!state.result)return '';
  const k=state.result.kpis;
  return `<section class="card"><div class="card-title"><h2>대출 상환 부담 · DSR</h2><span class="check-count">은행 심사 참고</span></div><div class="dsr-grid">${[['주담대 심사',k.dsr_mortgage_review],['신용대출 차주',k.dsr_credit_borrower],['가계 합산',k.dsr_household_actual],['갈아타기 점검',k.dsr_refinance_check]].map(([label,value])=>`<div class="dsr-item">${label}<strong class="${Number(value)>.4?'over':''}">${value==null?'—':(Number(value)*100).toFixed(1)+'%'}</strong></div>`).join('')}</div></section>`;
}
function renderAssumptions() {
  if (!state.result) return '';
  const items=state.result.assumptions.filter(row=>row.label);
  const warnings=state.result.warnings;
  return `<section class="notice"><strong>${state.confirmed?'확정된 미래 자금만 계산했어요.':'예정된 자금도 계산에 포함되어 있어요.'}</strong><p>입금일이나 대출 한도가 바뀌면 결과도 달라질 수 있어요.</p><details class="warning-detail"><summary>자금 전제 ${items.length}개와 확인할 내용 보기</summary><div class="assumption-list">${items.map(row=>`<div class="assumption"><strong>${esc(row.label)} · ${shortMoney(row.amount)}</strong><p>${esc(row.status)} · ${esc(row.date || '')}${row.without?`<br>제외 시 중도금 부족 ${shortMoney(row.without.interim_shortfall)}, 잔금 부족 ${shortMoney(row.without.closing_shortfall)}`:''}</p></div>`).join('')}</div><ul>${warnings.map(w=>`<li>${esc(w)}</li>`).join('')}</ul></details></section>`;
}
function renderFunds() {
  const allRows=state.draft.fund_events.filter(row=>row.data_kind!=='예시'),types=[...new Set(allRows.map(row=>row.type))];
  if(!types.includes(state.fundTypeFilter))state.fundTypeFilter=null;
  const rows=state.fundTypeFilter?allRows.filter(row=>row.type===state.fundTypeFilter):allRows;
  const positive=fundComposition(allRows,variableMode()).total;
  return `<div class="stats three">${stat('등록한 자금',`${allRows.length}<small>개 항목</small>`,'추가할 수 있는 항목 수에 제한이 없어요','highlight')}${stat('등록 자금 합계',shortMoney(positive),`변동자산 ${variableMode()} 기준 · 부채·출금·제외 별도`)}${stat('미확정 항목',`${allRows.filter(row=>!['확정','확인 완료','제외'].includes(row.status)).length}<small>개</small>`,'예정 입금일을 다시 확인하세요')}${stat('데이터',state.workspace==='demo'?'가상 테스트':'실제 가구','이 화면에서 추가·수정할 수 있어요')}</div>${renderFundComposition(allRows,{mode:variableMode(),scope:state.fundScope||'all',purchaseOnly:!!state.fundPurchaseOnly,selectedType:state.fundTypeFilter,shortMoney,won})}${renderVariableAssets()}<section class="card" id="fund-list"><div class="section-bar"><div><h2>우리 자금 목록</h2><p>현금, 적금, 투자자산, 들어올 돈을 한곳에</p></div><button class="button primary" data-action="fund-add">+ 새 자금 추가</button></div><div class="fund-list-filters"><label for="fund-type-filter">유형별 보기</label><select id="fund-type-filter"><option value="">전체 유형 · ${allRows.length}개</option>${types.map(type=>`<option value="${esc(type)}" ${state.fundTypeFilter===type?'selected':''}>${esc(type)} · ${allRows.filter(row=>row.type===type).length}개</option>`).join('')}</select>${state.fundTypeFilter?'<button class="button small" id="fund-filter-clear">전체 목록 보기</button>':''}</div><div class="table-wrap"><table><thead><tr><th>자금 이름</th><th>누구의 돈</th><th>매수 투입액</th><th>사용 가능일</th><th>확정 여부</th><th></th></tr></thead><tbody>${rows.map(row=>{const amount=fundAmount(row),negative=row.type.includes('부채')||row.type==='기타 나갈 돈',shown=negative?-Number(row.cash_out_amount??row.value??0)-Number(row.cost||0):amount;return `<tr class="${row.status==='제외'?'muted-row':''}"><td><span class="record-name">${esc(row.name)}</span><small class="record-subtitle">${esc(row.type)}${row.is_variable?' · 변동자산':''}${row.use_for_purchase===false?' · 매수 투입 안 함':''}</small></td><td>${esc(row.owner)}</td><td class="amount ${shown<0?'negative-text':''}">${won(shown)}원${row.is_variable?`<small class="variable-range">보수적 ${shortMoney(fundAmount(row,'보수적'))}<br>공격적 ${shortMoney(fundAmount(row,'공격적'))}</small>`:''}</td><td>${esc(row.available_date||'현재 보유')}</td><td><span class="status-pill ${['확정','확인 완료'].includes(row.status)?'':'pending'}">${esc(row.status)}</span></td><td><div class="row-actions"><button class="row-action" data-action="fund-edit" data-id="${esc(row.id)}" aria-label="${esc(row.name)} 수정">수정</button><button class="row-action" data-action="fund-toggle" data-id="${esc(row.id)}">${row.status==='제외'?'복원':'제외'}</button><button class="row-action danger" data-action="fund-delete" data-id="${esc(row.id)}" aria-label="${esc(row.name)} 삭제">삭제</button></div></td></tr>`;}).join('')}</tbody></table></div>${rows.length?'':'<div class="empty">새 자금 추가 버튼으로 첫 항목을 등록하세요.</div>'}</section>`;
}
function renderSupport() {
  const rows=state.draft.parent_support;
  return `<section class="card"><div class="section-bar"><div><h2>부모님 지원 일정</h2><p>아직 받지 않은 지원은 미확정으로 남겨두세요.</p></div><button class="button primary" data-action="support-add">+ 지원 추가</button></div><div class="table-wrap"><table><thead><tr><th>지원 유형</th><th>받는 사람</th><th>금액</th><th>입금일</th><th>상태</th><th></th></tr></thead><tbody>${rows.map((row,index)=>`<tr class="${row.status==='제외'?'muted-row':''}"><td><span class="record-name">부모님 ${esc(row.kind)}</span></td><td>${esc(row.to)}</td><td class="amount">${won(row.amount)}원</td><td>${esc(row.date||'날짜 미입력')}</td><td><span class="status-pill ${['확정','확인 완료'].includes(row.status)?'':'pending'}">${esc(row.status)}</span></td><td><div class="row-actions"><button class="row-action" data-action="support-edit" data-id="${index}">수정</button><button class="row-action" data-action="support-toggle" data-id="${index}">${row.status==='제외'?'복원':'제외'}</button><button class="row-action danger" data-action="support-delete" data-id="${index}" aria-label="부모님 ${esc(row.kind)} 지원 삭제">삭제</button></div></td></tr>`).join('')}</tbody></table></div>${rows.length?'':'<div class="empty">지원 일정을 추가하면 해당 날짜의 자금에 반영됩니다.</div>'}</section><section class="card form-section" style="margin-top:20px"><h2>가족 차입 상환 계획</h2><div class="fields">${field('family_loan_rate','가족 차입 연 이율 · %','percent')}${field('family_loan_monthly_principal','월 상환 원금 · 원')}${field('family_loan_repay_start','상환 시작일','date')}</div><p class="hint">차입으로 등록한 금액에 적용됩니다. 이자·상환 약정은 가족과 별도로 확인하세요.</p></section>`;
}
const expenseRows=()=>state.draft.expense_items??seedExpenseItems(state.draft);
function expensePeriod(row){
  const resolved=state.calculatedSnapshot===JSON.stringify(state.draft)?state.result?.expense_schedule?.find(item=>item.id===row.id):null;
  const actual=resolved?.enabled?`${resolved.start_date||state.result.daily_balances[0].date} → ${resolved.end_date||'종료 없음'}`:'';
  return `${esc(row.start_date||'기준일')} → ${esc(row.end_date||'종료 없음')}${actual?`<small class="record-subtitle">${esc(actual)}</small>`:''}`;
}
function expenseSummaryBody(){
  const k=state.result?.kpis,months=Object.keys(k?.monthly_spend||{}).sort();
  const month=months.includes(state.expenseMonth)?state.expenseMonth:state.result?.schedule.closing_date.slice(0,7);
  const rows=k?.monthly_expense_breakdown?.[month]||{};
  return `<div class="expense-month-total"><span>${esc(month||'')} 월 지출 합계</span><strong>${shortMoney(k?.monthly_spend?.[month]||0)}</strong><small>${esc(k?.expense_mode||'계산 전')} 기준 · 월 한도 ${shortMoney(state.draft.settings.monthly_spend_limit)}</small></div><div class="expense-breakdown">${Object.entries(rows).map(([name,amount])=>`<div><span>${esc(name)}</span><strong>${won(amount)}원</strong></div>`).join('')||'<p class="cash-note">이 달에 등록된 지출이 없습니다.</p>'}</div>`;
}
function renderExpensePlan(){
  const rows=expenseRows(),preview=state.draft.expense_items==null,months=Object.keys(state.result?.kpis.monthly_spend||{}).sort(),chosen=months.includes(state.expenseMonth)?state.expenseMonth:state.result?.schedule.closing_date.slice(0,7);
  return `<section class="card form-section expense-plan"><div class="section-bar"><div><h2>기간별 지출 계획</h2><p>생활비, 전세 주거비, 이사 후 지출, 양육비를 각각 나눠요.</p></div><button class="button primary small" data-action="expense-add">+ 지출 추가</button></div><div class="expense-phases"><span>전세 거주 중</span><span>퇴거·이사 이후</span><span>출산·양육</span></div>${preview?'<div class="notice expense-preview"><strong>기존 금액으로 새 지출 구분을 준비했어요.</strong><p>적용할 때 고정비가 전세 주거비인지, 전세이자를 포함하는지 확인합니다. 현재 계산은 기존 입력 기준이에요.</p><button class="button small" data-action="expense-apply">이 지출 계획 적용</button></div>':''}<div class="table-wrap"><table><thead><tr><th>구분 · 지출 이름</th><th>월 금액</th><th>시작일 → 종료일</th><th>계산 방식</th><th></th></tr></thead><tbody>${rows.map(row=>`<tr class="${row.enabled?'':'muted-row'}"><td><span class="record-name">${esc(row.name)}</span><small class="record-subtitle">${esc(row.category)}${row.includes_lease_interest?' · 전세대출 이자 포함':''}${row.includes_management?' · 새집 관리비 포함':''}${row.enabled?'':' · 사용 안 함'}</small></td><td class="amount">${won(row.amount)}원</td><td>${expensePeriod(row)}</td><td>${row.prorate?'부분월 일할':'부분월도 월 전액'}<small class="record-subtitle">${row.pay_day?`매월 ${row.pay_day}일`:'가계 납부일'}</small></td><td><div class="row-actions"><button class="row-action" data-action="expense-edit" data-id="${esc(row.id)}">수정</button><button class="row-action" data-action="expense-toggle" data-id="${esc(row.id)}">${row.enabled?'사용 안 함':'사용'}</button><button class="row-action danger" data-action="expense-delete" data-id="${esc(row.id)}">삭제</button></div></td></tr>`).join('')}</tbody></table></div>${rows.length?'':'<p class="cash-note">직접 지출이 없습니다. 대출 상환 등 자동 지출은 계속 반영돼요.</p>'}<div class="expense-presets"><button class="button small soft" data-action="expense-after">+ 이사 후 고정비</button><button class="button small soft" data-action="expense-childcare">양육비 설정</button></div><p class="hint">이사 후 보험·통신 등 남는 고정비는 직접 추가해 주세요. 같은 기간의 여러 항목은 합산됩니다. 주담대·새집 관리비는 아래 자동 지출에서 확인하세요.</p></section><section class="card form-section"><div class="section-bar"><div><h2>월별 지출을 확인해요</h2><p>적용 기간과 자동 지출을 합쳐 비교합니다.</p></div><select id="expense-month" aria-label="지출 확인 월">${months.map(month=>`<option value="${month}" ${month===chosen?'selected':''}>${month.replace('-','년 ')}월</option>`).join('')}</select></div><div id="expense-summary">${expenseSummaryBody()}</div><p class="hint">월 한도 점검용 합계입니다. 연 비용·보유세는 월평균이며, 일회성 수리·출산 비용과 실제 납부일의 현금은 날짜별 원장에서 확인하세요.</p></section>`;
}
function renderIncome(){return `<section class="card form-section"><h2>소득</h2><div class="fields">${field('husband_net_pay','남편 월 실수령')}${field('wife_net_pay','아내 월 실수령')}${field('payday','급여일 · 매월 며칠','int')}${field('husband_gross','남편 연 총급여')}${field('wife_gross','아내 연 총급여')}${field('bank_income','은행 인정 연소득')}</div></section>`;}
function renderAutomaticExpenses(){return `<section class="card form-section"><h2>자동 지출 · 주거비와 납부일</h2><p class="hint">현재 전세 주거비에 포함된 이자는 기간별 항목의 ‘전세대출 이자 포함’으로 구분합니다. 주담대·신용대출 상환은 아래 대출 조건으로 자동 계산하므로 직접 지출에 다시 넣지 마세요.</p><div class="fields">${field('expense_day','가계 기본 납부일 · 빈칸은 급여일','optional-int')}${field('lease_loan_rate','전세대출 연 이율 · %','percent')}${field('lease_loan_repay_date','전세대출 상환일','date')}${field('mgmt_fee','새집 월 관리비','money','listing')}${field('management_start_date','새집 관리비 시작일','date')}${field('management_end_date','새집 관리비 종료일 · 선택','date')}</div></section><section class="card form-section"><h2>출산·양육 일정</h2><div class="fields">${field('birth_date','출산 예정일','date')}${field('birth_one_off','출산 일회성 비용')}</div><p class="hint">매달 양육비는 위 기간별 지출에서 금액과 시작·종료일을 설정하세요. 출산 예정일은 출산 일회성 비용과 등록된 육아 지원금 일정에도 반영됩니다.</p></section><section class="card form-section"><h2>연간 비용·보유세·저축</h2><div class="fields">${field('annual_cost','연 1회 비용')}${field('annual_cost_month','연 비용 납부월 · 1~12','int')}${field('property_tax_annual','연간 보유세 예상액')}${field('monthly_saving','매달 적금·투자 납입')}${field('saving_end_date','적금·투자 납입 종료일','date')}</div>${checkField('fixed_in_living',state.draft.expense_items==null?'기존 고정비·연 비용이 생활비에 이미 포함':'연 1회 비용이 기간별 지출에 이미 포함')}${checkField('saving_in_spend_limit','적금·투자 납입을 월 지출 한도에도 포함')}</section><section class="card form-section"><h2>지출 한도와 비상금</h2><div class="fields">${field('monthly_spend_limit','월 가계지출 한도')}${field('min_emergency_cash','최소 비상금')}${field('target_cash_after_purchase','매수 후 목표 현금')}</div></section>`;}
async function commitExpensePlan(rows){
  if(state.saving)throw new Error('저장이 끝난 뒤 다시 시도해 주세요.');
  const snapshot=JSON.stringify(state.draft),workspace=state.workspace,candidate=clone(state.draft);candidate.expense_items=clone(rows);
  const result=await post('/api/evaluate',{household:candidate,listing_id:selected().id,confirmed_only:state.confirmed});
  if(workspace!==state.workspace||snapshot!==JSON.stringify(state.draft))throw new Error('입력이 바뀌었습니다. 지출 설정을 다시 확인해 주세요.');
  ++state.sequence;state.draft=candidate;state.result=result;state.max=null;state.evaluating=false;state.calculatedSnapshot=JSON.stringify(candidate);render();
}
async function deleteExpense(id){
  const rows=expenseRows(),row=rows.find(item=>item.id===id),workspace=state.workspace;if(!row)return;
  if(!await confirmation('이 지출 항목을 삭제할까요?',`<p class="preview-summary"><strong>${esc(row.name)}</strong><br>월 ${won(row.amount)}원 · ${esc(row.start_date||'기준일')} → ${esc(row.end_date||'계속')}<br>저장 전 버전은 기록에서 복원할 수 있어요.</p>`,'삭제',{focusConfirm:true})||workspace!==state.workspace)return;
  try{await commitExpensePlan(rows.filter(item=>item.id!==id));toast('지출 항목을 삭제했습니다. 변경사항을 저장해 주세요.');}catch(error){toast(error.message,true);}
}
function editExpense(id=null,preset=null){
  const rows=expenseRows(),existing=rows.find(row=>row.id===id),s=state.draft.settings;
  const row=clone(existing||{id:nextId(rows,'E'),name:preset==='after'?'이사 후 고정비':preset==='childcare'?'양육비':'',category:preset==='childcare'?'양육비':'고정비',amount:preset==='childcare'?s.childcare_cost:null,start_date:preset==='after'?'퇴거일+1':preset==='childcare'?(s.birth_date?'출산예정일':''):'기준일',end_date:null,pay_day:null,enabled:true,prorate:false,includes_lease_interest:false,includes_management:false});
  if(preset==='childcare'){row.enabled=true;if(!row.start_date)row.start_date=s.birth_date?'출산예정일':'';}
  const checks=[['enabled','이 지출을 계산에 사용'],['prorate','월중 시작·종료하면 해당 일수만 일할 계산'],['includes_lease_interest','이 금액에 전세대출 이자가 이미 포함'],['includes_management','이 금액에 새집 관리비가 이미 포함']];
  openModal(`${existing?'수정':'추가'} · 기간별 지출`,`<form id="expense-form" autocomplete="off"><div class="fields">${dialogInput('name','지출 이름',row.name,'text',true)}${dialogSelect('category','지출 분류',['생활비','주거비','고정비','양육비','기타'],row.category)}${dialogInput('amount','월 금액',row.amount??'')}${dialogInput('start_date','시작일 · 빈칸은 기준일',row.start_date||'','date')}${dialogInput('end_date','종료일 · 포함, 빈칸은 계속',row.end_date||'','date')}${dialogInput('pay_day','납부일 · 매월 며칠 (선택)',row.pay_day??'','number')}</div><div class="expense-date-presets"><button type="button" class="row-action" data-expense-date="start_date" data-date="기준일">기준일부터</button><button type="button" class="row-action" data-expense-date="end_date" data-date="퇴거일">퇴거일까지</button><button type="button" class="row-action" data-expense-date="end_date" data-date="출산예정일">출산일까지</button><button type="button" class="row-action" data-expense-date="start_date" data-date="퇴거일+1">퇴거 다음 날부터</button><button type="button" class="row-action" data-expense-date="start_date" data-date="입주일">입주일부터</button><button type="button" class="row-action" data-expense-date="start_date" data-date="출산예정일">출산일부터</button></div>${checks.map(([name,label])=>`<label class="checkbox-line"><input autocomplete="off" type="checkbox" name="${name}" ${row[name]?'checked':''}> ${label}</label>`).join('')}<p class="field-help">부분월 전액은 그 달 월액을 한 번 반영합니다. 납부일이 적용 기간 밖이면 시작일 또는 종료일에 반영해요. 일할 계산은 그 달의 실제 일수를 사용합니다.</p><div class="modal-error" role="alert"></div><div class="modal-actions"><button type="button" class="button" id="expense-cancel">취소</button><button type="submit" class="button primary">반영하고 계산</button></div></form>`);
  $('#expense-cancel').onclick=closeModal;
  $$('[data-expense-date]').forEach(button=>button.onclick=()=>{closeCalendar();$(`#record-${button.dataset.expenseDate}`).value=button.dataset.date;});
  $('#expense-form').onsubmit=async event=>{event.preventDefault();const button=$('button[type="submit"]',event.currentTarget);button.disabled=true;try{
    const data=new FormData(event.currentTarget),updated={...row,name:String(data.get('name')||'').trim(),category:data.get('category'),amount:readMoneyInput($('#record-amount')),start_date:String(data.get('start_date')||'').trim()||null,end_date:String(data.get('end_date')||'').trim()||null,pay_day:data.get('pay_day')?Number(data.get('pay_day')):null};
    for(const [key]of checks)updated[key]=data.has(key);
    if(!updated.name||updated.amount==null)throw new Error('지출 이름과 월 금액을 입력해 주세요.');
    if(updated.enabled&&updated.category==='양육비'&&!updated.start_date)throw new Error('양육비 시작일을 입력해 주세요. 출산 예정일에 연결할 수도 있어요.');
    const candidate=clone(rows);if(existing)candidate[candidate.findIndex(item=>item.id===id)]=updated;else candidate.push(updated);
    await commitExpensePlan(candidate);closeModal();toast('지출 계획을 반영했습니다. 확인 후 변경사항을 저장해 주세요.');
  }catch(error){$('.modal-error').textContent=error.message;}finally{button.disabled=false;}};
}
function renderTaxCardPlan(){
  const s=state.draft.settings;
  return `<section class="card form-section" id="tax-card-plan"><h2>취득세 카드 납부</h2>${checkField('card_pay_tax','취득세를 카드로 납부해요')}${s.card_pay_tax?`${checkField('card_repay_on_credit_draw','신용대출 실행일에 남은 카드 할부 완납')}<p class="hint">${s.card_repay_on_credit_draw?'신용대출 실행일에 남은 카드 원금이 한 번 출금되고 카드 빚은 0원이 됩니다. 이후 카드 할부는 청구하지 않아요. 신용대출 빚은 그대로 남습니다.':'아래 일정에 따라 카드 할부를 나누어 납부합니다.'} 신용대출 실행일은 위 대출 설정을 따릅니다.</p><div class="fields">${field('card_months','카드 할부 개월','int')}${field('card_first_offset','첫 납부 · 잔금월부터 몇 개월 후','int')}${field('card_paid_installments','유이자 회차 수','int')}${field('card_fee_rate','할부 연 수수료율 · %','percent')}</div><p class="hint">완납일 이전 회차만 기존 할부 금액·수수료로 계산하고, 완납일에는 남은 원금만 갚는 계획입니다. 신용대출을 끄거나 미확정 대출금을 제외해도 완납 지출은 유지됩니다.</p>`:'<p class="hint">취득세는 잔금일 현금 지출에 포함됩니다.</p>'}</section>`;
}
function renderCosts(){return renderPurchaseCosts({state,selected,field,checkField,taxCard:renderTaxCardPlan,esc,won,shortMoney});}
function renderSettings() {
  const s=state.draft.settings, options=state.draft.bank_quotes.flatMap(q=>q.options.map(o=>({...o,bank:q.bank,date:q.date}))),chosen=s.mortgage_quote_option?.[s.mortgage_method]||'';
  return `<div id="calculation-state" class="recalculate-note" ${state.calculatedSnapshot===JSON.stringify(state.draft)?'hidden':''}>지출이나 소득이 바뀌었습니다. 다시 계산하면 새 조건으로 보여드려요.</div>${renderIncome()}${renderExpensePlan()}${renderAutomaticExpenses()}<section class="card form-section"><h2>주택담보대출</h2><div class="fields"><div class="field wide"><label for="bank-option">은행 상담 옵션</label><select id="bank-option"><option value="">직접 입력</option>${options.map(o=>`<option value="${esc(o.id)}" ${o.id===chosen?'selected':''}>${esc(o.bank)} · ${esc(o.method)} · ${(Number(o.rate)*100).toFixed(2)}% · 한도 ${shortMoney(o.limit)}</option>`).join('')}</select></div>${field('mortgage_desired','희망 대출금 · 원')}${field('bank_confirmed_limit','은행 확인 한도 · 원')}${field('mortgage_rate','실제 연 금리 · %','percent')}${selectField('mortgage_method','상환 방식',['원리금균등','원금균등'])}${field('mortgage_years','상환기간 · 년','int')}${field('monthly_repay_limit','월 주담대 상환 한도 · 원')}${field('ltv','LTV · %','percent')}${field('stress_rate','심사 스트레스 가산 · %p','percent')}${selectField('loan_status','대출 확인 상태',['미확정','은행 상담 완료','승인 완료'])}</div><p class="hint">금리 또는 은행 한도를 직접 수정하면 직접 입력 모드로 전환합니다. 상담 조건과 실제 심사 조건은 다시 확인하세요.</p></section><section class="card form-section"><h2>신용대출과 청약담보대출</h2>${checkField('credit_use','신용대출을 계획에 포함')}<div class="fields">${field('credit_amount','신용대출 · 원 (0이면 자동)')}${field('credit_rate','신용대출 연 금리 · %','percent')}${field('credit_draw_date','실행일 · 날짜 또는 잔금일+1','text')}${selectField('credit_borrower','신용대출 차주',['남편','아내'])}${selectField('credit_status','신용대출 확인 상태',['미확정','확인 완료'])}${selectField('credit_method','상환 방식',['만기일시','5년 분할'])}</div>${checkField('sub_loan_use','청약통장 담보대출을 계획에 포함')}<div class="fields">${field('sub_amount','청약담보대출 · 원 (0이면 자동)')}${field('sub_draw_date','실행일 · 날짜 또는 잔금일+1','text')}${selectField('sub_status','청약담보 확인 상태',['미확정','확인 완료'])}</div></section>${renderTaxCardPlan()}<div class="page-actions"><button class="button soft" id="settings-evaluate">변경한 조건으로 계산</button><button class="button primary" data-action="save">변경사항 저장</button></div>`;
}
function renderDateCash(detailed=false) {
  const r=state.result, days=r?.daily_balances;
  if(!days?.length)return '';
  const first=days[0].date,last=days.at(-1).date,chosen=state.cashDate||r.schedule.closing_date;
  const day=days.find(row=>row.date===chosen),inRange=Boolean(day);
  const events=r.ledger.filter(row=>row.date===chosen);
  const inflows=events.filter(row=>row.amount>0).reduce((sum,row)=>sum+row.amount,0);
  const outflows=-events.filter(row=>row.amount<0).reduce((sum,row)=>sum+row.amount,0);
  const checkpoints=[['기준일',first],['계약일',r.schedule.contract_date],['중도금일',r.schedule.interim_date],['잔금일',r.schedule.closing_date],['입주일',r.schedule.move_in_date]].filter(([,date])=>date&&date>=first&&date<=last);
  const detail=day&&detailed?`<div class="cash-details"><div><h3>이날의 입출금</h3>${events.length?`<div class="table-wrap"><table><thead><tr><th>항목</th><th>입금·출금</th><th>이후 현금</th></tr></thead><tbody>${events.map(row=>`<tr><td>${esc(row.label)}</td><td class="amount ${row.amount<0?'negative-text':''}">${row.amount>0?'+':''}${won(row.amount)}원</td><td class="amount">${won(row.balance)}원</td></tr>`).join('')}</tbody></table></div>`:'<p class="cash-empty">이날 예정된 입출금이 없습니다. 전날 잔고가 이어집니다.</p>'}</div><div><h3>남은 빚 원금</h3>${Object.keys(day.debt_breakdown).length?`<div class="table-wrap"><table><thead><tr><th>빚 종류</th><th>미상환 원금</th></tr></thead><tbody>${Object.entries(day.debt_breakdown).map(([label,amount])=>`<tr><td>${esc(label)}</td><td class="amount">${won(amount)}원</td></tr>`).join('')}</tbody></table></div>`:'<p class="cash-empty">이 날짜에 남은 등록 부채가 없습니다.</p>'}<p class="cash-note">이자·수수료는 현금 지출에 반영하며, 상환한 원금만 빚에서 줄입니다.</p></div></div>`:'';
  return `<section class="card cash-card" id="date-cash"><div class="card-title"><div><h2>특정 날짜에 얼마가 남을까요?</h2><p>입력한 일정에 따른 예상 잔액 · 하루 마감 기준</p></div>${detailed?'':'<a href="#ledger" class="row-action">자세히 보기 →</a>'}</div><div class="cash-controls"><div class="cash-picker"><button class="row-action" data-cash-step="-1" aria-label="이전 날짜" ${!inRange||chosen===first?'disabled':''}>←</button><label for="cash-date" class="sr-only">조회 날짜</label><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="cash-date" type="date" min="${first}" max="${last}" value="${esc(chosen)}"><button class="row-action" data-cash-step="1" aria-label="다음 날짜" ${!inRange||chosen===last?'disabled':''}>→</button></div><div class="cash-shortcuts">${checkpoints.map(([label,date])=>`<button class="row-action ${chosen===date?'selected':''}" data-cash-date="${date}">${label}</button>`).join('')}</div></div>${day?`<div class="cash-totals">${stat('보유 현금 · 대출금 포함',shortMoney(day.closing),`${won(day.closing)}원`,day.closing<0?'negative':'highlight')}${stat('남은 빚 원금',shortMoney(day.debt_total),`${won(day.debt_total)}원`)}${stat('현금 − 빚',shortMoney(day.net_cash),`${won(day.net_cash)}원`)}</div><div class="cash-flow">${[['시작 현금',day.opening],['이날 입금',inflows],['이날 출금',outflows],['장중 최저',day.minimum]].map(([label,amount])=>`<div><span>${label}</span><strong class="${amount<0?'negative-text':''}">${won(amount)}원</strong></div>`).join('')}</div>${detail}`:`<p class="cash-range-error" role="status">${first} ~ ${last} 사이의 날짜를 선택해 주세요.</p>`}<p class="cash-note">변동자산 ${esc(state.result.kpis.variable_asset_mode||'보수적')} 기준의 예상치입니다. 매수 투입 제외 항목·현금화 전 자산은 포함하지 않습니다. ‘현금 − 빚’에는 주택·반환 전 보증금의 가치가 포함되지 않습니다.</p>${Number(state.draft.settings.existing_debt_annual)>0?'<p class="cash-note">DSR용 연간 상환액만 입력한 기타 부채는 원금을 알 수 없어 남은 빚에 포함하지 않습니다.</p>':''}${detailed?`<label class="checkbox-line"><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="cash-confirmed-only" type="checkbox" ${state.confirmed?'checked':''}> 확정된 미래 자금만 계산</label>`:''}</section>`;
}
function bindDateCash() {
  const picker=$('#cash-date');if(!picker)return;
  picker.onchange=()=>{state.cashDate=picker.value;render();};
  $$('[data-cash-date]').forEach(button=>button.onclick=()=>{state.cashDate=button.dataset.cashDate;render();});
  $$('[data-cash-step]').forEach(button=>button.onclick=()=>{const date=new Date(`${picker.value}T00:00:00Z`);date.setUTCDate(date.getUTCDate()+Number(button.dataset.cashStep));state.cashDate=date.toISOString().slice(0,10);render();});
  $('#cash-confirmed-only')?.addEventListener('change',event=>{state.confirmed=event.target.checked;calculate();});
}
function renderLedger() {
  const r=state.result;if(!r)return '<section class="card loading-card">계산 결과를 불러오는 중입니다.</section>';
  return `<div id="calculation-state" class="recalculate-note" ${state.calculatedSnapshot===JSON.stringify(state.draft)?'hidden':''}>입력이 바뀌었습니다. 상단에서 다시 계산하면 새 조건의 결과를 보여드려요.</div>${renderDateCash(true)}<section class="card"><div class="section-bar"><div><h2>현금 원장</h2><p>일별 입출금과 월말 잔고를 더 살펴보세요.</p></div></div><div class="ledger-toolbar"><select id="ledger-mode" aria-label="원장 종류"><option value="monthly">월말 잔고</option><option value="events">일별 입출금</option></select><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="ledger-search" type="search" placeholder="월·날짜·항목 검색" aria-label="원장 검색"></div><div id="ledger-table"></div></section>`;
}
function renderLedgerTable() {
  const mode=$('#ledger-mode')?.value||'monthly',search=$('#ledger-search')?.value||'';
  const rows=mode==='monthly'?Object.entries(state.result.kpis.month_end_balance).filter(([month])=>month.includes(search)).map(([month,balance])=>`<tr><td>${month}</td><td class="amount ${balance<0?'negative-text':''}">${won(balance)}원</td></tr>`):state.result.ledger.filter(row=>(row.date+' '+row.label).includes(search)).map(row=>`<tr><td>${row.date}</td><td>${esc(row.label)}</td><td class="amount ${row.amount<0?'negative-text':''}">${row.amount>0?'+':''}${won(row.amount)}원</td><td class="amount ${row.balance<0?'negative-text':''}">${won(row.balance)}원</td></tr>`);
  $('#ledger-table').innerHTML=`<div class="table-wrap"><table><thead><tr>${(mode==='monthly'?['월','월말 잔고']:['날짜','항목','입금·출금','이후 잔고']).map(label=>`<th>${label}</th>`).join('')}</tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
}
function render() {
  const [label,title,description]=pages[state.route];
  $('#navigation').innerHTML=Object.entries(pages).map(([key,[name]])=>`<a href="#${key}" class="nav-item ${state.route===key?'active':''}" aria-current="${state.route===key?'page':'false'}"><svg viewBox="0 0 24 24"><path d="${icons[key]}" stroke-linecap="round" stroke-linejoin="round"/></svg><span>${name}</span></a>`).join('');
  $('#breadcrumb-title').textContent=label;$('#page-title').textContent=title;$('#page-description').textContent=description;
  $('#workspace-switch').innerHTML=state.workspaces.map(w=>`<button data-workspace="${esc(w.id)}" class="${w.id===state.workspace?'active':''}" aria-pressed="${w.id===state.workspace}">${esc(w.label)}</button>`).join('');
  $('#content').innerHTML=`<nav class="mobile-nav">${Object.entries(pages).map(([key,[name]])=>`<a href="#${key}" class="${state.route===key?'active':''}">${name}</a>`).join('')}</nav>${state.workspace==='demo'?'<div class="demo-banner">가상 테스트 중입니다. 이 화면에서 저장해도 실제 가구 데이터는 바뀌지 않아요.</div>':''}`+({plan:renderPlan,costs:renderCosts,funds:renderFunds,support:renderSupport,settings:renderSettings,ledger:renderLedger,leave:menus.renderLeave,repayment:menus.renderRepayment,banks:menus.renderBanks,purchase:purchase.render}[state.route])();
  updateSavedState();
  if(state.route==='plan'){syncRefundLink();$('#refund-interim-link').onclick=toggleRefundLink;}
  bindDateCash();
  if(state.route==='funds'){
    const filter=type=>{state.fundTypeFilter=state.fundTypeFilter===type?null:type;render();$('#fund-list').scrollIntoView({block:'start',behavior:'smooth'});};
    $$('[data-fund-filter]').forEach(button=>{button.onclick=()=>filter(button.dataset.fundFilter);button.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();filter(button.dataset.fundFilter);}};});
    $$('[data-fund-scope]').forEach(button=>button.onclick=()=>{state.fundScope=button.dataset.fundScope;render();});
    $('#fund-purchase-only').onchange=e=>{state.fundPurchaseOnly=e.target.checked;render();};
    $('#fund-type-filter').onchange=e=>{state.fundTypeFilter=e.target.value||null;render();};
    $('#fund-filter-clear')?.addEventListener('click',()=>{state.fundTypeFilter=null;render();});
  }
  $('#variable-asset-mode')?.addEventListener('change',event=>{state.draft.settings.variable_asset_mode=event.target.value;state.max=null;render();calculate();});
  if(state.route==='plan'){drawChart();$('#calculate-button').onclick=calculate;$('#maximum-button').onclick=calculateMaximum;$('#chart-range').onchange=e=>{state.chartRange=e.target.value;drawChart();};$('#confirmed-only').onchange=e=>{state.confirmed=e.target.checked;calculate();};$('#show-checks')?.addEventListener('click',()=>{state.showAll=!state.showAll;render();});$('#listing-select').onchange=e=>{state.draft.selected_listing=e.target.value;state.max=null;render();calculate();};}
  if(state.route==='costs'){
    $('#costs-calculate').onclick=()=>calculate();$('#costs-save').onclick=saveDraft;
    $('#cost-listing-select').onchange=e=>{state.draft.selected_listing=e.target.value;state.max=null;render();calculate();};
    for(const [id,key,amount] of [['cost-tax-mode','acquisition_tax_amount',state.result?.costs.acquisition_taxes_total],['cost-broker-mode','brokerage_amount',state.result?.costs.brokerage]]){
      $('#'+id).onchange=e=>{if(e.target.value==='auto'){selected()[key]=null;inputProblems.delete(`listing:${selected().id}:${key}`);state.max=null;render();calculate();return;}if(!validInputs()){e.target.value=selected()[key]==null?'auto':'manual';return;}selected()[key]=e.target.value==='manual'?(amount||0):null;inputProblems.delete(`listing:${selected().id}:${key}`);state.max=null;render();calculate();};
    }
  }
  if(state.route==='settings'){$('#settings-evaluate').onclick=()=>calculate(true);$('#bank-option').onchange=e=>{const option=state.draft.bank_quotes.flatMap(q=>q.options).find(o=>o.id===e.target.value),s=state.draft.settings;if(option){s.mortgage_method=option.method;s.mortgage_rate=option.rate;s.bank_confirmed_limit=option.limit;s.mortgage_quote_option={...s.mortgage_quote_option,[option.method]:option.id};}else{s.mortgage_quote_option={};}render();};}
  if(state.route==='settings')$('#expense-month').onchange=event=>{state.expenseMonth=event.target.value;$('#expense-summary').innerHTML=expenseSummaryBody();};
  if(state.route==='ledger'&&state.result){renderLedgerTable();$('#ledger-mode').onchange=renderLedgerTable;$('#ledger-search').oninput=renderLedgerTable;}
  refreshCalendar();
  for(const problem of inputProblems.values()){if(problem.listingId&&problem.listingId!==selected().id)continue;const input=$(`[data-scope="${problem.scope}"][data-key="${problem.key}"]`);if(input){input.value=problem.raw;input.classList.add('invalid');input.setCustomValidity(problem.error);}}
  upgrades?.afterRender();
  menus?.bind();
  purchase?.bind();
}
async function calculate(goToPlan=false) {
  if(!validInputs())return;
  const sequence=++state.sequence,snapshot=JSON.stringify(state.draft);state.evaluating=true;
  const button=$('#calculate-button');if(button){button.disabled=true;button.innerHTML='<span class="spinner"></span> 계산 중…';}
  try{const result=await post('/api/evaluate',{household:clone(state.draft),listing_id:selected().id,confirmed_only:state.confirmed});if(sequence!==state.sequence)return;if(snapshot!==JSON.stringify(state.draft)){toast('입력이 바뀌었습니다. 다시 계산해 주세요.');return;}state.result=result;state.calculatedSnapshot=snapshot;if(goToPlan){state.route='plan';location.hash='plan';}render();}
  catch(error){if(sequence===state.sequence)toast(error.message,true);}
  finally{if(sequence===state.sequence){state.evaluating=false;const current=$('#calculate-button');if(current){current.disabled=false;current.textContent='현재 조건으로 계산';}}}
}
async function calculateMaximum() {
  if(!validInputs())return;
  const button=$('#maximum-button');button.disabled=true;button.innerHTML='<span class="spinner"></span> 최대 매수가 계산 중…';
  const sequence=state.sequence,workspace=state.workspace,snapshot=JSON.stringify(state.draft);
  try{const result=await post('/api/max-price',{household:clone(state.draft),listing_id:selected().id,mode:'listing',confirmed_only:state.confirmed});if(state.workspace===workspace&&snapshot===JSON.stringify(state.draft)&&sequence===state.sequence){state.max=result;if($('#maximum-result'))$('#maximum-result').innerHTML=renderMaximum();}else toast('입력이 바뀌어 이전 조건의 최대가를 적용하지 않았습니다.');}
  catch(error){toast(error.message,true);}finally{if(button.isConnected){button.disabled=false;button.textContent='이 조건의 최대 매수가 찾기';}}
}
function drawChart() {
  const container=$('#chart');if(!container)return;
  let rows=state.result?.daily_balances||[];
  if(state.chartRange==='purchase'&&rows.length){const end=new Date(rows[0].date+'T00:00:00');end.setFullYear(end.getFullYear()+1);rows=rows.filter(r=>new Date(r.date+'T00:00:00')<=end);}
  if(state.chartRange==='leave'){const s=state.draft.settings,start=s.maternity_start||s.wife_leave_start;if(start){const end=state.result.kpis.min_balance_during_leave_date;rows=rows.filter(r=>r.date>=String(start).slice(0,10));}else rows=[];}
  if(!rows.length){container.innerHTML='<div class="empty">이 기간에 표시할 잔고가 없습니다.</div>';return;}
  const width=900,height=250,pad={left:61,right:20,top:17,bottom:32},emergency=Number(state.draft.settings.min_emergency_cash||0);
  let low=Math.min(0,emergency,...rows.map(r=>r.minimum)),high=Math.max(emergency,...rows.map(r=>r.minimum));const spread=high-low||1;low-=spread*.1;high+=spread*.13;
  const x=index=>pad.left+index/Math.max(1,rows.length-1)*(width-pad.left-pad.right),y=value=>pad.top+(high-value)/(high-low)*(height-pad.top-pad.bottom);
  const path=rows.map((row,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(row.minimum).toFixed(2)}`).join(' ');
  const ticks=Array.from({length:5},(_,i)=>high-(high-low)*i/4);
  container.innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="일별 최저 현금 잔고 그래프"><defs><linearGradient id="cash-fill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#4a9676" stop-opacity=".2"/><stop offset="100%" stop-color="#4a9676" stop-opacity=".015"/></linearGradient></defs>${ticks.map(t=>`<line x1="${pad.left}" x2="${width-pad.right}" y1="${y(t)}" y2="${y(t)}" stroke="#edf0e9"/><text x="${pad.left-12}" y="${y(t)+4}" text-anchor="end">${esc(shortMoney(t))}</text>`).join('')}<path d="${path} L${x(rows.length-1)},${height-pad.bottom} L${pad.left},${height-pad.bottom}Z" fill="url(#cash-fill)"/><path d="${path}" fill="none" stroke="#377d5e" stroke-width="2.2"/><line x1="${pad.left}" x2="${width-pad.right}" y1="${y(emergency)}" y2="${y(emergency)}" stroke="#b79450" stroke-dasharray="5 5"/><line x1="${pad.left}" x2="${width-pad.right}" y1="${y(0)}" y2="${y(0)}" stroke="#d6dfd1"/>${Array.from({length:5},(_,i)=>{const index=Math.round(i*(rows.length-1)/4);return `<text x="${x(index)}" y="${height-5}" text-anchor="middle">${rows[index].date.slice(0,7).replace('-','.')}</text>`;}).join('')}<line id="chart-hover-line" class="chart-hover" y1="${pad.top}" y2="${height-pad.bottom}" stroke="#588365" stroke-dasharray="3 3" visibility="hidden"/><circle id="chart-hover-point" class="chart-hover" r="4" fill="#377d5e" stroke="white" stroke-width="2" visibility="hidden"/></svg><div class="chart-tooltip"></div>`;
  const svg=$('svg',container),tip=$('.chart-tooltip',container),line=$('#chart-hover-line',container),point=$('#chart-hover-point',container);
  svg.onpointermove=event=>{const rect=svg.getBoundingClientRect(),relative=(event.clientX-rect.left)/rect.width*width,index=Math.max(0,Math.min(rows.length-1,Math.round((relative-pad.left)/(width-pad.left-pad.right)*(rows.length-1)))),row=rows[index];line.setAttribute('x1',x(index));line.setAttribute('x2',x(index));line.setAttribute('visibility','visible');point.setAttribute('cx',x(index));point.setAttribute('cy',y(row.minimum));point.setAttribute('visibility','visible');tip.innerHTML=`${row.date}<br>최저 <strong>${won(row.minimum)}원</strong>`;tip.style.display='block';tip.style.left=Math.min(Math.max(0,event.clientX-rect.left+12),rect.width-190)+'px';tip.style.top='20px';};
  svg.onpointerleave=()=>{tip.style.display='none';line.setAttribute('visibility','hidden');point.setAttribute('visibility','hidden');};
}
function openModal(title,body) {$('#modal-title').textContent=title;$('#modal-body').innerHTML=body;$('#modal').showModal();}
function closeModal() {closeCalendar();$('#modal').close();}
function confirmation(title,body,label='확인',{focusConfirm=false}={}) {
  return new Promise(resolve=>{
    openModal(title,`${body}<div class="modal-actions"><button class="button" id="confirm-cancel">취소</button><button class="button primary" id="confirm-ok">${esc(label)}</button></div>`);
    const dialog=$('#modal');let done=false;
    const finish=value=>{if(done)return;done=true;dialog.removeEventListener('close',cancel);closeModal();resolve(value);};
    const cancel=()=>{if(!dialog.open)finish(false);};
    $('#confirm-ok').onclick=()=>finish(true);$('#confirm-cancel').onclick=()=>finish(false);dialog.addEventListener('close',cancel);
    if(focusConfirm)$('#confirm-ok').focus({preventScroll:true});
  });
}
const nextId=(rows,prefix)=>{let n=1;while(rows.some(row=>row.id===prefix+String(n).padStart(2,'0')))n++;return prefix+String(n).padStart(2,'0');};
const moneyNames=new Set(['value','amount','price','appraisal','mgmt_fee','repair','cash_out_amount','cost','conservative_amount','aggressive_amount']);
const dialogInput=(name,label,value='',type='text',wide=false)=>{
  const id=`record-${name}`,attributes=`name="${name}"`,money=moneyNames.has(name),date=type==='date'||['date','available_date'].includes(name);
  if(money)label=label.replace(' · 원','');
  const control=money?moneyControl(id,label,value,attributes,{defaultUnit:['price','appraisal'].includes(name)?1e8:undefined}):date?dateControl(id,label,value,attributes,{rollingNow:name==='available_date'}):`<input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="${id}" ${attributes} type="${type}" value="${esc(value)}">`;
  return `<div class="field ${wide?'wide':''}"><label for="${id}">${esc(label)}</label>${control}</div>`;
};
const dialogSelect=(name,label,options,value)=>`<div class="field"><label for="record-${name}">${esc(label)}</label><select id="record-${name}" name="${name}">${[...new Set([...options,value].filter(Boolean))].map(v=>`<option ${v===value?'selected':''}>${esc(v)}</option>`).join('')}</select></div>`;
function editRecord(kind,id=null,preset=null) {
  const support=kind==='support',listing=kind==='listing';
  const rows=state.draft[support?'parent_support':listing?'listings':'fund_events'];
  const existing=id==null?null:support?rows[Number(id)]:rows.find(row=>row.id===id);
  const row=clone(existing||(preset?{name:preset.name,type:preset.type}:{}));
  if(preset)row.is_variable=true;
  if(row.is_variable){row.conservative_amount??=row.cash_out_amount??row.value??null;row.aggressive_amount??=row.cash_out_amount??row.value??null;}
  let fields='';
  if(listing){fields=dialogInput('name','단지·매물 이름',row.name||'', 'text',true)+dialogInput('price','검토 매수가 · 원',row.price==null?'':won(row.price))+dialogInput('area_m2','전용면적 · ㎡',row.area_m2||'84.9')+dialogInput('appraisal','담보평가액 · 원 (선택)',row.appraisal==null?'':won(row.appraisal))+dialogInput('mgmt_fee','월 관리비 · 원',won(row.mgmt_fee??state.draft.settings.mgmt_fee_default))+dialogInput('repair','수리비 · 원',won(row.repair??state.draft.settings.repair_default))+dialogSelect('tenant','거주 상태',['집주인 거주','세안고매매'],row.tenant||'집주인 거주')+dialogInput('move_in_available','입주 가능일 (선택)',row.move_in_available||'','date');}
  else if(support){fields=dialogSelect('kind','지원 유형',['증여','차입'],row.kind||'증여')+dialogSelect('to','받는 사람',['공동','남편','아내'],row.to||'공동')+dialogInput('amount','금액 · 원',row.amount==null?'':won(row.amount))+dialogInput('date','입금일 · 날짜 또는 일정',row.date||'', 'text')+dialogSelect('status','확정 여부',['미확정','확정','확인 완료','제외'],row.status||'미확정');}
  else {fields=dialogInput('name','자금 이름',row.name||'','text',true)+dialogSelect('type','자금 유형',fundTypes.map(([type])=>type),row.type||'현금·예금')+dialogSelect('owner','누구의 돈인가요?',['공동','남편','아내'],row.owner||'공동')+dialogInput('value','금액 · 원 (평가액)',row.value==null?'':won(row.value))+dialogInput('available_date','사용 가능일 · 지금/날짜/일정',row.available_date||'지금')+dialogInput('cash_out_amount','매도·수령 예상액 · 원 (선택)',row.cash_out_amount==null?'':won(row.cash_out_amount))+dialogInput('cost','비용·세금 · 원 (선택)',row.cost==null?'':won(row.cost))+dialogSelect('status','확정 여부',['미확정','확정','확인 완료','제외'],row.status||'미확정');}
  if(!listing&&!support)fields+=`<div class="field wide"><label class="checkbox-line variable-checkbox"><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="record-is_variable" name="is_variable" type="checkbox" ${row.is_variable?'checked':''}> 변동자산 · 보수적/공격적 금액을 따로 입력</label></div>${dialogInput('conservative_amount','보수적 예상액',row.conservative_amount??'')}${dialogInput('aggressive_amount','공격적 예상액',row.aggressive_amount??'')}<p class="field-help wide variable-explanation">예상 수령·매도액을 입력하세요. 등록한 비용은 계산에서 한 번 차감합니다. 0원도 입력할 수 있어요.</p>`;
  openModal(`${existing?'수정':'새로 추가'} · ${listing?'매물':support?'부모님 지원':'우리 자금'}`,`<form id="record-form" autocomplete="off"><div class="fields">${fields}</div>${!support&&!listing?`<label class="checkbox-line"><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" name="use_for_purchase" type="checkbox" ${row.use_for_purchase!==false?'checked':''}> 이 돈을 매수 계획에 사용해요</label>`:''}<p class="field-help">금액은 3600만, 1.2억처럼 입력해도 됩니다.${listing?'':' 날짜는 2027-03-14 또는 잔금일-1처럼 입력하세요.'}</p><div class="modal-error" role="alert"></div><div class="modal-actions"><button type="button" class="button" id="record-cancel">취소</button><button type="submit" class="button primary">반영하고 계산</button></div></form>`);
  $('#record-cancel').onclick=closeModal;
  if(support){
    const date=$('#record-date');
    date.closest('.field').insertAdjacentHTML('beforeend',`<div class="fund-timing-actions" role="group" aria-label="지원 입금일 연결"><button type="button" class="button small" data-support-timing="interim" aria-pressed="false">중도금일에 맞추기</button><button type="button" class="button small" data-support-timing="closing" aria-pressed="false">잔금일에 맞추기</button></div><small id="support-timing-hint" role="status"></small>`);
    const buttons=$$('[data-support-timing]');
    const updateTiming=()=>{
      const value=date.value.replace(/\s/g,'').replace(/^=/,''),interim=['중도금일','중도금지급일','interim_date'].includes(value),closing=['잔금일','closing_date'].includes(value);
      for(const button of buttons){const active=button.dataset.supportTiming==='interim'?interim:closing;button.setAttribute('aria-pressed',String(active));button.classList.toggle('selected',active);}
      $('#support-timing-hint').textContent=interim?(state.draft.settings.interim_date?'중도금일에 지원금을 받도록 연결했어요. 일정이 바뀌면 함께 반영됩니다.':'매수계획에서 중도금일을 입력해 주세요.'):closing?(state.draft.settings.closing_date?'잔금일에 지원금을 받도록 연결했어요. 일정이 바뀌면 함께 반영됩니다.':'매수계획에서 잔금일을 입력해 주세요.'):'일정에 연결하면 지원 입금일도 함께 바뀝니다.';
    };
    for(const button of buttons)button.onclick=()=>{closeCalendar();date.value=button.dataset.supportTiming==='interim'?'중도금일':'잔금일';date.setCustomValidity('');date.dispatchEvent(new Event('input',{bubbles:true}));date.dispatchEvent(new Event('change',{bubbles:true}));};
    date.addEventListener('input',updateTiming);date.addEventListener('change',updateTiming);updateTiming();
  }
  if(!listing&&!support){
    const type=$('#record-type'),date=$('#record-available_date'),variable=$('#record-is_variable');
    date.closest('.field').insertAdjacentHTML('beforeend',`<div class="fund-timing-actions" role="group" aria-label="자금 사용 시점"><button type="button" class="button small" data-fund-timing="lease" aria-pressed="false">전세보증금</button><button type="button" class="button small" data-fund-timing="interim" aria-pressed="false">중도금 사용</button><button type="button" class="button small" data-fund-timing="closing" aria-pressed="false" hidden>잔금일에 맞추기</button></div><small id="fund-timing-hint" role="status"></small>`);
    const timingButtons=$$('[data-fund-timing]'),timingHint=$('#fund-timing-hint');
    const updateTiming=()=>{
      const value=date.value.replace(/\s/g,'').replace(/^=/,''),blocked=type.value.includes('부채')||['기타 나갈 돈','가족 차입'].includes(type.value);
      const retirement=type.value==='퇴직 관련 수령금',lease=type.value==='전세보증금'&&['퇴거일','보증금반환일','lease_refund_date'].includes(value),interim=['중도금일','중도금지급일','interim_date'].includes(value),closing=['잔금일','closing_date'].includes(value);
      for(const button of timingButtons){const timing=button.dataset.fundTiming,active=!blocked&&(timing==='lease'?lease:timing==='interim'?interim:retirement&&closing);button.hidden=timing==='lease'?retirement:timing==='closing'?!retirement:false;if(timing==='interim')button.textContent=retirement?'중도금일에 맞추기':'중도금 사용';button.disabled=blocked;button.setAttribute('aria-pressed',String(active));button.classList.toggle('selected',active);}
      timingHint.textContent=blocked?'들어오는 자금에서 사용할 수 있어요.':interim?(state.draft.settings.interim_date?(retirement?'중도금일에 퇴직금을 받도록 연결했어요. 일정이 바뀌면 함께 반영됩니다.':'이 항목의 전액을 중도금일에 사용할 자금으로 계산해요.'):'매수계획에서 중도금일을 입력해 주세요.'):retirement&&closing?(state.draft.settings.closing_date?'잔금일에 퇴직금을 받도록 연결했어요. 일정이 바뀌면 함께 반영됩니다.':'매수계획에서 잔금일을 입력해 주세요.'):lease?'퇴거일에 보증금 전액을 받아요. 매수계획의 퇴거일·보증금 반환일을 따라갑니다.':'일정에 연결하면 날짜가 바뀔 때 함께 반영돼요.';
      if(retirement&&!['확정','확인 완료'].includes($('#record-status').value))timingHint.textContent+=' 퇴직금은 확정·확인 완료로 설정해야 계산에 반영돼요.';
    };
    const adjustFields=()=>{
      const investment=type.value==='투자자산';
      variable.disabled=type.value.includes('부채')||['기타 나갈 돈','가족 차입'].includes(type.value);
      if(variable.disabled)variable.checked=false;
      const ranged=variable.checked;
      $('#record-value').closest('.field').hidden=ranged;
      $('#record-value').disabled=ranged;
      $('#record-cash_out_amount').closest('.field').hidden=ranged||(!investment&&!row.cash_out_amount);
      $('#record-cash_out_amount').disabled=ranged;
      $('#record-cost').closest('.field').hidden=!investment&&!type.value.includes('부채')&&!row.cost;
      for(const key of ['conservative_amount','aggressive_amount']){const input=$(`#record-${key}`);input.closest('.field').hidden=!ranged;input.required=ranged;input.disabled=!ranged;}
      $('.variable-explanation').hidden=!ranged;
      $('label[for="record-value"]').textContent=investment?'현재 평가액':'금액';
      const future=!['현금·예금','투자자산','적금·청년도약계좌'].includes(type.value);
      if(future&&date.value==='지금'&&!row.available_date&&!date.dataset.nowSelected)date.value='';
      date.placeholder=future?'2027-03-14 또는 잔금일-1':'지금 또는 사용할 수 있는 날짜';
      date.required=future;
      updateTiming();
    };
    for(const button of timingButtons)button.onclick=()=>{
      closeCalendar();
      if(button.dataset.fundTiming==='lease'){type.value='전세보증금';date.value='퇴거일';}else date.value=button.dataset.fundTiming==='closing'?'잔금일':'중도금일';
      date.setCustomValidity('');delete date.dataset.nowSelected;
      $('[name="use_for_purchase"]').checked=true;
      adjustFields();
      date.dispatchEvent(new Event('input',{bubbles:true}));date.dispatchEvent(new Event('change',{bubbles:true}));
    };
    date.addEventListener('input',updateTiming);date.addEventListener('change',updateTiming);
    $('#record-status').addEventListener('change',updateTiming);
    variable.onchange=()=>{if(variable.checked){let current=null;try{current=readMoneyInput($('#record-cash_out_amount'))??readMoneyInput($('#record-value'));}catch{}for(const key of ['conservative_amount','aggressive_amount'])if(!$(`#record-${key}`).value)normalizeMoneyInput($(`#record-${key}`),current);}adjustFields();};
    type.onchange=adjustFields;adjustFields();
  }
  $('#record-form').onsubmit=async event=>{event.preventDefault();const submit=event.submitter||$('#record-form [type="submit"]');if(submit.disabled)return;submit.disabled=true;try{const data=new FormData(event.currentTarget);const updated={...row,origin:'app'};for(const [key,value]of data){if(moneyNames.has(key)){updated[key]=readMoneyInput($(`#record-${key}`));}else if(key==='area_m2'){updated[key]=Number(value);if(!(updated[key]>0))throw new Error('전용면적을 확인해 주세요.');}else updated[key]=value;}
    if(!listing&&!support){updated.use_for_purchase=data.has('use_for_purchase');updated.is_variable=data.has('is_variable');if(updated.is_variable){if(updated.conservative_amount==null||updated.aggressive_amount==null)throw new Error('보수적·공격적 금액을 모두 입력해 주세요.');if(updated.conservative_amount>updated.aggressive_amount)throw new Error('보수적 금액은 공격적 금액 이하여야 합니다.');}}
    if(!listing&&!support&&!updated.name.trim())throw new Error('자금 이름을 입력해 주세요.');
    const timing=String((support?updated.date:updated.available_date)||'').replace(/\s/g,'').replace(/^=/,'');
    if(!listing&&['중도금일','중도금지급일','interim_date'].includes(timing)&&!state.draft.settings.interim_date)throw new Error('매수계획에서 중도금일을 먼저 입력해 주세요.');
    if(!listing&&['잔금일','closing_date'].includes(timing)&&!state.draft.settings.closing_date)throw new Error('매수계획에서 잔금일을 먼저 입력해 주세요.');
    if((updated.value===null&&!updated.is_variable)||updated.amount===null||updated.price===null)throw new Error('금액을 입력해 주세요.');
    if(!listing&&!support){
      if(!existing){updated.id=nextId(rows,'A');updated.data_kind='실제';}
      const candidate=clone(state.draft);
      if(existing)candidate.fund_events=candidate.fund_events.map(r=>r.id===id?updated:r);else candidate.fund_events.push(updated);
      await upgrades.applyCandidate(candidate);closeModal();toast('자금을 반영했습니다. 계산 결과를 확인한 뒤 변경사항을 저장해 주세요.');return;
    }
    if(!existing){updated.id=nextId(rows,listing?'APT':'P');rows.push(updated);}else rows[rows.indexOf(existing)]=updated;
    if(listing)state.draft.selected_listing=updated.id;
    closeModal();state.max=null;render();calculate();toast('변경을 반영했습니다. 계산 결과를 확인한 뒤 저장해 주세요.');
  }catch(error){$('.modal-error').textContent=error.message;}finally{if(submit.isConnected)submit.disabled=false;}};
  if(!listing&&!support&&!existing)installFundBuilder({form:$('#record-form'),preset:!!preset,mode:variableMode(),shortMoney,won});
}
async function deleteFund(id) {
  if(state.saving){toast('저장이 끝난 뒤 다시 시도해 주세요.');return;}
  const row=state.draft.fund_events.find(item=>item.id===id),workspace=state.workspace;
  if(!row)return;
  const yes=await confirmation('이 자금 항목을 삭제할까요?',`<p class="preview-summary"><strong>${esc(row.name)}</strong><br>이 항목을 자금 목록에서 지우고 다시 계산합니다.</p><p class="preview-summary">변경사항을 저장해야 삭제가 보관됩니다. 저장 전 버전은 기록에서 복원할 수 있어요.</p>`,'삭제',{focusConfirm:true});
  if(!yes||state.workspace!==workspace)return;
  const index=state.draft.fund_events.indexOf(row);if(index<0)return;
  state.draft.fund_events.splice(index,1);
  state.max=null;render();await calculate();
  toast('자금 항목을 삭제했습니다. 변경사항 저장을 눌러 보관하세요.');
}
async function deleteSupport(index) {
  if(state.saving){toast('저장이 끝난 뒤 다시 시도해 주세요.');return;}
  const row=state.draft.parent_support[index],workspace=state.workspace;
  if(!row)return;
  const yes=await confirmation('이 지원 항목을 삭제할까요?',`<p class="preview-summary"><strong>부모님 ${esc(row.kind)} · ${esc(row.to)}</strong><br>${won(row.amount)}원 · ${esc(row.date||'날짜 미입력')}<br>이 항목을 지원 일정에서 지우고 다시 계산합니다.</p><p class="preview-summary">변경사항을 저장해야 삭제가 보관됩니다. 저장 전 버전은 기록에서 복원할 수 있어요.</p>`,'삭제',{focusConfirm:true});
  if(!yes||state.workspace!==workspace)return;
  const current=state.draft.parent_support.indexOf(row);if(current<0)return;
  state.draft.parent_support.splice(current,1);
  state.max=null;render();await calculate();
  toast('지원 항목을 삭제했습니다. 변경사항 저장을 눌러 보관하세요.');
}
async function deleteListing() {
  if(state.draft.listings.length<=1){toast('계산할 매물이 하나 필요합니다. 새 매물을 추가한 뒤 삭제해 주세요.');return;}
  const item=selected(),workspace=state.workspace,index=state.draft.listings.findIndex(row=>row.id===item.id);
  const remaining=state.draft.listings.filter(row=>row.id!==item.id),next=remaining[Math.min(index,remaining.length-1)];
  const yes=await confirmation('이 매물을 삭제할까요?',`<p class="preview-summary"><strong>${esc(item.name)}</strong> · ${esc(shortMoney(item.price))}<br>삭제 후 <strong>${esc(next.name)}</strong> 매물로 전환해 계산합니다.</p><p class="preview-summary">변경사항을 저장해야 삭제가 보관됩니다. 저장 전 버전은 기록에서 복원할 수 있어요.</p>`,'매물 삭제',{focusConfirm:true});
  if(!yes||state.workspace!==workspace)return;
  const currentIndex=state.draft.listings.findIndex(row=>row.id===item.id);
  if(currentIndex<0||state.draft.listings.length<=1)return;
  state.draft.listings.splice(currentIndex,1);
  state.draft.selected_listing=state.draft.listings[Math.min(currentIndex,state.draft.listings.length-1)].id;
  state.max=null;render();await calculate();
  toast('매물을 삭제했습니다. 변경사항 저장을 눌러 보관하세요.');
}
async function saveDraft() {
  if(!validInputs())return;
  if(!dirty()||state.saving)return;
  state.saving=true;updateSavedState();const candidate=clone(state.draft),workspace=state.workspace,revision=state.revision;
  try{const preview=await post(`/api/workspaces/${workspace}/preview`,{household:candidate,revision});
    const summary=preview.changes.map(change=>change.kind==='setting'?`${settingLabels[change.key]||'설정'} 변경`:`${change.label||change.key} ${change.after==null?'삭제':change.before==null?'추가':'수정'}`);
    const yes=await confirmation('변경사항을 저장할까요?',`<p class="preview-summary">자금에 미치는 영향을 확인해 주세요.<br>저장 전 버전은 기록에 남아 다시 복원할 수 있어요.</p><div class="preview-stats"><div class="preview-stat">잔금일 가용자금<strong>${shortMoney(preview.before.closing_cash_available)} → ${shortMoney(preview.after.closing_cash_available)}</strong></div><div class="preview-stat">일별 최저 잔고<strong>${shortMoney(preview.before.min_balance_overall)} → ${shortMoney(preview.after.min_balance_overall)}</strong></div></div><p class="preview-summary">${esc(preview.before.status)} → <b>${esc(preview.after.status)}</b></p><ul class="preview-changes">${summary.map(text=>`<li>${esc(text)}</li>`).join('')}</ul>`,'확인하고 저장');
    if(!yes)return;const saved=await post(`/api/workspaces/${workspace}`,{household:candidate,revision},'PUT');state.base=clone(saved.household);state.draft=clone(saved.household);state.revision=saved.revision;upgrades?.clearDraft();render();calculate();toast('이 컴퓨터에 저장했습니다. 이전 버전도 보관했어요.');
  }catch(error){toast(error.message,true);}finally{state.saving=false;updateSavedState();}
}
async function switchWorkspace(id) {
  if(id===state.workspace)return;
  if(dirty()&&!await confirmation('데이터를 전환할까요?','<p class="preview-summary">저장하지 않은 변경사항은 사라집니다. 현재 변경사항을 보관하려면 취소 후 저장해 주세요.</p>','저장 없이 전환'))return;
  upgrades?.flushDraft();inputProblems.clear();state.sequence++;state.result=null;state.max=null;state.confirmed=false;state.cashDate=null;
  const loaded=await api(`/api/workspaces/${id}`);state.workspace=id;try{localStorage.setItem(`homeplan-last-workspace:${location.origin}`,id);}catch{}state.base=clone(loaded.household);state.draft=clone(loaded.household);state.revision=loaded.revision;render();await calculate();await upgrades?.offerRecovery();
}
async function showHistory() {
  try{const rows=await api(`/api/workspaces/${state.workspace}/history`);openModal('저장 기록',`<p class="preview-summary">이전 버전을 복원해도 현재 저장 기록은 유지됩니다.</p>${rows.map(row=>`<div class="history-row"><div>${row.revision===state.revision?'현재 저장된 계획':`저장 기록 ${row.revision}`}<small>${esc(row.saved_at.replace('T',' ').slice(0,19))}</small>${row.changes?.length?`<details class="history-changes"><summary>변경 ${row.changes.length}개</summary><ul>${row.changes.map(change=>`<li>${esc(change.label||settingLabels[change.key]||change.key)} · ${esc(typeof change.before==='object'?(change.before==null?'새 항목':JSON.stringify(change.before)):String(change.before??'없음'))} → ${esc(typeof change.after==='object'?(change.after==null?'삭제':JSON.stringify(change.after)):String(change.after??'없음'))}</li>`).join('')}</ul></details>`:''}</div>${row.revision===state.revision?'<span class="status-pill">현재</span>':`<button class="button small" data-restore="${row.revision}">이 버전 복원</button>`}</div>`).join('')}`);$$('[data-restore]',$('#modal')).forEach(button=>button.onclick=async()=>{const target=Number(button.dataset.restore);closeModal();if(await confirmation('이전 버전을 복원할까요?','<p class="preview-summary">저장하지 않은 변경사항은 사라집니다. 현재 저장된 버전은 기록에 유지됩니다.</p>','복원')){try{const loaded=await post(`/api/workspaces/${state.workspace}/restore`,{revision:state.revision,target_revision:target});state.base=clone(loaded.household);state.draft=clone(loaded.household);state.revision=loaded.revision;state.max=null;render();calculate();toast('선택한 버전을 복원했습니다.');}catch(error){toast(error.message,true);}}});}catch(error){toast(error.message,true);}
}
installInputControls();
$('#content').addEventListener('change',onFieldChange);
document.addEventListener('click',event=>{
  const button=event.target.closest('[data-action]');if(!button)return;const action=button.dataset.action,id=button.dataset.id;
  if(action==='save')saveDraft();
  else if(action==='price-correct'){
    if(state.saving){toast('저장이 끝난 뒤 다시 시도해 주세요.');return;}
    const item=selected(),price=Number(button.dataset.price);
    if(item.id!==button.dataset.listing||price!==Number(item.price)*10000||!(price>=1e8&&price<=1e10))return;
    item.price=price;item.origin='app';state.max=null;render();
    const unit=$('[data-unit-for="field-price"]');unit.value=String(1e8);unit.dispatchEvent(new Event('change',{bubbles:true}));
    calculate();
    toast(`매수가를 ${formatMoney(price,1e8)}억원으로 수정했습니다. 계산 결과를 확인한 뒤 저장해 주세요.`);
  }
  else if(action==='listing-add')editRecord('listing');else if(action==='listing-edit')editRecord('listing',selected().id);else if(action==='listing-delete')deleteListing();
  else if(action==='fund-add')editRecord('fund');else if(action==='fund-edit')editRecord('fund',id);else if(action==='fund-delete')deleteFund(id);
  else if(action==='variable-preset')variablePreset(button.dataset.preset);
  else if(action==='support-add')editRecord('support');else if(action==='support-edit')editRecord('support',id);else if(action==='support-delete')deleteSupport(Number(id));
  else if(action==='expense-add')editExpense();else if(action==='expense-edit')editExpense(id);else if(action==='expense-delete')deleteExpense(id);
  else if(action==='expense-after')editExpense(null,'after');
  else if(action==='expense-childcare'){const row=expenseRows().find(item=>item.category==='양육비');editExpense(row?.id||null,'childcare');}
  else if(action==='expense-apply')commitExpensePlan(expenseRows()).then(()=>toast('기간별 지출을 적용했습니다. 확인 후 변경사항을 저장해 주세요.')).catch(error=>toast(error.message,true));
  else if(action==='expense-toggle'){const rows=clone(expenseRows()),row=rows.find(item=>item.id===id);if(row){row.enabled=!row.enabled;commitExpensePlan(rows).catch(error=>toast(error.message,true));}}
  else if(action.endsWith('-toggle')){const row=action.startsWith('fund')?state.draft.fund_events.find(row=>row.id===id):state.draft.parent_support[Number(id)];row.status=row.status==='제외'?'미확정':'제외';row.origin='app';state.max=null;render();calculate();}
});
$('#workspace-switch').onclick=event=>{const button=event.target.closest('[data-workspace]');if(button)switchWorkspace(button.dataset.workspace).catch(error=>toast(error.message,true));};
$('#toolbar-calculate').onclick=()=>calculate();$('#save-button').onclick=saveDraft;$('#history-button').onclick=showHistory;$('#modal-close').onclick=closeModal;
$('#export-button').onclick=async()=>{try{const response=await fetch(`/api/workspaces/${state.workspace}/export`);if(!response.ok)throw new Error('내보내기에 실패했습니다.');const url=URL.createObjectURL(await response.blob());const a=document.createElement('a');a.href=url;a.download=`homeplan-${state.workspace}.local.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){toast(error.message,true);}};
window.addEventListener('hashchange',()=>{const route=location.hash.slice(1);if(pages[route]&&state.draft){state.route=route;render();}});
window.addEventListener('beforeunload',event=>{upgrades?.flushDraft();if(state.draft&&dirty()){event.preventDefault();event.returnValue='';}});
async function boot(){state.workspaces=await api('/api/workspaces');let previous;try{previous=localStorage.getItem(`homeplan-last-workspace:${location.origin}`);}catch{}const initial=state.workspaces.some(w=>w.id===previous)?previous:state.workspaces.some(w=>w.id==='actual')?'actual':state.workspaces[0].id;const route=location.hash.slice(1);if(pages[route])state.route=route;await switchWorkspace(initial);if(state.draft.onboarding_pending)await upgrades.startOnboarding();}
if(!globalThis.HOMEPLAN_BROWSER){const heartbeat=()=>fetch('/api/heartbeat',{method:'POST'}).catch(()=>{});heartbeat();setInterval(heartbeat,20000);document.addEventListener('visibilitychange',heartbeat);}
upgrades=createUpgradeTools({state,inputProblems,$,$$,esc,won,shortMoney,clone,api,post,toast,render,calculate,validInputs,openModal,closeModal,confirmation,field,selectField,checkField,dialogInput,dialogSelect,readMoneyInput,commitExpensePlan,expenseRows,switchWorkspace,settingLabels});
menus=createPlanningMenus({state,$,$$,esc,won,shortMoney,clone,toast,field,checkField,openModal,closeModal,confirmation,render,calculate,upgrades:()=>upgrades});
purchase=createPurchaseTracking({state,$,$$,esc,won,shortMoney,clone,openModal,closeModal,confirmation,toast,render,calculate,upgrades:()=>upgrades});
boot().then(()=>{window.homeplanStartup?.done();installUpdateNotice({canReload:()=>!dirty()&&!state.saving&&!state.evaluating&&!$('#modal').open,beforeReload:()=>upgrades?.flushDraft()});}).catch(error=>{if(window.homeplanStartup)window.homeplanStartup.fail(error.message);else $('#content').innerHTML=`<section class="card empty">계획을 불러오지 못했습니다.<br>${esc(error.message)}<br>창을 닫고 바탕화면 바로가기를 다시 실행해 주세요.</section>`;});
