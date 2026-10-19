import assert from 'node:assert/strict';
import {parseMoney, formatMoney, moneyWords, moneyControl} from '../../web/form-inputs.mjs';
import {seedExpenseItems} from '../../web/expense-plan.mjs';

assert.equal(parseMoney('3', 10000000), 30000000);
assert.equal(parseMoney('1.2', 100000000), 120000000);
assert.equal(parseMoney('3,000', 10000), 30000000);
assert.equal(parseMoney('3천만', 100000000), 30000000);
assert.equal(parseMoney('30,000,000원', 100000000), 30000000);
assert.equal(parseMoney('1억 2천만원', 10000), 120000000);
assert.equal(parseMoney('1억 2천만', 10000), 120000000);
assert.equal(parseMoney('0.00000001', 100000000), 1);
assert.equal(parseMoney('1.23456789', 100000000), 123456789);
assert.equal(parseMoney(''), null);
assert.equal(parseMoney('0', 10000), 0);
assert.equal(moneyWords(30000000), '3,000만원');
assert.equal(moneyWords(120000000), '1억 2,000만원');
assert.equal(moneyWords(123456789), '1억 2,345만 6,789원');
assert.equal(moneyWords(100000000), '1억원');
for(const amount of [0,1,9999,30000000,123456789,Number.MAX_SAFE_INTEGER]){
  for(const unit of [1,10000,10000000,100000000]){
    assert.equal(parseMoney(formatMoney(amount,unit),unit),amount,`${amount} at unit ${unit}`);
  }
}
for(const invalid of ['-1','Infinity','1e8','9007199254740992','3abc']){
  assert.throws(()=>parseMoney(invalid));
}
assert.throws(()=>parseMoney('0.000000001',100000000));
assert.throws(()=>parseMoney('0.1원',100000000));
// Property inputs default to eok while preserving every won in existing values.
const smallPrice=moneyControl('test-price','매수가',118000,'',{defaultUnit:1e8});
assert.match(smallPrice,/data-money-unit="100000000"/);
assert.match(smallPrice,/value="0\.00118"/);
assert.equal(parseMoney('0.00118',1e8),118000);
assert.match(moneyControl('test-price-corrected','매수가',1180000000,'',{defaultUnit:1e8}),/value="11\.8"/);
assert.match(moneyControl('test-empty-property','매수가','','',{defaultUnit:1e8}),/data-money-unit="100000000"/);
assert.match(moneyControl('test-fund','자금',3000000),/data-money-unit="10000"/);
console.log('Money unit conversion, Korean amounts, exact won round trips and invalid values passed.');
const household={settings:{living_cost:3000000,fixed_cost:1500000,childcare_cost:800000}};
const original=JSON.stringify(household),expenses=seedExpenseItems(household);
assert.equal(expenses[1].amount,1500000);
assert.equal(expenses[1].end_date,null);
assert.equal(expenses[1].includes_lease_interest,false);
assert.equal(expenses[1].includes_management,false);
assert.equal(expenses[2].enabled,false);
assert.equal(JSON.stringify(household),original);
household.settings.birth_date='2027-06-01';
assert.equal(seedExpenseItems(household)[2].start_date,'출산예정일');
assert.equal(seedExpenseItems(household)[2].enabled,true);
console.log('Expense preview preserves amounts, separates current housing, and handles missing birth date.');

assert.match(moneyControl('zero-credit','신용대출',0),/data-money-unit="10000"/);
assert.equal(parseMoney('8300',10000),83000000);
