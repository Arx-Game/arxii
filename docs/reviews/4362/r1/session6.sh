#!/usr/bin/env bash
set -u
S=/tmp/claude-1000/-workspaces-arxii/0becb4bd-7ff9-4c65-97f3-936ed6f34cc2/scratchpad
WT=/workspaces/arxii/.claude/worktrees/feature-4362-favor-with-beings-slice-2-pledges-and-sa
export DATABASE_URL=postgres://arxii:arxii@db:5432/rtc_4362 PGPASSWORD=arxii
q() { psql -h db -U arxii -d rtc_4362 -tAc "$1"; }
cd "$WT"
if ss -ltn | grep -qE ':(4000|4001|4002) '; then echo "PORTS BUSY"; exit 3; fi
uv run arx manage shell -c "exec(open('$S/scripts/expire_hobb.py').read())" 2>&1 | grep -E "EXPIRED|Error"
P=$(q "select p.id from arxii_project p join arxii_pledgedetails d on d.project_id=p.id order by p.id desc limit 1")
echo "before start: $(date -u +%T) project $P: $(q "select status, current_progress from arxii_project where id=$P"); lifecycle_tick last_run_at $(q "select last_run_at from arxii_scheduledtaskrecord where task_key='projects.lifecycle_tick'")"
uv run arx start > $S/rtc_start.log 2>&1
for i in $(seq 1 60); do curl -s -o /dev/null -w '%{http_code}' http://localhost:4001/ | grep -qE '200|302' && break; sleep 2; done
echo "server up: $(date -u +%T)"
for i in $(seq 1 66); do
  st=$(q "select status from arxii_project where id=$P")
  [ "$st" != "ACTIVE" ] && break; sleep 10
done
echo "after wait: $(date -u +%T) project $P: $(q "select status, current_progress from arxii_project where id=$P"); lifecycle_tick last_run_at $(q "select last_run_at from arxii_scheduledtaskrecord where task_key='projects.lifecycle_tick'")"
echo "hobb credits: $(q "select string_agg(source||' '||base||'/'||credited, ', ' order by c.id) from arxii_pledgecredit c where pledge_details_id=(select id from arxii_pledgedetails where project_id=$P)")"
echo "hobb favor: $(q "select favor from arxii_devotionstanding s join arxii_charactersheet c on c.character_id=s.character_sheet_id join objects_objectdb o on o.id=c.character_id where o.db_key='Hobb Pennock'")"
timeout 300 python3 $S/rt/telnet.py '[["e2e_test_account","Hobb Pennock",["pledge"]]]'
rm -f docs/reviews/4362/h-ready-for-delete docs/reviews/4362/h-deleted
( cd frontend && timeout 400 npx playwright test --config e2e.backend.config.ts e2e/rt-4362.spec.ts -g "H builder" --workers=1 --reporter=line ) &
PW=$!
for i in $(seq 1 120); do [ -f docs/reviews/4362/h-ready-for-delete ] && break; sleep 1; done
echo "closing award rows before delete: $(q "select count(*) from arxii_favoroutcomeaward where kind='closing'")"
q "delete from arxii_favoroutcomeaward where kind='closing'" >/dev/null
echo "closing award rows after delete: $(q "select count(*) from arxii_favoroutcomeaward where kind='closing'")"
touch docs/reviews/4362/h-deleted
wait $PW; echo "playwright rc=$?"
uv run arx stop > /dev/null 2>&1
