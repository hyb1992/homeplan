import {readMoneyInput,closeCalendar} from './form-inputs.mjs';

export const fundTypes=[
  ['현금·예금','입출금 통장, 정기예금, 비상금'],
  ['적금·청년도약계좌','적금, 청약통장, 만기 저축'],
  ['투자자산','주식, 펀드, ETF 등'],
  ['성과급·환급금','성과급, 상여금, 연말정산 환급'],
  ['퇴직 관련 수령금','퇴직금, 퇴직연금 중도 수령'],
  ['전세보증금','퇴거할 때 돌려받을 보증금'],
  ['기타 들어올 돈','다른 유형에 없는 예정 수입'],
  ['기존 전세대출(부채)','갚아야 할 기존 전세대출'],
  ['기타 나갈 돈','별도로 지급할 돈'],
];
const ownedTypes=new Set(['현금·예금','적금·청년도약계좌','투자자산','전세보증금']);
const colors=['#28765b','#7e9c4b','#5c83aa','#c39442','#8c79ad','#4a9a93','#ab7d66','#ac6663','#6e8791'];
const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

export function recommendFundTypes(name){
  const text=String(name||'').normalize('NFKC').toLowerCase().replace(/[\s·_-]/g,'');
  if(!text||/(신용대출|주택담보|주담대|청약담보)/.test(text))return [];
  const rules=[
    ['기존 전세대출(부채)',/(전세.*대출|보증금대출)/],
    ['기타 나갈 돈',/(추가납부|추징|세금납부|보증금지급|보증금납부)/],
    ['퇴직 관련 수령금',/(퇴직|퇴사|irp)/],
    ['성과급·환급금',/(연말정산|환급|성과급|상여|보너스|인센티브)/],
    ['적금·청년도약계좌',/(적금|청년도약|청약|저축)/],
    ['투자자산',/(주식|펀드|etf|isa|증권|투자|코인|비트코인)/],
    ['전세보증금',/(전세|보증금|임대차)/],
    ['기타 나갈 돈',/(수리비|이사비|(?<!입)출금|지출|상환|지급)/],
    ['현금·예금',/(현금|예금|통장|비상금|파킹|cma|예치금|은행|뱅크)/],
  ];
  const matches=[...new Set(rules.filter(([,pattern])=>pattern.test(text)).map(([type])=>type))];
  // A lease loan is a liability even if its name also contains “deposit” or “repayment”.
  return matches[0]==='기존 전세대출(부채)'?matches.slice(0,1):matches;
}

export function fundComposition(rows,mode='보수적',purchaseOnly=false){
  const groups=new Map();let owned=0,incoming=0,debt=0,outgoing=0,excluded=0,missing=0;
  for(const row of rows){
    if(row.data_kind==='예시')continue;
    if(row.status==='제외'){excluded++;continue;}
    if(purchaseOnly&&row.use_for_purchase===false)continue;
    const raw=row.is_variable?(mode==='보수적'?row.conservative_amount:row.aggressive_amount):(row.cash_out_amount??row.value);
    if(raw==null){missing++;continue;}
    const value=Number(raw),cost=Number(row.cost||0),type=row.type||'기타 들어올 돈';
    if(type.includes('부채')||type==='가족 차입'){debt+=value;outgoing+=cost;continue;}
    if(type==='기타 나갈 돈'){outgoing+=value+cost;continue;}
    const amount=value-cost;
    if(amount<=0){outgoing-=Math.min(0,amount);continue;}
    const ownedType=ownedTypes.has(type);
    if(ownedType)owned+=amount;else incoming+=amount;
    const group=groups.get(type)||{type,amount:0,count:0,kind:ownedType?'owned':'incoming',color:colors[Math.max(0,fundTypes.findIndex(([t])=>t===type))%colors.length]};
    group.amount+=amount;group.count++;groups.set(type,group);
  }
  return {groups:[...groups.values()].sort((a,b)=>b.amount-a.amount||a.type.localeCompare(b.type)),owned,incoming,debt,outgoing,total:owned+incoming,excluded,missing};
}

export function renderFundComposition(rows,{mode='보수적',scope='all',purchaseOnly=false,selectedType=null,shortMoney,won}){
  const data=fundComposition(rows,mode,purchaseOnly),groups=data.groups.filter(g=>scope==='all'||g.kind===scope),total=groups.reduce((sum,g)=>sum+g.amount,0);
  let offset=0;
  const segments=groups.map(g=>{const share=g.amount/total*100,start=offset;offset+=share;const label=`${g.type} ${won(g.amount)}원, ${share.toFixed(1)}%`;return `<circle class="fund-segment ${selectedType===g.type?'selected':''}" cx="110" cy="110" r="82" pathLength="100" fill="none" stroke="${g.color}" stroke-width="29" stroke-dasharray="${share} ${100-share}" stroke-dashoffset="${-start}" transform="rotate(-90 110 110)" role="button" tabindex="0" data-fund-filter="${escape(g.type)}" aria-label="${escape(label)}"><title>${escape(label)}</title></circle>`;}).join('');
  const metric=(label,amount,detail)=>`<div><span>${label}</span><strong>${shortMoney(amount)}</strong><small>${detail}</small></div>`;
  return `<section class="card fund-composition"><div class="section-bar"><div><h2>유형별 자금 구성</h2><p>어떤 자금이 얼마나 있는지 한눈에 확인하세요.</p></div><button class="button primary" data-action="fund-add">+ 새 자금 추가</button></div><div class="fund-chart-controls"><div class="fund-chart-tabs" role="group" aria-label="자금 구성 범위">${[['all','전체 자금'],['owned','보유 자산 유형'],['incoming','예정 수입 유형']].map(([key,label])=>`<button class="button small ${scope===key?'soft':''}" data-fund-scope="${key}" aria-pressed="${scope===key}">${label}</button>`).join('')}</div><label class="checkbox-line"><input type="checkbox" id="fund-purchase-only" ${purchaseOnly?'checked':''}> 매수에 쓰는 자금만</label></div><div class="fund-composition-body"><div class="fund-donut"><svg viewBox="0 0 220 220" aria-label="유형별 자금 비중"><circle cx="110" cy="110" r="82" fill="none" stroke="#edf1eb" stroke-width="29"/>${segments}</svg><div class="fund-donut-total" data-total="${total}"><span>${scope==='all'?'등록 자금 합계':scope==='owned'?'보유 자산 유형 합계':'예정 수입 유형 합계'}</span><strong>${shortMoney(total)}</strong><small>${mode} 기준</small></div></div><div class="fund-chart-legend">${groups.map(g=>`<button type="button" class="fund-chart-row ${selectedType===g.type?'selected':''}" data-fund-filter="${escape(g.type)}" aria-pressed="${selectedType===g.type}"><span class="fund-swatch" style="background:${g.color}"></span><span>${escape(g.type)}<small>${g.count}개 · ${(g.amount/total*100).toFixed(1)}%</small></span><strong>${shortMoney(g.amount)}<small>${won(g.amount)}원</small></strong></button>`).join('')||'<p class="fund-chart-empty">표시할 자금이 없습니다.<br>자금을 추가하거나 조회 범위를 바꿔 보세요.</p>'}</div></div><div class="fund-composition-metrics">${metric('보유 자산 유형',data.owned,'예금·적금·투자·전세보증금')}${metric('예정 수입 유형',data.incoming,'성과급·환급금·퇴직금 등')}${metric('등록 부채 원금',data.debt,'원형 그래프와 별도')}${metric('별도 출금·비용',data.outgoing,'원형 그래프와 별도')}</div><p class="hint">미확정 예정금도 포함한 등록 자금의 비용 차감 후 구성입니다. 현재 가용 현금은 사용 가능일에 따라 달라집니다. 부모님 지원·대출 계약은 각 메뉴에서 확인하세요. 제외 ${data.excluded}개${data.missing?` · 금액 미입력 ${data.missing}개`:''}. 유형을 누르면 아래 목록을 좁혀 볼 수 있어요.</p></section>`;
}

export function installFundBuilder({form,preset=false,mode='보수적',shortMoney,won}){
  const $=s=>form.querySelector(s),name=$('#record-name'),type=$('#record-type'),variable=$('#record-is_variable');
  const modal=form.closest('dialog');modal.classList.add('fund-builder-dialog');modal.addEventListener('close',()=>modal.classList.remove('fund-builder-dialog'),{once:true});
  type.closest('.field').classList.add('wide');
  modal.querySelector('#modal-title').textContent='새 자금 만들기';
  form.noValidate=true;name.required=true;type.required=true;
  let step=0,visited=0,manual=!!preset,selected=!!preset,choosing=false,dateEdited=false,expanded=false;
  $('#record-available_date').addEventListener('input',()=>dateEdited=true);
  if(!preset){type.insertAdjacentHTML('afterbegin','<option value="">유형을 선택하세요</option>');type.value='';}
  const progress=document.createElement('div');progress.className='fund-builder-progress';progress.innerHTML=['이름·유형','금액','일정·확인'].map((title,index)=>`<button type="button" data-builder-step="${index}"><span>${index+1}</span>${title}</button>`).join('');
  form.prepend(progress);
  const grid=$('.fields'),sections=[0,1,2].map(index=>{const section=document.createElement('section');section.className='fund-builder-step';section.dataset.step=index;section.innerHTML=`<p class="builder-step-intro">${['먼저 자금 이름을 적어 주세요. 어울리는 유형을 추천해 드려요.','얼마를 사용할 수 있나요? 금액이 달라질 수 있다면 예상 범위를 정하세요.','언제, 누구의 자금인가요? 마지막으로 확인해 주세요.'][index]}</p><div class="fields"></div>`;return section;});
  for(const node of [...grid.children]){
    const index=node.querySelector('#record-name,#record-type')?0:node.querySelector('[data-money],#record-is_variable')||node.classList.contains('variable-explanation')?1:2;
    sections[index].querySelector('.fields').append(node);
  }
  grid.replaceWith(...sections);
  sections[2].append($('[name="use_for_purchase"]').closest('label'));
  sections[1].append($(':scope > p.field-help'));
  const recommendations=document.createElement('div');recommendations.className='fund-type-choices';
  const suggestion=document.createElement('p');suggestion.className='builder-suggestion';suggestion.setAttribute('role','status');
  const expand=document.createElement('button');expand.type='button';expand.className='button small builder-expand';
  sections[0].append(suggestion,recommendations,expand);
  const review=document.createElement('div');review.className='fund-builder-review';sections[2].prepend(review);
  const actions=$('.modal-actions'),submit=actions.querySelector('[type="submit"]');
  actions.insertAdjacentHTML('afterbegin','<button class="button" type="button" id="builder-back">이전</button>');
  actions.insertAdjacentHTML('beforeend','<button class="button primary" type="button" id="builder-next">다음</button>');
  const error=$('.modal-error');
  function refreshTypes(){
    const recommended=recommendFundTypes(name.value),all=[...new Set([...recommended,...fundTypes.map(([t])=>t)])],choices=expanded?all:[...new Set([...recommended.slice(0,2),selected?type.value:null,'현금·예금','적금·청년도약계좌','투자자산'].filter(Boolean))].slice(0,4);
    recommendations.innerHTML=choices.map(t=>`<button type="button" class="fund-type-choice ${selected&&type.value===t?'selected':''}" data-builder-type="${escape(t)}" aria-pressed="${selected&&type.value===t}"><span>${escape(t)}${recommended[0]===t?'<small>추천</small>':''}</span><small>${escape(fundTypes.find(([key])=>key===t)?.[1]||'직접 선택한 유형')}</small></button>`).join('');
    expand.textContent=expanded?'추천 유형만 보기':'모든 유형 펼치기';expand.setAttribute('aria-expanded',String(expanded));
    suggestion.textContent=!name.value.trim()?'예: 남편 예금, 연말정산 환급, 퇴직금, 전세보증금':/(신용대출|주담대|주택담보|청약담보)/.test(name.value)?'신용·주택담보·청약담보 대출 실행은 대출·가계 메뉴에서 설정할 수 있어요.':recommended.length?manual?`직접 고른 ‘${type.value}’ 유형을 유지합니다. 이름 기준 추천은 ‘${recommended[0]}’예요.`:`이름을 보고 ‘${recommended[0]}’ 유형을 추천했어요. 직접 바꿀 수 있어요.`:'이름만으로 유형을 정하기 어려워요. 아래에서 알맞은 유형을 선택해 주세요.';
  }
  function choose(value,byUser=false){type.value=value;selected=!!value;if(byUser)manual=true;if(value){const date=$('#record-available_date');if(!dateEdited&&!date.value&&['현금·예금','적금·청년도약계좌','투자자산'].includes(value))date.value='지금';choosing=true;type.dispatchEvent(new Event('change',{bubbles:true}));choosing=false;}refreshTypes();}
  name.addEventListener('input',()=>{name.setCustomValidity('');const recommended=recommendFundTypes(name.value);if(!manual)choose(recommended[0]||'');refreshTypes();});
  type.addEventListener('change',()=>{if(!choosing){manual=true;selected=!!type.value;}type.setCustomValidity('');refreshTypes();});
  recommendations.onclick=event=>{const button=event.target.closest('[data-builder-type]');if(button)choose(button.dataset.builderType,true);};
  expand.onclick=()=>{expanded=!expanded;refreshTypes();};
  function read(key){return readMoneyInput($('#record-'+key));}
  function refreshReview(){
    let amount='금액을 입력해 주세요.';
    try{
      const cost=read('cost')||0,raw=variable.checked?read(mode==='보수적'?'conservative_amount':'aggressive_amount'):read('cash_out_amount')??read('value');
      if(raw!==null){const negative=type.value.includes('부채')||type.value==='기타 나갈 돈',net=negative?-raw-cost:raw-cost;amount=`${shortMoney(net)}<small>${won(net)}원${variable.checked?` · ${mode} 기준`:''}</small>`;}
    }catch{amount='금액을 확인해 주세요.';}
    review.innerHTML=`<span>등록할 자금</span><strong>${escape(name.value||'이름 미입력')}</strong><p>${escape(type.value||'유형 미선택')} · ${escape($('#record-owner').value)}</p><div>${amount}</div><small>변경사항 저장을 누르면 이 계획에 보관됩니다.</small>`;
  }
  function validate(index){
    error.textContent='';
    try{
      if(index===0){if(!name.value.trim())throw new Error('자금 이름을 입력해 주세요.');if(!selected||!type.value)throw new Error('자금 유형을 선택해 주세요.');}
      if(index===1){
        if(variable.checked){const low=read('conservative_amount'),high=read('aggressive_amount');if(low==null||high==null)throw new Error('보수적·공격적 금액을 모두 입력해 주세요.');if(low>high)throw new Error('보수적 금액은 공격적 금액 이하여야 합니다.');}
        else if(read('value')==null)throw new Error('금액을 입력해 주세요.');
        for(const key of ['cost','cash_out_amount'])if(!$('#record-'+key).disabled)read(key);
      }
      for(const input of sections[index].querySelectorAll('input,select'))if(!input.disabled&&!input.checkValidity()){input.reportValidity();throw new Error(input.validationMessage);}
      return true;
    }catch(e){error.textContent=e.message;return false;}
  }
  function show(index){
    closeCalendar();step=index;visited=Math.max(visited,step);sections.forEach((section,i)=>section.hidden=i!==step);
    for(const button of progress.querySelectorAll('button')){const i=Number(button.dataset.builderStep);button.disabled=i>visited;button.setAttribute('aria-current',i===step?'step':'false');}
    $('#builder-back').hidden=step===0;$('#builder-next').hidden=step===2;submit.hidden=step!==2;
    refreshReview();error.textContent='';const first=[name,variable.checked?$('#record-conservative_amount'):$('#record-value'),$('#record-owner')][step];first.focus({preventScroll:true});modal.scrollTop=0;
  }
  $('#builder-next').onclick=()=>{if(validate(step))show(step+1);};$('#builder-back').onclick=()=>show(step-1);
  progress.onclick=event=>{const button=event.target.closest('[data-builder-step]');if(button&&(Number(button.dataset.builderStep)<=step||validate(step)))show(Number(button.dataset.builderStep));};
  form.addEventListener('submit',event=>{
    if(step<2){event.preventDefault();event.stopImmediatePropagation();if(validate(step))show(step+1);return;}
    for(let i=0;i<3;i++)if(!validate(i)){event.preventDefault();event.stopImmediatePropagation();show(i);validate(i);return;}
  },true);
  form.addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.isComposing&&step<2&&event.target.matches('input')){event.preventDefault();if(validate(step))show(step+1);}});
  form.addEventListener('input',refreshReview);form.addEventListener('change',refreshReview);
  refreshTypes();show(0);
}
