import assert from 'node:assert/strict';
import {recommendFundTypes,fundComposition,renderFundComposition} from '../../web/fund-builder.mjs';

for(const [name,type] of [
  ['남편 입출금통장','현금·예금'],['청년도약계좌 적금','적금·청년도약계좌'],
  ['퇴직연금 중도인출','퇴직 관련 수령금'],['연말정산 환급','성과급·환급금'],
  ['S&P500 ETF','투자자산'],['전세보증금 반환','전세보증금'],
  ['전세보증금 대출 상환','기존 전세대출(부채)'],['이사비 지급','기타 나갈 돈'],['연말정산 추가 납부','기타 나갈 돈'],
  ['우리은행','현금·예금'],['ISA','투자자산'],
])assert.equal(recommendFundTypes(name)[0],type,name);
for(const name of ['', '목돈', '신용대출', '주택담보대출', '청약담보대출'])assert.deepEqual(recommendFundTypes(name),[]);

const rows=[
  {type:'현금·예금',value:100,cost:10},
  {type:'투자자산',value:999,cash_out_amount:999,is_variable:true,conservative_amount:80,aggressive_amount:160,cost:5},
  {type:'전세보증금',value:500,use_for_purchase:false},
  {type:'성과급·환급금',value:30,status:'미확정'},
  {type:'기존 전세대출(부채)',value:100,cost:2},
  {type:'기타 나갈 돈',value:40,cost:3},
  {type:'투자자산',value:5,cost:10},
  {type:'현금·예금',value:1000,status:'제외'},
  {type:'현금·예금',value:1000,data_kind:'예시'},
  {type:'현금·예금',value:null},
  {type:'현금·예금',value:0},
];
const snapshot=structuredClone(rows),base=fundComposition(rows);
assert.deepEqual([base.owned,base.incoming,base.total,base.debt,base.outgoing,base.excluded,base.missing],[665,30,695,100,50,1,1]);
assert.equal(base.groups.find(g=>g.type==='투자자산').amount,75);
assert.equal(fundComposition(rows,'공격적').total,775);
assert.equal(fundComposition(rows,'보수적',true).total,195);
assert.deepEqual(rows,snapshot);
assert.equal(fundComposition([{type:'투자자산',is_variable:true,conservative_amount:0,aggressive_amount:100,value:500}]).total,0);
assert.equal(fundComposition([{type:'현금·예금',value:100,cash_out_amount:0}]).total,0);

const options={shortMoney:n=>String(n),won:n=>String(n)};
for(const empty of [[],[{type:'현금·예금',value:0}],[{type:'현금·예금',value:10,status:'제외'}]]){
  const html=renderFundComposition(empty,options);
  assert.ok(html.includes('표시할 자금이 없습니다'));
  assert.ok(!/NaN|Infinity/.test(html));
}
const html=renderFundComposition([{type:'<img src=x onerror=alert(1)>',value:10}],options);
assert.ok(html.includes('&lt;img'));
assert.ok(!html.includes('<img'));
console.log('Fund recommendations, net composition, variable assets, exclusions, debt separation, zero states and escaping passed.');
