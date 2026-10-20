"""Trusted synthetic smoke. No project code is executed here."""
import ast,json,time,argparse
from pydantic import BaseModel,ConfigDict,Field
from services.ai.adapter import AIAdapter,Settings
from apps.api.ai_runtime import reserve
class Smoke(BaseModel):
 model_config=ConfigDict(extra='forbid')
 requirement:str
 gherkin:str
 code:str
parser=argparse.ArgumentParser(description='Trusted synthetic live smoke; never executes project code on backend.')
parser.add_argument('--allow-external',action='store_true')
args=parser.parse_args()
if not args.allow_external:raise SystemExit('Synthetic external sending requires --allow-external')
s=Settings.load();s.max_calls=1
rows=[];start=time.monotonic()
result={'provider':s.base_url,'requested_model':s.model,'mode':s.mode,'response_format':s.response_format}
def validate(v):
 ast.parse(v.code)
 if 'Feature:' not in v.gherkin or 'Scenario:' not in v.gherkin:raise ValueError('Gherkin')
 return v
try:
 adapter=AIAdapter(s,reserve=reserve,audit=rows.append)
 answer=adapter.generate('live_smoke',Smoke,'Analyze the explicit requirement. Return a short Gherkin scenario and executable pytest test importing add from calc; do not execute code.',{'requirement':'R1. add(a,b) returns the mathematical sum of two integers.','source':'def add(a,b): return a+b\n'},validate)
 result.update(status='validated',generated=answer.model_dump())
except Exception as e:result.update(status='failed',error_code=getattr(e,'code',type(e).__name__))
result.update(attempts=rows,duration=round(time.monotonic()-start,3))
print(json.dumps(result,ensure_ascii=True))
