import {moneyControl,dateControl,readMoneyInput,moneyWords} from './form-inputs.mjs?v=bbb1f0d1db400a0c';

const advancedLabels={asset_base_date:'보유 자금 기준일',deposit_ratio:'계약금 비율',same_day_inflow_usable:'당일 입금을 당일 지출에 사용',permit_date:'토지거래 허가일',land_permit_required:'토지거래허가 대상',tenant_deferral_confirmed:'실거주 유예 확인',ownership:'소유 형태',husband_share:'남편 소유 지분',first_home_tax_relief:'생애최초 취득세 감면 적용',manual_tax_rate:'직접 입력 취득세율',mortgage_borrower:'주담대 차주',mortgage_cap:'주담대 사용자 상한',mortgage_mode:'주담대 금액 결정 방식',mortgage_rate_type:'주담대 금리 유형',mortgage_reset_after_months:'주담대 금리 재설정 · 개월 후',mortgage_reset_rate:'재설정 금리',first_interest_adjustment:'첫 이자 조정액 · 원',mortgage_round_unit:'대출 역산 단위 · 원',equal_principal_dsr_basis:'원금균등 DSR 기준',dsr_limit:'DSR 한도',existing_debt_annual:'기타 대출 연간 상환액',credit_repay_date:'신용대출 전액 상환일',sub_repay_date:'청약담보 전액 상환일',sub_principal_husband:'남편 청약통장 원금',sub_principal_wife:'아내 청약통장 원금',sub_ratio:'청약담보 대출 비율',sub_savings_rate:'청약 저축 금리',sub_spread:'청약담보 가산 금리',lease_end_date:'전세 만기',maternity_start:'출산휴가 시작일',maternity_months:'출산휴가 개월',maternity_pay_m12:'출산휴가 첫 두 달 월 급여',maternity_pay_m3:'출산휴가 세 번째 달 급여',wife_leave_start:'아내 육아휴직 시작일',wife_leave_months:'아내 육아휴직 개월',return_delay_months:'복직 추가 지연 개월',wife_gov_benefit_months:'아내 휴직급여 지급 개월',wife_ordinary_wage:'아내 통상임금',wife_company_topup:'아내 회사 월 보전액',wife_company_topup_months:'아내 회사 보전 개월',benefit_pay_delay_months:'휴직급여 지급 지연 개월',husband_leave_use:'남편 육아휴직 사용',husband_leave_start:'남편 육아휴직 시작일',husband_leave_months:'남편 육아휴직 개월',husband_ordinary_wage:'남편 통상임금',husband_gov_benefit_months:'남편 휴직급여 지급 개월',husband_company_topup:'남편 회사 월 보전액',husband_company_topup_months:'남편 회사 보전 개월',parents_6p6:'부모 함께 육아휴직 6+6 적용',lawyer_fee:'법무 비용',registry_fee:'등기 비용',official_price_ratio:'공시가 추정 비율',bond_buy_rate:'채권 매입 비율',bond_discount_rate:'채권 할인 비율',loan_stamp_share:'대출 인지세 부담 비율',brokerage_rate:'중개보수 직접 비율',repair_default:'기본 수리비',appliances:'가전·가구 비용',moving:'이사 비용',cleaning:'청소 비용',temp_housing:'임시 거처 비용',comparison_area_m2:'비교 주택 전용면적',mgmt_fee_default:'기본 관리비',property_tax_month1:'보유세 첫 납부월',property_tax_month2:'보유세 두 번째 납부월',lease_interest_in_living:'기존 생활비에 전세이자 포함',mgmt_in_living:'기존 생활비에 관리비 포함',living_cost:'기존 생활비',fixed_cost:'기존 고정비',childcare_cost:'기존 양육비'};
const integerKeys=new Set(['payday','expense_day','annual_cost_month','property_tax_month1','property_tax_month2','mortgage_years','mortgage_reset_after_months','mortgage_round_unit','first_interest_adjustment','card_months','card_paid_installments','card_first_offset','maternity_months','wife_leave_months','return_delay_months','wife_gov_benefit_months','wife_company_topup_months','benefit_pay_delay_months','husband_leave_months','husband_gov_benefit_months','husband_company_topup_months','comparison_area_m2']);
const ratioKeys=new Set(['deposit_ratio','mortgage_rate','mortgage_reset_rate','ltv','dsr_limit','stress_rate','credit_rate','sub_ratio','sub_savings_rate','sub_spread','family_loan_rate','husband_share','manual_tax_rate','card_fee_rate','official_price_ratio','bond_buy_rate','bond_discount_rate','loan_stamp_share','brokerage_rate','lease_loan_rate']);
const loanNames={mortgage:'주택담보대출',credit:'신용대출',sub:'청약담보대출'};

export function createUpgradeTools(c){
  const {state,inputProblems,$,$$,esc,won,shortMoney,clone,api,post,toast,render,calculate,validInputs,openModal,closeModal,confirmation,field,selectField,checkField,commitExpensePlan,expenseRows,switchWorkspace,settingLabels}=c;
  Object.assign(settingLabels,advancedLabels,{start_today:'오늘부터 계산',credit_amount_mode:'신용대출 금액 결정',sub_amount_mode:'청약담보 금액 결정'});
  const offered=new Set(),groups=new Map();let draftTimer,templateCache,lastToday;
  const draftKey=()=>`homeplan-draft:${location.origin}:${state.workspace}`;
  const draftDirty=()=>JSON.stringify(state.draft)!==JSON.stringify(state.base)||inputProblems.size>0;
  const formField=(key,label,value='',kind='text')=>`<div class="field"><label for="upgrade-${key}">${esc(label)}</label>${kind==='money'?moneyControl(`upgrade-${key}`,label,value):kind==='date'?dateControl(`upgrade-${key}`,label,value):`<input autocomplete="off" id="upgrade-${key}" type="${kind}" value="${esc(value)}">`}</div>`;
  const value=key=>$(`#upgrade-${key}`).value;
  const money=key=>{const result=readMoneyInput($(`#upgrade-${key}`));if(result==null)throw new Error('금액을 입력해 주세요.');return result;};
  function modalError(error){const target=$('#upgrade-error');if(target)target.textContent=error.message;else toast(error.message,true);}
  const actions=(submit='반영하고 계산')=>`<div id="upgrade-error" class="modal-error" role="alert"></div><div class="modal-actions"><button type="button" class="button" data-upgrade="close">취소</button><button class="button primary" type="submit">${submit}</button></div>`;
  async function candidateResult(candidate){return post('/api/evaluate',{household:candidate,listing_id:candidate.selected_listing||candidate.listings[0].id,confirmed_only:state.confirmed});}
  async function applyCandidate(candidate){
    if(!validInputs())throw new Error('입력 오류를 먼저 수정해 주세요.');
    const snapshot=JSON.stringify(state.draft),workspace=state.workspace,result=await candidateResult(candidate);
    if(workspace!==state.workspace||snapshot!==JSON.stringify(state.draft))throw new Error('입력이 바뀌었습니다. 다시 적용해 주세요.');
    state.sequence++;state.draft=candidate;state.result=result;state.calculatedSnapshot=JSON.stringify(candidate);state.max=null;state.evaluating=false;
    scheduleDraft();render();return result;
  }
  async function refreshWorkspaces(){state.workspaces=await api('/api/workspaces');}
  async function applySaved(saved){inputProblems.clear();clearDraft();state.base=clone(saved.household);state.draft=clone(saved.household);state.revision=saved.revision;state.result=null;render();await calculate();}
  function scheduleDraft(){
    clearTimeout(draftTimer);draftTimer=setTimeout(()=>{
      if(!state.workspace||!draftDirty())return;
      try{localStorage.setItem(draftKey(),JSON.stringify({revision:state.revision,household:state.draft,problems:[...inputProblems],savedAt:new Date().toISOString()}));}catch{toast('임시 초안을 보관할 공간이 부족합니다. 계획을 저장해 주세요.',true);}
    },300);
  }
  function flushDraft(){
    clearTimeout(draftTimer);if(!state.workspace||!draftDirty())return;
    try{localStorage.setItem(draftKey(),JSON.stringify({revision:state.revision,household:state.draft,problems:[...inputProblems],savedAt:new Date().toISOString()}));}catch{toast('임시 초안 저장에 실패했습니다. 변경사항을 저장해 주세요.',true);}
  }
  function clearDraft(){clearTimeout(draftTimer);if(state.workspace)localStorage.removeItem(draftKey());}
  async function offerRecovery(){
    if(!state.workspace||offered.has(state.workspace))return;offered.add(state.workspace);
    let stored;try{stored=JSON.parse(localStorage.getItem(draftKey())||'null');}catch{return;}
    if(!stored||(JSON.stringify(stored.household)===JSON.stringify(state.base)&&!stored.problems?.length))return;
    const conflict=stored.revision!==state.revision;
    const yes=await confirmation('임시 초안을 복구할까요?',`<p>${esc(stored.savedAt?.replace('T',' ').slice(0,16)||'')}에 보관한 미저장 초안입니다.</p><p>${conflict?'저장본이 바뀌었습니다. 초안을 새 계획으로 복사해 확인할 수 있어요.':'이 창에서 이어서 편집할 수 있어요.'}</p>`,conflict?'새 계획으로 복구':'초안 복구');
    if(!yes){clearDraft();return;}
    if(conflict){const saved=await post('/api/workspaces',{label:'복구한 초안',household:stored.household});await refreshWorkspaces();await switchWorkspace(saved.id);for(const [key,problem] of stored.problems||[])inputProblems.set(key,problem);render();scheduleDraft();return;}
    state.draft=stored.household;for(const [key,problem] of stored.problems||[])inputProblems.set(key,problem);render();if(!inputProblems.size)await calculate();
  }
  async function copyPlan(){
    if(!validInputs())return;
    openModal('현재 입력을 새 계획으로 복사',`<form id="upgrade-copy">${formField('label','계획 이름','비교할 계획')}${actions('복사해 저장')}</form>`);
    $('#upgrade-copy').onsubmit=async e=>{e.preventDefault();try{if(!value('label').trim())throw new Error('계획 이름을 입력하세요.');const saved=await post('/api/workspaces',{label:value('label').trim(),household:clone(state.draft)});closeModal();await refreshWorkspaces();await switchWorkspace(saved.id);}catch(error){modalError(error);}};
  }
  async function newPlan(){
    const blueprint=await api('/api/new-plan');templateCache=blueprint;
    let step=0,costPreview=null;const candidate=clone(blueprint.household),values={label:'우리의 새 계획',people:'두 사람',cash:0,living:0,lease:0,debt:0,husband:0,wife:0};
    const readCosts=()=>{
      for(const key of ['lawyer_fee','registry_fee','appliances','moving','cleaning','temp_housing'])candidate.settings[key]=money(key);
      candidate.listings[0].repair=money('repair');
      candidate.listings[0].acquisition_tax_amount=readMoneyInput($('#upgrade-tax'));
      candidate.listings[0].brokerage_amount=readMoneyInput($('#upgrade-broker'));
    };
    const draw=()=>{
      let rows;
      if(step===0)rows=`${formField('label','계획 이름',values.label)}<div class="field"><label for="upgrade-people">소득을 함께 계획할 사람</label><select id="upgrade-people"><option ${values.people==='두 사람'?'selected':''}>두 사람</option><option ${values.people==='혼자'?'selected':''}>혼자</option></select></div><p class="hint">계산은 매일 오늘부터 시작합니다. 보유 현금은 오늘의 실제 잔액을 입력하세요.</p>`;
      else if(step===1)rows=`${formField('cash','현재 보유 현금',values.cash,'money')}${formField('husband',values.people==='혼자'?'내 월 실수령':'첫 번째 사람 월 실수령',values.husband,'money')}${values.people==='혼자'?'':formField('wife','두 번째 사람 월 실수령',values.wife,'money')}${formField('living','매달 생활비',values.living,'money')}${formField('lease','돌려받을 전세보증금',values.lease,'money')}${formField('debt','갚아야 할 전세대출',values.debt,'money')}`;
      else if(step===2)rows=`${formField('price','검토할 집 가격',candidate.listings[0].price,'money')}${formField('area','전용면적 · ㎡',candidate.listings[0].area_m2,'number')}${formField('contract','계약일',candidate.settings.contract_date,'date')}${formField('closing','잔금일',candidate.settings.closing_date,'date')}${formField('move','입주일',candidate.settings.move_in_date,'date')}<p class="hint">다음 단계에서 세금·법무·입주 비용을 검토합니다. 대출·중도금·휴직은 계획을 만든 뒤 설정할 수 있습니다.</p>`;
      else rows=`<p class="hint wide">취득세 등 예상 합계 ${shortMoney(costPreview?.costs.acquisition_taxes_total||0)} · 중개보수 ${shortMoney(costPreview?.costs.brokerage||0)}. 매수가와 등록된 계산 기준에 따른 예상값입니다.</p>${formField('tax','취득세 등 최종 총액 · 빈칸은 자동',candidate.listings[0].acquisition_tax_amount??'','money')}${formField('broker','협의한 중개보수 · 빈칸은 자동',candidate.listings[0].brokerage_amount??'','money')}${formField('lawyer_fee','법무사 보수',candidate.settings.lawyer_fee,'money')}${formField('registry_fee','등기 비용',candidate.settings.registry_fee,'money')}${formField('repair','수리비',candidate.listings[0].repair??candidate.settings.repair_default,'money')}${formField('appliances','가전·가구',candidate.settings.appliances,'money')}${formField('moving','이사비',candidate.settings.moving,'money')}${formField('cleaning','입주 청소비',candidate.settings.cleaning,'money')}${formField('temp_housing','임시 거주비',candidate.settings.temp_housing,'money')}<p class="hint wide">직접 세금은 교육세·농특세·감면까지 반영한 최종 합계입니다. 법무사 견적에 포함된 세금·등기 비용을 다시 합산하지 마세요. 저장 후 매수 비용 화면에서 상세 내역과 납부 방식을 조정할 수 있어요.</p><p class="hint wide">최근 미리보기 · 집값 외 비용 ${shortMoney((costPreview?.costs.closing_costs_total||0)+(costPreview?.costs.move_in_costs||0))}</p><button type="button" class="button" id="upgrade-cost-preview">비용 미리보기</button>`;
      openModal(`새 계획 만들기 · ${step+1}/4`,`<form id="upgrade-new"><div class="fields">${rows}</div><div id="upgrade-error" class="modal-error" role="alert"></div><div class="modal-actions">${step?'<button type="button" class="button" id="upgrade-back">이전</button>':''}<button type="submit" class="button primary">${step===3?'새 계획 저장':'다음'}</button></div></form>`);
      $('#upgrade-back')?.addEventListener('click',()=>{try{if(step===3)readCosts();step--;draw();}catch(error){modalError(error);}});
      $('#upgrade-cost-preview')?.addEventListener('click',async()=>{try{readCosts();costPreview=await candidateResult(candidate);draw();}catch(error){modalError(error);}});
      $('#upgrade-new').onsubmit=async e=>{e.preventDefault();try{
        if(step===0){values.label=value('label').trim();values.people=value('people');if(!values.label)throw new Error('계획 이름을 입력하세요.');step++;draw();return;}
        if(step===1){for(const key of ['cash','husband','living','lease','debt'])values[key]=money(key);values.wife=values.people==='혼자'?0:money('wife');step++;draw();return;}
        if(step===2){
          candidate.settings.husband_net_pay=values.husband;candidate.settings.wife_net_pay=values.wife;
          candidate.settings.contract_date=value('contract');candidate.settings.closing_date=value('closing');candidate.settings.move_in_date=value('move');candidate.settings.interim_date=null;
          candidate.listings[0].price=money('price');candidate.listings[0].area_m2=Number(value('area'));
          if(candidate.listings[0].price<=0)throw new Error('집 가격을 0원보다 크게 입력하세요.');
          candidate.fund_events=[{id:'CASH',name:'현재 보유 현금',type:'현금·예금',value:values.cash,status:'확정'}];
          if(values.lease)candidate.fund_events.push({id:'LEASE',name:'전세보증금 반환',type:'전세보증금',value:values.lease,available_date:'퇴거일',status:'미확정'});
          if(values.debt)candidate.fund_events.push({id:'DEBT',name:'전세대출 상환',type:'기존 전세대출(부채)',value:values.debt,available_date:'전세대출상환일',status:'확인 완료'});
          candidate.expense_items=[{id:'E01',name:'생활비',category:'생활비',amount:values.living,start_date:'기준일'}];
          costPreview=await candidateResult(candidate);step++;draw();return;
        }
        readCosts();await candidateResult(candidate);
        const saved=await post('/api/workspaces',{label:values.label,household:candidate});closeModal();state.route='costs';location.hash='costs';await refreshWorkspaces();await switchWorkspace(saved.id);toast('새 계획을 만들었습니다. 매수 비용과 납부 방식을 확인하세요.');
      }catch(error){modalError(error);}};
    };draw();
  }
  async function compare(){
    await refreshWorkspaces();
    openModal('저장된 계획 비교',`<form id="upgrade-compare"><p class="hint">최대 5개를 선택하세요. 저장된 입력으로 같은 오늘 날짜에 계산합니다.</p>${state.workspaces.map(row=>`<label class="checkbox-line"><input type="checkbox" name="compare-plan" value="${esc(row.id)}" ${row.id===state.workspace?'checked':''}>${esc(row.label)}</label>`).join('')}${actions('비교')}</form>`);
    $('#upgrade-compare').onsubmit=async e=>{e.preventDefault();try{
      const keys=$$('input[name="compare-plan"]:checked').map(i=>i.value);if(!keys.length||keys.length>5)throw new Error('1~5개 계획을 선택하세요.');
      const rows=await post('/api/compare',{keys});
      const metrics=[['최저 현금','min_balance_overall'],['잔금 부족액','closing_shortfall'],['월 최대 지출','max_monthly_spend'],['주담대 원금','mortgage_amount'],['신용대출 원금','credit_loan_amount']];
      openModal('계획 비교 결과',`<div class="table-wrap"><table><thead><tr><th>항목</th>${rows.map(r=>`<th>${esc(r.label)}</th>`).join('')}</tr></thead><tbody><tr><td>판정</td>${rows.map(r=>`<td>${esc(r.error||r.status)}</td>`).join('')}</tr>${metrics.map(([label,key])=>`<tr><td>${label}</td>${rows.map(r=>`<td>${r.kpis?shortMoney(r.kpis[key]):'계산 확인 필요'}</td>`).join('')}</tr>`).join('')}<tr><td>미확정 전제</td>${rows.map(r=>`<td>${r.assumptions?.length??'—'}개</td>`).join('')}</tr><tr><td>기준안에 적용</td>${rows.map(r=>`<td>${r.id===state.workspace?'현재 계획':`<button class="row-action" data-upgrade="apply-scenario" data-id="${esc(r.id)}">이 입력 사용</button>`}</td>`).join('')}</tr></tbody></table></div><p class="hint">서로 다른 매수 일정·자산 기준일의 계획은 조건을 함께 비교하세요. 주택을 제외한 현금·부채 계산입니다.</p>`);
    }catch(error){modalError(error);}};
  }
  async function backupDialog(){
    const data=await api('/api/backups');
    openModal('백업과 계획 복구',`<form id="upgrade-backup">${globalThis.HOMEPLAN_BROWSER?'<p class="hint">백업은 이 브라우저 안에 보관됩니다. 기기 밖 보관은 상단의 입력값 내보내기를 사용하세요.</p>':formField('directory','백업 저장 폴더',data.directory)}${actions('현재 DB 백업')}</form><h3>독립 백업에서 현재 계획 복구</h3><p class="hint">자동 백업은 하루 첫 실행·저장 때 만들어집니다. 복구 전에 현재 상태도 별도 백업합니다.</p><div class="backup-list">${data.files.map(f=>`<div class="history-row"><span>${esc(f.name)}<small>${Math.ceil(f.size/1024)} KB</small></span><button class="row-action" data-upgrade="restore-backup" data-name="${esc(f.name)}">내용 확인</button></div>`).join('')||'<p>아직 백업이 없습니다.</p>'}</div>`);
    $('#upgrade-backup').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget;try{await post('/api/backups',globalThis.HOMEPLAN_BROWSER?{}:{directory:value('directory')});toast('독립 백업을 만들었습니다.');if(form.isConnected&&$('#modal').open)await backupDialog();}catch(error){modalError(error);}};
  }
  async function restoreBackup(name){
    const request={key:state.workspace,revision:state.revision,name};
    const data=await post('/api/backups/preview',request);if(state.workspace!==request.key||state.revision!==request.revision)throw new Error('계획이 바뀌었습니다. 복구 내용을 다시 확인해 주세요.');const preview=await post(`/api/workspaces/${request.key}/preview`,{household:data.household,revision:request.revision});
    if(!await confirmation('백업의 입력으로 현재 계획을 복구할까요?',`<p>${esc(name)}</p><p>최저 현금 ${shortMoney(preview.before.min_balance_overall)} → ${shortMoney(preview.after.min_balance_overall)}</p><p>변경 ${preview.changes.length}개 · 미저장 편집은 복구한 입력으로 바뀝니다. 이전 상태는 백업과 저장 기록에 보관합니다.</p>`,'복구'))return;
    const saved=await post('/api/backups/restore',request);await applySaved(saved);toast('선택한 계획을 백업에서 복구했습니다.');
  }
  async function importJson(){
    openModal('계획 JSON 가져오기','<p class="hint">파일 내용을 미리 확인한 뒤 현재 계획에 저장합니다. 이전 버전은 보관됩니다.</p><input id="upgrade-file" type="file" accept=".json,application/json"><div id="upgrade-error" class="modal-error" role="alert"></div>');
    $('#upgrade-file').onchange=async e=>{try{
      const file=e.target.files[0];if(!file)return;const data=JSON.parse(await file.text()),household=data.household||data;
      const request={household,revision:state.revision},preview=await post(`/api/workspaces/${state.workspace}/preview`,request);
      if(!await confirmation('가져온 계획을 저장할까요?',`<p>${esc(file.name)} · 변경 ${preview.changes.length}개</p><p>최저 현금 ${shortMoney(preview.before.min_balance_overall)} → ${shortMoney(preview.after.min_balance_overall)}</p>`,'가져오고 저장'))return;
      const saved=await post(`/api/workspaces/${state.workspace}`,request,'PUT');await applySaved(saved);
    }catch(error){modalError(error);}};
  }
  async function advanced(){
    templateCache??=await api('/api/new-plan');
    const visible=new Set($$('#content [data-key]').map(i=>i.dataset.key));
    const fields=[];
    for(const [key,schema] of Object.entries(templateCache.settings_schema)){
      if(visible.has(key)||['setting_statuses','mortgage_quote_option','credit_amount_mode','sub_amount_mode'].includes(key))continue;
      const current=state.draft.settings[key]??schema.default??'';
      if(typeof current==='object'&&current!==null)continue;
      const label=settingLabels[key]||key;
      if(schema.type==='boolean'){fields.push({key,kind:'bool',html:checkField(key,label)});continue;}
      let kind=ratioKeys.has(key)?'percent':integerKeys.has(key)?'int':key.endsWith('_date')||key.endsWith('_start')?'date':schema.type==='integer'?'money':'text';
      const options={ownership:['공동명의','남편','아내'],mortgage_borrower:['남편','아내'],mortgage_mode:['대출금 고정','월 상환 한도 역산'],equal_principal_dsr_basis:['전체 평균','첫해'],mortgage_rate_type:['고정금리','변동금리','혼합금리','확인 필요']};
      fields.push({key,kind,html:options[key]?selectField(key,label,options[key]):field(key,label,kind)});
    }
    openModal('상세 설정 · 보유 자금·휴직·수리·규칙',`<form id="upgrade-advanced"><p class="hint">자산 기준일의 보유금과 과거 계획으로 오늘의 시작 현금을 이어 계산합니다. 실제 잔액이 달라졌다면 기준일과 자금 목록을 함께 갱신하세요. 명의·지분은 기록용이며 명의별 세금은 별도로 계산하지 않습니다.</p><div class="fields">${fields.map(f=>f.html).join('')}</div>${actions()}</form>`);
    $('#upgrade-advanced').onsubmit=async e=>{e.preventDefault();try{
      const candidate=clone(state.draft);
      for(const {key,kind} of fields){const input=$(`#upgrade-advanced [data-key="${key}"]`);let v=input.value;
        if(kind==='money'){v=readMoneyInput(input);if(v==null)throw new Error(`${settingLabels[key]||key} 금액을 입력하세요.`);}
        if(kind==='int'){if(v.trim()===''&&key==='expense_day')v=null;else{v=Number(v);if(!Number.isFinite(v))throw new Error('숫자를 확인하세요.');}}
        if(kind==='percent')v=Number(v)/100;
        if(kind==='bool')v=input.checked;
        if(kind==='date'&&!v)v=null;
        candidate.settings[key]=v;
      }
      // The resolved date/enum/range contract is validated by the same server engine.
      await applyCandidate(candidate);closeModal();toast('상세 설정을 반영했습니다. 확인 후 저장해 주세요.');
    }catch(error){modalError(error);}};
  }
  function prepaymentDialog(id){
    const row=state.draft.loan_prepayments?.find(r=>r.id===id)||{loan:'credit',date:'잔금일+1',amount:0,fee:0,method:'납입 감소',enabled:true};
    openModal('대출 추가 상환',`<form id="upgrade-prepay"><div class="fields"><div class="field"><label for="upgrade-loan">상환할 대출</label><select id="upgrade-loan">${Object.entries(loanNames).map(([key,label])=>`<option value="${key}" ${row.loan===key?'selected':''}>${label}</option>`).join('')}</select></div>${formField('date','추가 상환일',row.date,'date')}${formField('amount','상환 원금',row.amount,'money')}${formField('fee','상환 수수료',row.fee,'money')}<div class="field"><label for="upgrade-method">상환 후 계산</label><select id="upgrade-method"><option ${row.method==='납입 감소'?'selected':''}>납입 감소</option><option ${row.method==='기간 단축'?'selected':''}>기간 단축</option></select></div><label class="checkbox-line"><input id="upgrade-enabled" type="checkbox" ${row.enabled?'checked':''}>이 상환을 계획에 포함</label></div><p class="hint">같은 날 정기 납부 후 추가 원금을 갚습니다. 납입 감소는 남은 기간으로 월액을 다시 계산하고, 기간 단축은 기존 납입 수준을 유지합니다. 은행 약정에 맞는 방식과 수수료를 입력하세요. 지원금 수령은 부모님 지원에서 별도로 등록하세요.</p>${actions()}</form>`);
    $('#upgrade-prepay').onsubmit=async e=>{e.preventDefault();try{
      const candidate=clone(state.draft);candidate.loan_prepayments??=[];
      const updated={id:id||`PRE-${Date.now()}`,loan:value('loan'),date:value('date'),amount:money('amount'),fee:money('fee'),method:value('method'),enabled:$('#upgrade-enabled').checked};
      if(id)candidate.loan_prepayments=candidate.loan_prepayments.map(r=>r.id===id?updated:r);else candidate.loan_prepayments.push(updated);
      await applyCandidate(candidate);closeModal();toast('추가 상환을 반영했습니다. 확인 후 저장해 주세요.');
    }catch(error){modalError(error);}};
  }
  function replacement(id){
    const old=expenseRows().find(r=>r.id===id);if(!old)return;
    openModal('기존 지출 금액 변경',`<form id="upgrade-replace"><p>${esc(old.name)} · 월 ${shortMoney(old.amount)}</p><div class="fields">${formField('name','변경 후 이름',`${old.name} · 변경 후`)}${formField('date','변경일부터 새 금액 적용',state.draft.settings.birth_date?'출산예정일':'입주일','date')}${formField('amount','변경 후 월 금액',old.amount,'money')}</div><p class="hint">기존 항목은 변경 전날까지, 새 금액은 변경일부터 적용합니다. 교체하는 달은 양쪽 모두 일할로 계산합니다. 상대 날짜는 계속 연결됩니다.</p><button type="button" class="button small" id="replacement-preview-button">전후 3개월 미리보기</button><div id="replacement-preview"></div>${actions()}</form>`);
    const candidate=()=>{const h=clone(state.draft);h.expense_items=clone(expenseRows());h.expense_items.push({...clone(old),id:`EXP-${Date.now()}`,name:value('name').trim(),amount:money('amount'),start_date:value('date'),end_date:null,replaces_id:id,enabled:true,prorate:true});return h;};
    $('#replacement-preview-button').onclick=async()=>{try{const h=candidate(),r=await candidateResult(h),newRow=r.expense_schedule.at(-1),start=newRow.start_date.slice(0,7),months=Object.keys(r.kpis.monthly_expense_breakdown),index=months.indexOf(start),selected=months.slice(Math.max(0,index-1),index+2);$('#replacement-preview').innerHTML=`<div class="table-wrap"><table><thead><tr><th>월</th><th>기존 지출</th><th>변경 후 지출</th></tr></thead><tbody>${selected.map(month=>`<tr><td>${month}</td><td>${won(r.kpis.monthly_expense_breakdown[month][old.name]||0)}원</td><td>${won(r.kpis.monthly_expense_breakdown[month][newRow.name]||0)}원</td></tr>`).join('')}</tbody></table></div>`;}catch(error){modalError(error);}};
    $('#upgrade-replace').onsubmit=async e=>{e.preventDefault();try{await applyCandidate(candidate());closeModal();toast('지출 금액 변경을 반영했습니다.');}catch(error){modalError(error);}};
  }
  function composition(action,id){
    openModal('기존 고정비의 내용을 확인해 주세요',`<form id="upgrade-composition"><p>고정비 월 ${shortMoney(state.draft.settings.fixed_cost||0)}를 기간별 지출로 옮깁니다.</p><label class="checkbox-line"><input id="upgrade-current-housing" type="checkbox">현재 전세의 이자·관리비이며 퇴거일까지만 지출</label><label class="checkbox-line"><input id="upgrade-included-interest" type="checkbox">이 금액에 전세대출 이자가 포함</label><p class="hint">보험·통신 등 이사 후에도 유지되는 고정비라면 두 선택을 꺼두세요.</p>${actions('지출 계획 적용')}</form>`);
    $('#upgrade-composition').onsubmit=async e=>{e.preventDefault();try{
      const rows=clone(expenseRows()),fixed=rows.find(r=>r.id==='E02');if(fixed){fixed.includes_lease_interest=$('#upgrade-included-interest').checked;fixed.end_date=$('#upgrade-current-housing').checked?'퇴거일':null;fixed.name=$('#upgrade-current-housing').checked?'현재 전세 주거비':'기존 고정비';}
      await commitExpensePlan(rows);closeModal();scheduleDraft();
      if(action!=='expense-apply')$(`[data-action="${action}"]${id?`[data-id="${id}"]`:''}`)?.click();
    }catch(error){modalError(error);}};
  }
  async function inspect(action){
    if(state.calculatedSnapshot!==JSON.stringify(state.draft)){if(!validInputs())return;await calculate();if(state.calculatedSnapshot!==JSON.stringify(state.draft))return;}
    if(!state.result)return;
    if(action==='inspect-spend'){
      const check=state.result.checks.find(r=>r.name==='월 가계지출 한도');state.expenseMonth=check?.numbers.month;state.route='settings';location.hash='settings';render();$('#expense-summary')?.closest('section')?.scrollIntoView({block:'start'});return;
    }
    if(action==='inspect-minimum'){state.cashDate=String(state.result.kpis.min_balance_date);state.chartRange='all';}
    state.route='ledger';location.hash='ledger';render();$('#date-cash')?.scrollIntoView({block:'start'});
  }
  function afterRender(){
    if(!state.draft)return;
    if(!$('#upgrade-toolbar'))$('.page-heading').insertAdjacentHTML('afterend',`<div class="upgrade-toolbar" id="upgrade-toolbar"><button class="button small" data-upgrade="new">+ 새 계획</button><button class="button small" data-upgrade="copy">계획 복사</button><button class="button small" data-upgrade="compare">계획 비교</button><button class="button small" data-upgrade="advanced">상세 설정</button><button class="button small" data-upgrade="backup">백업·복구</button><button class="button small" data-upgrade="import">JSON 가져오기</button><button class="button small" data-upgrade="rules">계산 기준·출처</button></div>`);
    const r=state.result,k=r?.kpis;
    if(k){
      const uncertain=(r.assumptions||[]).filter(a=>a.kind==='loan'||a.kind==='support'||a.kind==='fund').reduce((sum,a)=>sum+Number(a.amount||0),0);
      $('#content').insertAdjacentHTML('afterbegin',`<section class="runtime-summary"><div><strong>계산 시작 ${esc(String(k.calculation_start_date))}</strong><small>보유 자금 기준 ${esc(String(k.asset_base_date))} · 시작 현금 ${shortMoney(k.opening_cash)}</small></div><label class="checkbox-line"><input type="checkbox" data-key="start_today" data-kind="bool" data-scope="settings" ${state.draft.settings.start_today?'checked':''}>매일 오늘부터 계산</label><div><span>${esc(k.variable_asset_mode)} · ${state.confirmed?'확정 자금만':'예정 자금 포함'}</span><small>미확정 유입 ${shortMoney(uncertain)}</small></div><button class="row-action" data-upgrade="confirmed">${state.confirmed?'예정 자금도 포함':'확정 자금만 비교'}</button></section>`);
    }
    if(state.route==='settings'){
      $$('[data-action="expense-edit"]').forEach(button=>button.insertAdjacentHTML('afterend',`<button class="row-action" data-upgrade="replace" data-id="${esc(button.dataset.id)}">금액 변경</button>`));
      const rows=state.draft.loan_prepayments||[];
      $('#tax-card-plan')?.insertAdjacentHTML('afterend',`<section class="card form-section" id="prepayment-plan"><div class="section-bar"><h2>대출 추가 상환</h2><button class="button small" data-upgrade="prepay">+ 추가 상환</button></div><div class="table-wrap"><table><thead><tr><th>대출</th><th>날짜</th><th>원금 · 수수료</th><th>방식</th><th></th></tr></thead><tbody>${rows.map(row=>`<tr class="${row.enabled?'':'muted-row'}"><td>${loanNames[row.loan]}</td><td>${esc(row.date)}</td><td>${shortMoney(row.amount)} · ${shortMoney(row.fee)}</td><td>${esc(row.method)}</td><td><button class="row-action" data-upgrade="prepay" data-id="${esc(row.id)}">수정</button><button class="row-action danger" data-upgrade="prepay-delete" data-id="${esc(row.id)}">삭제</button></td></tr>`).join('')}</tbody></table></div><p class="hint">일회성 추가 상환은 실제 현금과 부채에 반영하고, 월 유지비에는 재계산한 정기 납부액을 반영합니다.</p></section>`);
      for(const prefix of ['credit','sub']){
        const input=$(`#field-${prefix}_amount`);if(!input)continue;
        const use=prefix==='credit'?'credit_use':'sub_loan_use',amount=state.draft.settings[`${prefix}_amount`],mode=state.draft.settings[`${prefix}_amount_mode`];
        const selected=!state.draft.settings[use]?'미사용':mode==='자동'||(mode!=='직접'&&!amount)?'자동 한도':'직접 금액';
        input.closest('.field').insertAdjacentHTML('afterbegin',`<label for="${prefix}-amount-mode">금액 결정</label><select id="${prefix}-amount-mode" data-loan-mode="${prefix}">${['미사용','자동 한도','직접 금액'].map(v=>`<option ${v===selected?'selected':''}>${v}</option>`).join('')}</select>`);
        input.disabled=selected!=='직접 금액';input.closest('.money-control').querySelector('select').disabled=input.disabled;
        if(amount>0&&amount<1000000)input.closest('.field').insertAdjacentHTML('beforeend',`<p class="amount-warning" role="status">현재 금액은 ${esc(moneyWords(amount))}입니다. 입력 단위를 확인해 주세요.</p>`);
      }
      const month=state.expenseMonth||r?.schedule.closing_date.slice(0,7),events=r?.ledger.filter(e=>e.date.startsWith(month))||[];
      const income=events.filter(e=>e.amount>0).reduce((sum,e)=>sum+e.amount,0),out=-events.filter(e=>e.amount<0).reduce((sum,e)=>sum+e.amount,0);
      $('#expense-summary')?.insertAdjacentHTML('beforeend',`<div class="actual-month"><strong>이 월의 원장 · ${esc(month||'')}</strong><p>실제 예정 입금 ${shortMoney(income)} · 출금 ${shortMoney(out)} · 차액 ${shortMoney(income-out)}</p><small>대출 실행·자산 이동·일회성 비용 포함. 월 유지비의 세금 월평균과 실제 납부액은 다릅니다.</small></div>`);
      $$('#content .form-section').forEach(section=>{
        const heading=section.querySelector('h2');if(!heading)return;
        const title=heading.textContent,details=document.createElement('details');details.className='settings-group';details.open=groups.get(title)??(title.includes('지출 계획')||title.includes('주택담보')||title.includes('추가 상환'));
        const summary=document.createElement('summary');summary.textContent=title;details.append(summary);section.before(details);details.append(section);heading.classList.add('sr-only');details.ontoggle=()=>groups.set(title,details.open);
      });
    }
    scheduleDraft();
  }
  document.addEventListener('click',async event=>{
    const action=event.target.closest('[data-upgrade]');
    if(!action)return;
    const name=action.dataset.upgrade,id=action.dataset.id;
    try{
      if(name==='close'){closeModal();return;}
      if(name==='new')await newPlan();
      if(name==='copy')await copyPlan();
      if(name==='compare')await compare();
      if(name==='advanced')await advanced();
      if(name==='backup')await backupDialog();
      if(name==='restore-backup')await restoreBackup(action.dataset.name);
      if(name==='import')await importJson();
      if(name==='confirmed'){if(!validInputs())return;state.confirmed=!state.confirmed;await calculate();}
      if(name==='prepay')prepaymentDialog(id);
      if(name==='prepay-delete'&&await confirmation('이 추가 상환을 삭제할까요?','<p>정기 납부는 다시 계산합니다. 저장 기록에서 복원할 수 있어요.</p>','삭제',{focusConfirm:true})){const h=clone(state.draft);h.loan_prepayments=h.loan_prepayments.filter(r=>r.id!==id);await applyCandidate(h);}
      if(name==='replace')replacement(id);
      if(name==='apply-scenario'&&await confirmation('선택한 계획의 입력을 현재 초안으로 가져올까요?','<p>현재 저장본은 유지됩니다. 계산을 확인하고 변경사항을 저장해 주세요.</p>','초안에 적용')){const source=await api(`/api/workspaces/${id}`);await applyCandidate(clone(source.household));closeModal();}
      if(name==='rules'){const rules=await api('/api/rules');openModal('계산 기준과 출처',`<p class="hint">대출·세금·육아급여 등은 입력한 조건과 아래 규칙을 사용합니다. 토허 잔금 일정 점검은 자금계획 기준이며 허가조건 이행 확인과 구분하세요.</p>${Object.entries(rules).map(([key,meta])=>`<section class="rule-source"><h3>${esc(key)}</h3><p>${esc(meta.source||'출처 확인 필요')}</p><small>확인일 ${esc(meta.checked_at||'미기록')} · ${esc(meta.status||'적용 조건 확인')}</small></section>`).join('')}`);}
    }catch(error){toast(error.message,true);}
  });
  $('#content').addEventListener('click',event=>{
    const button=event.target.closest('[data-action]');if(!button)return;
    if(button.dataset.action.startsWith('inspect-')){event.stopImmediatePropagation();inspect(button.dataset.action);return;}
    if(state.draft.expense_items==null&&button.dataset.action.startsWith('expense-')){event.stopImmediatePropagation();composition(button.dataset.action,button.dataset.id);}
  },true);
  $('#content').addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)&&event.target.matches('.inspectable')){event.preventDefault();event.target.click();}});
  $('#content').addEventListener('change',event=>{
    const prefix=event.target.dataset.loanMode;
    if(prefix){const mode=event.target.value,use=prefix==='credit'?'credit_use':'sub_loan_use';state.draft.settings[use]=mode!=='미사용';state.draft.settings[`${prefix}_amount_mode`]=mode==='자동 한도'?'자동':'직접';state.max=null;scheduleDraft();render();}
    if(event.target.dataset.key==='start_today'){scheduleDraft();calculate();}
    if(event.target.id==='expense-month'){state.expenseMonth=event.target.value;render();}
  });
  const checkToday=async()=>{if(document.hidden||!state.draft?.settings.start_today||draftDirty()||document.activeElement?.matches('input,select,textarea'))return;try{const h=await api('/api/health');if(lastToday&&h.today!==lastToday)await calculate();lastToday=h.today;}catch{}};document.addEventListener('visibilitychange',checkToday);window.addEventListener('focus',checkToday);setInterval(checkToday,60000);
  api('/api/health').then(h=>lastToday=h.today).catch(()=>{});
  return {afterRender,scheduleDraft,flushDraft,clearDraft,offerRecovery,startOnboarding:newPlan,applyCandidate,applySaved};
}
