// Rendering-only stress data. No execution, LLM, secrets or hidden oracle.
const {readFileSync}=require('node:fs'),path=require('node:path');
function responsiveFixture(stress=false){
 const data=JSON.parse(readFileSync(path.resolve(__dirname,'../../../infra/server/public-demo.json'),'utf8'));
 data.routes['/api/health'].guest_mode_available=true;
 if(!stress)return data;
 const pid=data.projectId,prefix='/api/projects/'+pid;
 data.routes['/api/projects'][0].name='UIСТЕНД_'+ 'LongProjectName'.repeat(7);
 data.routes[prefix].name=data.routes['/api/projects'][0].name;
 const test=data.routes[prefix+'/test-cases'][0];
 test.title='Synthetic renderer fixture / '+ 'long_test_name_'.repeat(12);
 test.code='# SYNTHETIC RESPONSIVE FIXTURE - NOT EXECUTED\n'+Array.from({length:90},(_,i)=>`# line ${i}: ${'readable_code_'.repeat(30)}`).join('\n');
 const bugs=data.routes['/api/bugs?project_id='+pid];
 bugs[0].actual='SYNTHETIC TRACEBACK / '+ 'long_path_component_'.repeat(35);
 bugs[0].traceback='SYNTHETIC TRACEBACK - NOT EXECUTED\n'+Array.from({length:80},(_,i)=>`File "src/${'long_module_'.repeat(20)}.py", line ${i+1}`).join('\n');
 const fix=data.routes[prefix+'/fixes'][0];
 fix.diff='--- a/src/'+ 'module_'.repeat(25)+'.py\n+++ b/src/'+ 'module_'.repeat(25)+'.py\n@@ -1,2 +1,2 @@\n-'+ 'old_value_'.repeat(80)+'\n+'+'new_value_'.repeat(80)+'\n';
 return data;
}

module.exports={responsiveFixture};
