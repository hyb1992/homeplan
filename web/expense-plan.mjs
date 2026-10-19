// A reviewable starting point; creating a preview never changes stored input.
export function seedExpenseItems(household) {
  const s=household.settings;
  const defaults={start_date:'기준일',end_date:null,pay_day:null,enabled:true,prorate:false,includes_lease_interest:false,includes_management:false};
  return [
    {...defaults,id:'E01',name:'매달 생활비',category:'생활비',amount:Number(s.living_cost||0),includes_lease_interest:!!s.lease_interest_in_living,includes_management:!!s.mgmt_in_living},
    {...defaults,id:'E02',name:'기존 고정비',category:'주거비',amount:Number(s.fixed_cost||0),enabled:!s.fixed_in_living,includes_lease_interest:false},
    {...defaults,id:'E03',name:'출산 후 양육비',category:'양육비',amount:Number(s.childcare_cost||0),start_date:s.birth_date?'출산예정일':null,enabled:!!s.birth_date},
  ];
}
