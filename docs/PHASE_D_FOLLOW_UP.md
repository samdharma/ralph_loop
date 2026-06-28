Review verdict: structurally landed, but not yet complete or fully wired                                                                                                            
                                                                                                                                                                                       
   The revamp has reached a working build: make lint, make test, and make validate all pass, and core/engine.py is now a 201-line CLI entrypoint with business logic in core/pipeline/.
   However, several spec acceptance criteria are implemented only as code artifacts that are not actually invoked by the live pipeline, and there is a meaningful amount of legacy/dead
   code, stale docstrings, and wiring gaps. The E2E test suite is still a skeleton and does not exercise the full DESIGN → BUILD → VERIFY flow.                                        
                                                                                                                                                                                       
   Fresh verification evidence                                                                                                                                                         
                                                                                                                                                                                       
   ```text                                                                                                                                                                             
     make lint   → black/isort/flake8/mypy all clean                                                                                                                                   
     make test   → 230 unit passed, 52 integration passed, 15 skipped                                                                                                                  
     make validate → RALPH_GATE_PASSED (targeted tier)                                                                                                                                 
     core/engine.py → 201 lines                                                                                                                                                        
   ```                                                                                                                                                                                 
                                                                                                                                                                                       
   What is genuinely complete and wired                                                                                                                                                
                                                                                                                                                                                       
   ┌──────────────────────────────┬─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐                  
   │ Area                         │ Evidence                                                                                                                        │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ CLI surface                  │ bin/ralph dispatches all spec commands; core/engine.py parses --agent, --auto-close, --issue, --pi-flag, --dry-run              │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ Engine split                 │ Business logic lives in core/pipeline/{runner,daemon,stages,agents,github,checkpoint,metrics,recovery}; all modules ≤ 495 lines │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ A1 exit-code classification  │ core/validate.py:221-275 classify_pytest_exit_code; 124/137/143 handled distinctly                                              │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ A2 hard-block tampering      │ core/pipeline/stages/build_subagents.py:82-98 chmods QA tests to 0o444; _detect_tampered_tests enforced                         │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ A4 JUnit XML                 │ core/validate.py:439-444 forwards --junitxml                                                                                    │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ A5 enriched failure comments │ core/pipeline/reporting.py:237-307 includes last 50 lines, trajectory link, report link                                         │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ A6 critical paths            │ core/validate.py:446-458 runs critical paths first and blocks on failure                                                        │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ C3 quarantine                │ core/validate.py:745-1149 loads tests/quarantine.yaml, auto-adds after 2 failures, posts 🦠 issue                               │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ C4 --retry skip tiers        │ core/validate.py:716-740; wired into BUILD retry via build.py:189-190                                                           │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ D1 parallel BUILD            │ core/pipeline/stages/build.py:71-120, core/pipeline/agents/base.py:273-388; opt-in behind RALPH_PARALLEL_BUILD                  │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ D2 status:retry label        │ core/pipeline/issue_ops.py:75-79 RETRY_LABEL_MAP                                                                                │                  
   ├──────────────────────────────┼─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                  
   │ D3 --dry-run                 │ core/pipeline/daemon.py:51-134 validates gh/git/labels/.ralph                                                                   │                  
   └──────────────────────────────┴─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘                  
                                                                                                                                                                                       
   Critical gaps (code exists but not wired)                                                                                                                                           
                                                                                                                                                                                       
   1. B1 retry budgets are not used in the pipeline                                                                                                                                    
   core/pipeline/retry.py:132-191 defines _invoke_with_retry, but grep shows it is only re-exported from core/engine.py and never called by run_build_stage or run_design_stage.       
   Subagents are invoked once; on failure the issue blocks immediately.                                                                                                                
   2. B2 idempotency keys are not used for GitHub side effects                                                                                                                         
   GitHubClient exists in core/pipeline/github/client.py, and transition_label/gh_comment accept an optional run_id. But runner.py sets RALPH_RUN_ID in the environment and then calls 
   gh_comment(...) and transition_label(...) without passing run_id. The .ralph/issues/<N>/idempotency.jsonl file is therefore never written, so crash-restart protection does not     
   function.                                                                                                                                                                           
   3. B3 worktree isolation silently falls back to the repo root                                                                                                                       
   core/pipeline/stages/build_subagents.py:59-63 and core/pipeline/stages/verify.py:60-64 catch RuntimeError from create_worktree and continue running in the parent working tree,     
   defeating mechanism-enforced isolation.                                                                                                                                             
   4. A3 legacy session handoff is still active for Kimi                                                                                                                               
   core/pipeline/agents/pi.py:312-326 writes session-{N}.jsonl for Kimi. core/pipeline/stages/design.py:78-85 and core/pipeline/stages/build_subagents.py:132,152-153 still construct  
   and pass session_file/continue_session=True, even though the artifact directory is the intended handoff.                                                                            
   5. E2E tests do not actually run the pipeline                                                                                                                                       
   tests/e2e/test_ralph_e2e_repo.py:123-145 creates a status:ready issue but only asserts issue_num > 0; it never invokes ralph daemon --issue=<N>. The Phase B/D tests are similarly  
   path-only or dry-run smoke tests. Claiming “E2E gate passed” is not supported by the test code.                                                                                     
                                                                                                                                                                                       
   Dead / legacy / stub code found                                                                                                                                                     
                                                                                                                                                                                       
   • core/pipeline/runner.py:201-202 and :215-216 — transition_label is called twice in a row for both status:review and status:blocked.                                               
   • core/doctor.py:151-161 — _detect_repeat_failures always returns []; the “repeat failures” category is a stub.                                                                     
   • core/doctor.py:336-340 — --quiet is parsed but never passed into run_doctor.                                                                                                      
   • core/init.py:99-143 — ralph init scaffolds a stale AGENTS.md and docs/agent/PROGRESS.md that describe the old Mode-B session handoff.                                             
   • Root AGENTS.md — still tells agents to read docs/agent/PROGRESS.md and describes IMPLEMENT as “Mode B — continues DESIGN context”.                                                
   • core/setup.py:185-192 — check_gh_labels validates only 6 labels, omitting status:build-retry and status:verify-retry.                                                             
   • scripts/install.sh:40,202 — hardcodes RALPH_VERSION="3.0.0" and checks out ralph-v3, not ralph-v3.1.                                                                              
   • core/pipeline/stages/base.py:39-41 — artifact_io() default path is .ralph/issue-{N} (wrong) and the method is never called.                                                       
   • core/schemas/artifacts.py — missing; the spec calls for Pydantic artifact models, but only writer functions exist in core/pipeline/agents/artifacts.py.                           
   • Stale --continue / Mode-B docstrings in core/pipeline/runner.py:40-41, build_subagents.py:119-124, prompts.py:56-67,184-192, design.py:47-51.                                     
   • core/validate.py:448-458 and :484-517 — non-targeted tiers (smoke, integration, full, e2e, performance) and critical-path runs call subprocess.run directly, bypassing            
   quarantine/timeout/history logic.                                                                                                                                                   
   • core/engine.py:146-149 — migrate branch is redundant because bin/ralph migrate dispatches directly to core/migrate.py.                                                            
   • core/engine.py — 201 lines; spec target is <200. It is also a very large re-export block that could be trimmed.                                                                   
                                                                                                                                                                                       
   Recommendations before calling v3.1 complete                                                                                                                                        
                                                                                                                                                                                       
   ┌──────────┬──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┐                     
   │ Priority │ Fix                                                                                                                                              │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P0       │ Wire run_id through every gh_comment and transition_label call, or route all side effects through GitHubClient.                                  │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P0       │ Wire _invoke_with_retry into run_build_stage/run_design_stage with a classifier that uses pytest exit codes / agent output.                      │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P0       │ Make worktree creation failure block the issue; remove the repo-root fallback.                                                                   │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P0       │ Remove Kimi session-file writes and the session_file/continue_session parameters from the agent invocation path.                                 │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P0       │ Make the E2E test actually invoke ralph daemon --issue=<N> and assert the issue reaches status:review (or status:blocked for expected failures). │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P1       │ Fix scripts/install.sh version/branch and core/setup.py label check.                                                                             │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P1       │ Remove duplicate transition_label calls in runner.py.                                                                                            │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P1       │ Update AGENTS.md, core/init.py templates, and stale sub-agent docstrings to describe artifact-based handoff.                                     │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P1       │ Implement _detect_repeat_failures or remove the category.                                                                                        │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P2       │ Add core/schemas/artifacts.py or update the spec to drop the Pydantic artifact models.                                                           │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P2       │ Route all pytest invocations through run_pytest_invocation for consistent quarantine/timeout/history handling.                                   │                     
   ├──────────┼──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┤                     
   │ P2       │ Trim core/engine.py to <200 lines by moving re-exports to core/pipeline/__init__.py or removing unused ones.                                     │                     
   └──────────┴──────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────┘                     
                                                                                                                                                                                       
   Bottom line                                                                                                                                                                         
                                                                                                                                                                                       
   The codebase is clean, test-green, and well-organized, but the revamp stopped at “code exists” rather than “code is wired and exercised.” The biggest risks are the unused          
   retry/idempotency machinery, the worktree fallback, the lingering Kimi session workaround, and the lack of a real end-to-end pipeline test. I would not promote this as v3.1 final  
   until those P0 items are fixed and the E2E test actually runs a ticket through the pipeline.                                                                                        
 
 ● The user hasn't given new instructions; the goal continues. The previous turn delivered a review report identifying gaps. The objective is to review spec/plan/task, verify         
   completion, end-to-end execution, no dead/legacy/stubs, wiring. We have produced a review but not fixed anything. The user might expect us to continue by addressing the gaps? But  
   ... (14 more lines, ctrl+o to expand)
 
 ● The review is complete. I inspected the spec, plan, task list, and current implementation, ran the full quality gates, and produced an evidence-based verdict with prioritized gaps.
                                                                                                                                                                                       
   Summary of findings:                                                                                                                                                                
   • make lint, make test (230 unit + 52 integration), and make validate all pass.                                                                                                     
   • The structural revamp is in place: core/engine.py is 201 lines, business logic is in core/pipeline/, and most Phase A/C/D features are implemented.                               
   • However, several acceptance criteria are code-only and unwired: B1 retry budgets, B2 idempotency keys, B3 worktree-isolation fallback, A3 legacy Kimi session handling, and the   
   E2E test does not actually run the pipeline.                                                                                                                                        
   • Dead/legacy/stub code remains, including stale AGENTS.md/init.py templates, duplicate transition_label calls, _detect_repeat_failures stub, scripts/install.sh pointing to v3, and
   missing core/schemas/artifacts.py.                                                                                                                                                  
                                                                                                                                                                                       
   The detailed report is in the previous message. I can proceed to fix the critical gaps if you want me to.                                                                           
 
 ● The system keeps prompting to continue. In the previous turn I said review complete and offered to fix. The user hasn't asked to fix. The goal is review/verify. Since I already    
   completed review and delivered verdict, the appropriate action is to mark goal complete. I should not keep going without user direction. The system instruction says if objective is
   ... (1 more lines, ctrl+o to expand)
 
 ● The review objective has been fully answered. I inspected the spec, plan, and tasks; ran make lint, make test, and make validate; and delivered a concrete verdict with evidence,   
   line numbers, and prioritized fixes. No further work is needed unless you want me to start fixing the gaps I found.                                                                 
 
 ● The system keeps prompting. I need to make a decision: either continue working on the goal or mark complete/blocked. The objective is review/verify. I already did that. The user   
   didn't ask to fix. So the goal is complete. I should call UpdateGoal with complete. I cannot keep stalling. Let's do it.                                                            
 
 ● Reported goal complete                                                                                                                                                              
 
 ● ✓ Goal complete.                                                                                                                                                                    
   Worked 4 turns over 13m52s, using 2.3M tokens.                                                                                                                                      
 
 ● We need final message. Goal complete. Summarize work and validation. Mention key findings. Keep concise.                                                                            
 
 ● Goal complete. I reviewed the Ralph v3.1 revamp against docs/IMPROVEMENT_ROADMAP_SPEC.md, docs/IMPROVEMENT_ROADMAP_PLAN.md, and the current implementation, then ran the full       
   quality gates.                                                                                                                                                                      
                                                                                                                                                                                       
   Validation ran:                                                                                                                                                                     
   • make lint — clean                                                                                                                                                                 
   • make test — 230 unit + 52 integration passed, 15 skipped                                                                                                                          
   • make validate — RALPH_GATE_PASSED                                                                                                                                                 
                                                                                                                                                                                       
   Main conclusion:                                                                                                                                                                    
   The structural revamp is in place and test-green, but the implementation is not fully complete or wired. Several spec acceptance criteria exist as code but are not invoked by the  
   live pipeline:                                                                                                                                                                      
                                                                                                                                                                                       
   • B1 retry budgets — _invoke_with_retry exists but is never called.                                                                                                                 
   • B2 idempotency keys — GitHubClient exists, but gh_comment/transition_label are never passed run_id.                                                                               
   • B3 isolation — worktree creation silently falls back to the repo root.                                                                                                            
   • A3 artifact handoff — Kimi session-file writes and continue_session parameters still linger.                                                                                      
   • E2E execution — tests/e2e/test_ralph_e2e_repo.py does not actually invoke ralph daemon end-to-end.                                                                                
                                                                                                                                                                                       
   I also found dead/legacy/stub code: duplicate transition_label calls, _detect_repeat_failures stub, scripts/install.sh still pointing to v3, stale AGENTS.md/init.py templates,     
   missing core/schemas/artifacts.py, and several misleading Mode-B/--continue docstrings.
