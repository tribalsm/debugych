type Scenario={title:string;requirement:string;gherkin:string;code:string;framework:string;dimensions:string[]};
export type ValidationReport={status?:string;classification?:string;plan_sha256?:string;attempts?:{plan_sha256:string;draft?:{requirements:{key:string;text:string}[];scenarios:Scenario[]}}[]};
type Test={id:string;validation_id?:string;validation_plan_sha256?:string;scenario_index?:number;title:string;requirement?:string;gherkin:string;code:string;framework:string;dimensions?:string[]};
/** The edit API retains validation metadata. Never trust an ID alone after an edit. */
export function validationMatches(test:Test,requirements:{key:string;text:string}[],jobs:{id:string;validation?:ValidationReport}[]):boolean{
 const report=jobs.find(j=>j.id===test.validation_id)?.validation;
 if(!report||report.status!=='validated'||!test.validation_plan_sha256||report.plan_sha256!==test.validation_plan_sha256||test.scenario_index===undefined)return false;
 const draft=report.attempts?.find(a=>a.plan_sha256===report.plan_sha256)?.draft;
 const scenario=draft?.scenarios[test.scenario_index];
 if(!scenario||!draft||requirements.length!==draft.requirements.length||!draft.requirements.every(r=>requirements.some(current=>r.key===current.key&&r.text===current.text)))return false;
 return (['title','requirement','gherkin','code','framework'] as const).every(key=>scenario[key]===test[key])&&JSON.stringify(scenario.dimensions)===JSON.stringify(test.dimensions);
}
