const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const units = [[1,'원'],[10000,'만원'],[10000000,'천만원'],[100000000,'억원']];
const preferredUnits = new Map();
const number = value => Number(value).toLocaleString('ko-KR');
const maxMoney = BigInt(Number.MAX_SAFE_INTEGER);

function scaledInteger(text, multiplier) {
  if (!/^\d+(?:\.\d+)?$/.test(text)) throw new Error('0 이상의 금액을 입력해 주세요.');
  const [integer, fraction=''] = text.split('.');
  const denominator = 10n ** BigInt(fraction.length);
  const numerator = BigInt(integer + fraction) * BigInt(multiplier);
  if (numerator % denominator) throw new Error('원보다 작은 금액은 입력할 수 없어요.');
  return numerator / denominator;
}

export function parseMoney(value, unit=1) {
  const raw = String(value).replace(/[\s,]/g,'');
  if (!raw) return null;
  const explicitWon = raw.endsWith('원'),text=explicitWon?raw.slice(0,-1):raw;
  let amount;
  if (/^\d+(?:\.\d+)?$/.test(text)) amount = scaledInteger(text, explicitWon?1:unit);
  else {
    const scales = {'조':1000000000000,'억':100000000,'천만':10000000,'백만':1000000,'십만':100000,'만':10000,'천':1000,'백':100,'십':10};
    const tokens = [...text.matchAll(/(\d+(?:\.\d+)?)(천만|백만|십만|조|억|만|천|백|십)?/g)];
    if (!tokens.length || tokens.map(token=>token[0]).join('') !== text) throw new Error('숫자 또는 3천만, 1억 2천만처럼 입력해 주세요.');
    amount = tokens.reduce((sum,token)=>sum+scaledInteger(token[1],scales[token[2]]||1),0n);
  }
  if (amount > maxMoney) throw new Error('입력할 수 있는 금액 범위를 넘었습니다.');
  return Number(amount);
}

export function formatMoney(amount, unit=1) {
  if (amount == null || amount === '') return '';
  const value = BigInt(amount), divisor = BigInt(unit);
  const remainder = value % divisor;
  const fraction = remainder ? '.' + String(remainder).padStart(String(unit).length-1,'0').replace(/0+$/,'') : '';
  return number(value / divisor) + fraction;
}

export function moneyWords(amount) {
  if (amount == null) return '';
  if (!amount) return '0원';
  let remaining = amount;
  const parts = [];
  for (const [scale,label] of [[1e12,'조'],[1e8,'억'],[1e4,'만']]) {
    const group = Math.floor(remaining / scale);
    if (group) parts.push(number(group) + label);
    remaining %= scale;
  }
  if (remaining) parts.push(number(remaining));
  return parts.join(' ') + '원';
}

export function moneyControl(id, label, value, attributes='', {defaultUnit}={}) {
  const amount = value == null || value === '' ? null : Number(String(value).replaceAll(',',''));
  const unit = preferredUnits.get(id) || defaultUnit || 10000;
  return `<div class="money-control"><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="${id}" data-money data-money-unit="${unit}" type="text" inputmode="decimal" value="${escape(formatMoney(amount,unit))}" aria-describedby="${id}-reading" ${attributes}><select class="money-unit" data-unit-for="${id}" aria-label="${escape(label)} 입력 단위">${units.map(([scale,name])=>`<option value="${scale}" ${scale===unit?'selected':''}>${name}</option>`).join('')}</select></div><small id="${id}-reading" class="money-reading" aria-live="polite">${amount==null?'단위를 고르고 금액을 입력하세요.':escape(moneyWords(amount))}</small>`;
}

export function readMoneyInput(input) {
  return parseMoney(input.value, Number(input.dataset.moneyUnit));
}

export function normalizeMoneyInput(input, amount=readMoneyInput(input)) {
  input.value = formatMoney(amount, Number(input.dataset.moneyUnit));
  updateMoneyReading(input);
}

function updateMoneyReading(input) {
  const hint = document.getElementById(input.id+'-reading');
  try {
    const amount = readMoneyInput(input);
    hint.textContent = amount==null?'단위를 고르고 금액을 입력하세요.':moneyWords(amount);
    hint.classList.remove('error');input.classList.remove('invalid');input.removeAttribute('aria-invalid');input.setCustomValidity('');
  } catch (error) {
    hint.textContent = error.message;hint.classList.add('error');input.setAttribute('aria-invalid','true');input.setCustomValidity(error.message);
  }
}

export function dateControl(id, label, value, attributes='', {rollingNow=false}={}) {
  return `<div class="date-control"><input autocomplete="off" spellcheck="false" autocorrect="off" autocapitalize="off" id="${id}" type="text" value="${escape(value)}" placeholder="YYYY-MM-DD 또는 일정" ${rollingNow?`aria-describedby="${id}-hint"`:''} ${attributes}>${rollingNow?`<button type="button" class="date-now" data-now-for="${id}" title="계산할 때마다 오늘 날짜로 반영">지금</button>`:''}<button type="button" class="calendar-toggle" data-calendar-for="${id}" aria-label="${escape(label)} 달력 열기" aria-expanded="false" title="달력에서 날짜 선택"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7 3v4m10-4v4M4 10h16M5 5h14a1 1 0 0 1 1 1v14H4V6a1 1 0 0 1 1-1Z"/><path d="M8 14h2m4 0h2m-8 3h2"/></svg></button></div>${rollingNow?`<small id="${id}-hint">‘지금’은 계산할 때마다 오늘 날짜로 반영해요.</small>`:''}`;
}

let calendar = null;
const iso = day => `${day.getFullYear()}-${String(day.getMonth()+1).padStart(2,'0')}-${String(day.getDate()).padStart(2,'0')}`;

export function closeCalendar(focus=false) {
  if (!calendar) return;
  const {panel,button,input} = calendar;
  panel.remove();button.setAttribute('aria-expanded','false');calendar=null;
  if (focus && input.isConnected) button.focus();
}

export function refreshCalendar() {
  if(!calendar)return;
  const input=document.getElementById(calendar.input.id),button=document.querySelector(`[data-calendar-for="${calendar.input.id}"]`);
  if(!input||!button){closeCalendar();return;}
  calendar.input=input;calendar.button=button;button.setAttribute('aria-expanded','true');positionCalendar();
}

function renderCalendar() {
  const {panel,input,view} = calendar, year=view.getFullYear(),month=view.getMonth();
  const start=new Date(year,month,1).getDay(),count=new Date(year,month+1,0).getDate();
  const today=iso(new Date());
  panel.innerHTML=`<div class="calendar-heading"><button type="button" data-month-step="-1" aria-label="이전 달">‹</button><select data-calendar-year aria-label="연도">${Array.from({length:201},(_,i)=>1900+i).map(value=>`<option ${value===year?'selected':''}>${value}</option>`).join('')}</select><select data-calendar-month aria-label="월">${Array.from({length:12},(_,i)=>`<option value="${i}" ${i===month?'selected':''}>${i+1}월</option>`).join('')}</select><button type="button" data-month-step="1" aria-label="다음 달">›</button></div><div class="calendar-week">${['일','월','화','수','목','금','토'].map(name=>`<span>${name}</span>`).join('')}</div><div class="calendar-days">${'<span></span>'.repeat(start)}${Array.from({length:count},(_,i)=>{const value=iso(new Date(year,month,i+1));return `<button type="button" data-calendar-day="${value}" aria-label="${year}년 ${month+1}월 ${i+1}일" ${value===today?'aria-current="date"':''} class="${value===input.value?'selected':''}">${i+1}</button>`;}).join('')}</div><div class="calendar-footer"><button type="button" data-calendar-day="${today}">오늘</button><span>날짜를 고르면 입력됩니다</span><button type="button" data-calendar-close>닫기</button></div>`;
  positionCalendar();
}

function positionCalendar() {
  if(!calendar)return;
  if(!calendar.input.isConnected){closeCalendar();return;}
  const {panel,button}=calendar,anchor=button.getBoundingClientRect(),height=panel.offsetHeight,width=panel.offsetWidth;
  if(anchor.bottom<0||anchor.top>innerHeight){closeCalendar();return;}
  panel.style.left=Math.max(8,Math.min(innerWidth-width-8,anchor.right-width))+'px';
  panel.style.top=Math.max(8,anchor.bottom+8+height<=innerHeight?anchor.bottom+8:anchor.top-height-8)+'px';
}

function openCalendar(button) {
  if (calendar?.button===button) {closeCalendar(true);return;}
  closeCalendar();
  const input=document.getElementById(button.dataset.calendarFor),panel=document.createElement('div');
  const selected=/^\d{4}-\d{2}-\d{2}$/.test(input.value)?new Date(input.value+'T12:00:00'):new Date();
  panel.className='calendar-panel';panel.setAttribute('role','dialog');panel.setAttribute('aria-label','날짜 선택');
  (input.closest('dialog')||document.body).append(panel);
  calendar={input,button,panel,view:new Date(selected.getFullYear(),selected.getMonth(),1)};
  button.setAttribute('aria-expanded','true');renderCalendar();
  (panel.querySelector(`[data-calendar-day="${iso(selected)}"]`)||panel.querySelector('[data-calendar-day]')).focus({preventScroll:true});
}

let installed=false;
export function installInputControls() {
  if (installed) return;installed=true;
  document.addEventListener('input',event=>{if(event.target.matches('[data-money]'))updateMoneyReading(event.target);});
  document.addEventListener('change',event=>{
    const selector=event.target.closest('[data-unit-for]');
    if(selector){
      const input=document.getElementById(selector.dataset.unitFor),previous=Number(input.dataset.moneyUnit);
      try {const amount=readMoneyInput(input);input.dataset.moneyUnit=selector.value;preferredUnits.set(input.id,Number(selector.value));normalizeMoneyInput(input,amount);}
      catch {selector.value=String(previous);updateMoneyReading(input);input.reportValidity();}
      return;
    }
    if(event.target.matches('[data-money]')){try{normalizeMoneyInput(event.target);}catch{updateMoneyReading(event.target);}}
    if(calendar&&calendar.panel.contains(event.target)){
      const year=Number(calendar.panel.querySelector('[data-calendar-year]').value),month=Number(calendar.panel.querySelector('[data-calendar-month]').value);
      calendar.view=new Date(year,month,1);renderCalendar();
    }
  });
  document.addEventListener('click',event=>{
    const now=event.target.closest('[data-now-for]');
    if(now){
      closeCalendar();
      const input=document.getElementById(now.dataset.nowFor);
      input.value='지금';input.dataset.nowSelected='true';input.setCustomValidity('');
      input.focus({preventScroll:true});
      input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
      return;
    }
    const toggle=event.target.closest('[data-calendar-for]');
    if(toggle){openCalendar(toggle);return;}
    if(!calendar)return;
    const target=event.target.closest('button');
    if(target&&calendar.panel.contains(target)){
      if(target.hasAttribute('data-calendar-day')){
        const input=calendar.input;input.value=target.dataset.calendarDay;input.setCustomValidity('');closeCalendar();input.focus({preventScroll:true});input.dispatchEvent(new Event('input',{bubbles:true}));input.dispatchEvent(new Event('change',{bubbles:true}));
      }else if(target.hasAttribute('data-month-step')){
        const view=calendar.view;view.setMonth(view.getMonth()+Number(target.dataset.monthStep));renderCalendar();calendar.panel.querySelector(`[data-month-step="${target.dataset.monthStep}"]`).focus({preventScroll:true});
      }else if(target.hasAttribute('data-calendar-close'))closeCalendar(true);
    }else if(!calendar.panel.contains(event.target))closeCalendar();
  });
  document.addEventListener('keydown',event=>{
    if(!calendar)return;
    if(event.key==='Escape'){event.preventDefault();event.stopPropagation();closeCalendar(true);return;}
    const day=event.target.dataset.calendarDay,offset={ArrowLeft:-1,ArrowRight:1,ArrowUp:-7,ArrowDown:7}[event.key];
    if(day&&offset){event.preventDefault();const date=new Date(day+'T12:00:00');date.setDate(date.getDate()+offset);calendar.view=new Date(date.getFullYear(),date.getMonth(),1);renderCalendar();calendar.panel.querySelector(`[data-calendar-day="${iso(date)}"]`).focus({preventScroll:true});}
  },true);
  document.addEventListener('scroll',event=>{if(calendar&&!calendar.panel.contains(event.target))positionCalendar();},true);
  window.addEventListener('resize',()=>closeCalendar());
  document.addEventListener('close',event=>{if(event.target.tagName==='DIALOG'&&!event.target.open)closeCalendar();},true);
}
