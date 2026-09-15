#!/usr/bin/env python3
import argparse,json,platform,sys,time,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--report',default=str(ROOT/'reports/test-results.json'));a=p.parse_args()
    start=time.monotonic();suite=unittest.defaultTestLoader.discover(str(ROOT/'tests'),pattern='test_*.py')
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    summary={'scope':'local synthetic automated tests; not Doubao','python':platform.python_version(),'platform':platform.system(),'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'seconds':round(time.monotonic()-start,3),'details':[{'test':str(t),'trace':trace} for t,trace in result.failures+result.errors]}
    path=Path(a.report);path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(summary,indent=2)+'\n');print(json.dumps(summary));sys.exit(0 if result.wasSuccessful() else 1)
