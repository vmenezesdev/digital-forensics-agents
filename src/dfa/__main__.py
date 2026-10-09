import argparse
import json
import sys
from pathlib import Path
from .store import Case

def main(argv=None):
    p=argparse.ArgumentParser(description="Experimental local evidence workspace: synthetic data only")
    p.add_argument("--case",required=True)
    subs=p.add_subparsers(dest="action",required=True)
    subs.add_parser("init")
    subs.add_parser("status")
    a=subs.add_parser("audit-verify");a.add_argument("--checkpoint",type=Path)
    subs.add_parser("audit-checkpoint")
    subs.add_parser("task-list")
    a=subs.add_parser("message-list");a.add_argument("id",type=int)
    a=subs.add_parser("source-add");a.add_argument("source_id");a.add_argument("path")
    a=subs.add_parser("ingest");a.add_argument("source_id")
    a=subs.add_parser("verify");a.add_argument("source_id")
    a=subs.add_parser("search");a.add_argument("query")
    a=subs.add_parser("task-add");a.add_argument("title")
    a=subs.add_parser("task-claim");a.add_argument("id",type=int);a.add_argument("actor")
    a=subs.add_parser("task-complete");a.add_argument("id",type=int);a.add_argument("token")
    a=subs.add_parser("message-post");a.add_argument("id",type=int);a.add_argument("actor");a.add_argument("body")
    x=p.parse_args(argv)
    case=Case(x.case)
    try:
        commands={"init":lambda:case.init(),"status":lambda:case.status(),
                  "audit-verify":lambda:case.audit_verify(json.loads(x.checkpoint.read_text(encoding="utf-8")) if x.checkpoint else None),
                  "audit-checkpoint":lambda:case.audit_checkpoint(),
                  "task-list":lambda:case.task_list(),"message-list":lambda:case.message_list(x.id),"source-add":lambda:case.source_add(x.source_id,x.path),
                  "ingest":lambda:case.ingest(x.source_id),"verify":lambda:case.verify(x.source_id),
                  "search":lambda:case.search(x.query),"task-add":lambda:case.task_add(x.title),
                  "task-claim":lambda:case.task_claim(x.id,x.actor),"task-complete":lambda:case.task_complete(x.id,x.token),
                  "message-post":lambda:case.message_post(x.id,x.actor,x.body)}
        result=commands[x.action]()
        print(json.dumps(result,indent=2))
        return 0
    except (ValueError,OSError) as error:
        print(json.dumps({"error":str(error)}),file=sys.stderr)
        return 1

if __name__=="__main__":
    sys.exit(main())
