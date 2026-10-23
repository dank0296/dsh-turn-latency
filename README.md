# dsh-turn-latency

A DeepSeek Harness (dsh) turn that answers in 2 seconds can still take 30 to finish. This repo records one such case, the code path responsible, and the one-file fix.

Tested on **dsh 0.2.0-rc.2**, web profile, one workspace with no root `.gitignore`.

## Symptom

Ask `2+2`. The text `4` appears almost immediately. The "Deep diving" indicator keeps running for roughly 30 seconds, and the turn is not marked complete until it stops.

Nothing is wrong with the model. In this case it was a 2-box TP=2 deployment serving DeepSeek V4.1 Flash, measured at ~59 tok/s decode and ~2,200 tok/s prefill.

## Where the 28 seconds go

`packages/core/agent-loop/src/agent.ts`, after the final `step/end`:

```ts
if (turnEnds && this.inbox.nextStep.length === 0) {
  await this.dispatch.serial('agent/turn-stopping', { turn, signal })
}
```

`turn/end` is appended in the `finally`, so it cannot happen until every listener on `agent/turn-stopping` resolves. On the web profile one of those listeners is the **workspace-changes** deliverable (`packages/deliverables/workspace-changes/src/index.ts`):

```ts
ctx.on('agent/turn-stopping', async ({ agent, turn }) => {
  await recorders.get(agent.session)?.stopping(turn)
})
```

That recorder snapshots the work tree (`git.ts`, `snapshots()`):

```ts
git add --all --ignore-errors   # into a scratch index
git write-tree
```

and its config default is:

```ts
timeoutMs: 30_000   // "Milliseconds one git command may run before the turn's record is abandoned."
```

So the turn waits for a full work-tree snapshot, and if that exceeds 30 s the record is abandoned right at the turn boundary. The client's running indicator mounts while the session is running (`packages/client/ui-chat/src/client/chat/RunningStatus.tsx`), so it clears on `turn/end`, not when the text arrives.

## What the session actually looked like

Parsed from `/…/sessions/<workspace>/<session>/session.v4.jsonl.zstd`, timestamps relative to turn start:

```
+0.00s  turn/start
+0.09s  step/start
+2.06s  assistant message complete  content: "4"
+2.06s  step/end
+2.66s  session/title
+29.90s turn/end                    <- the 28 s tail
```

Engine side during the same window: 16 requests, 16 completions, the last one *before* the gap started. Disk fsync measured 0.00 s, and the model stream closes promptly (`[DONE]` then EOF in 0.01 s). The wait was the snapshot, not the model, not the network, not disk.

## Root cause: the workspace was unbaked git

The workspace had:

- **no commits at all** (`fatal: your current branch 'master' does not have any commits yet`), so every file is untracked and there is no baseline to diff against;
- **no root `.gitignore`**;
- a generated sandbox home from the harness sandbox: `.sandboxhome/` with **90,032 files, 2.1 GB** of npm and corepack caches.

Every turn therefore hashed the entire tree from scratch. Reproduced with the plugin's own commands, without restarting anything:

```
cd <workspace> && rm -f /tmp/snapidx
/usr/bin/time -f add-%e-s  env GIT_INDEX_FILE=/tmp/snapidx git add --all --ignore-errors
/usr/bin/time -f tree-%e-s env GIT_INDEX_FILE=/tmp/snapidx git write-tree
```

Before the fix:

```
add-51.33-s
tree-0.85-s
```

Past the 30 s default, so the snapshot was abandoned every turn, after costing the user the wait.

## Fix

Add a root `.gitignore` to the workspace. For this box, `.gitignore.example` in this repo:

```
.sandboxhome/
.buildlogs/
.ui-verify/
.ghenv/
__pycache__/
*.pyc
.venv/
node_modules/
```

Measured after:

```
status entries:        90,361 -> 270
git add --all:         51.33s -> 0.01s
git write-tree:        0.85s  -> 0.00s
```

The `workspace-changes` config stays at its stock default (no `timeoutMs` override), so the changes panel still reports the full diff, and the turn now closes as soon as the answer lands.

## What did not fix it, and why

Worth recording, because each of these looks plausible:

- **Lowering the plugin timeout** (`timeoutMs: 1500`) shortens the stall but throws away the change record on any turn that touches many files. It is a band-aid; the snapshot stays slow.
- **Disabling optional plugins** (`tool-bidb`, a dictation plugin) changed nothing. The listener is in a stock deliverable.
- **Telemetry / network** was not involved: sampling the dsh process every second across a turn showed zero outbound sockets and ~1% CPU during the tail, and the tail is variable (9 to 28 s) rather than a fixed timeout hit.
- **A headless run of the same agent loop with the same provider patch ends the turn instantly** (`turn-stopping` start and done in the same millisecond), which is how we proved the listener was web-profile-only rather than core.

## Reproducing the measurement

`scripts/session-timeline.py` prints the per-event timeline of a dsh session file and flags every inter-event gap over 1 s:

```
python3 scripts/session-timeline.py /path/to/session.v4.jsonl.zstd
```

`scripts/profile-workspace-snapshot.sh` times the snapshot commands against any workspace:

```
bash scripts/profile-workspace-snapshot.sh /path/to/workspace
```

## Takeaway

Time the turn boundary, not the model. A fast answer with a late `turn/end` looks exactly like a slow model in the UI, because the running indicator is driven by the session state. Session files carry timestamps for every event, so the split between model time and harness time is measurable in one pass.

## License

MIT
